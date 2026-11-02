"""Restricted native MCP tools. Credentials never become tool parameters or graph state."""
import asyncio
import hashlib
import json
import ssl
from contextvars import ContextVar
from typing import Annotated
from urllib.parse import urlsplit

from langchain_core.tools import InjectedToolCallId, ToolException, tool

current_run = ContextVar("obsidian_run", default=None)


class UnknownMutationError(Exception):
    pass


def validate_path(path, directory=False):
    if not isinstance(path, str) or "\x00" in path or "\\" in path or ":" in path:
        raise ValueError("Invalid vault path")
    if directory and path == "":
        return path
    parts = path.split("/")
    if not path or any(p in ("", ".", "..") for p in parts):
        raise ValueError("Invalid vault path")
    if any(p.casefold().startswith(".obsidian") for p in parts):
        raise ValueError("Configuration paths are unavailable")
    if not directory and not path.lower().endswith(".md"):
        raise ValueError("Only Markdown notes are supported")
    return path


def validate_url(value):
    url = urlsplit(value)
    if (url.scheme not in ("http", "https") or url.hostname not in ("127.0.0.1", "localhost", "::1")
            or url.path != "/mcp/" or url.username or url.password or url.query or url.fragment
            or (url.scheme == "http" and url.port != 27123)):
        raise ValueError("Expected local Obsidian MCP URL")


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


class Obsidian:
    def __init__(self, settings):
        self.settings = settings
        self.adapter = None
        self.state = "disabled" if not settings.obsidian_enabled else "unconfigured"
        self.write_supported = False

    def status(self):
        return {"enabled": self.settings.obsidian_enabled, "status": self.state,
                "write_supported": self.write_supported}

    async def connect(self):
        self.adapter, self.write_supported = None, False
        if not self.settings.obsidian_enabled:
            return self.status()
        if not self.settings.obsidian_api_key:
            self.state = "unconfigured"
            return self.status()
        try:
            validate_url(self.settings.obsidian_url)
            context = ssl.create_default_context(cafile=self.settings.obsidian_ca_file or None)
            import httpx2
            from fastmcp import Client
            from fastmcp.client.transports import StreamableHttpTransport
            from langchain.mcp import MCPAdapter

            def factory(**kwargs):
                return httpx2.AsyncClient(headers=kwargs.get("headers"), auth=kwargs.get("auth"),
                    timeout=kwargs.get("timeout", 10), follow_redirects=False, trust_env=False,
                    verify=context)
            transport = StreamableHttpTransport(self.settings.obsidian_url,
                headers={"Authorization": "Bearer " + self.settings.obsidian_api_key},
                httpx_client_factory=factory)
            adapter = MCPAdapter(Client(transport, timeout=15, init_timeout=5))
            async with asyncio.timeout(8), adapter:
                tools = await adapter.list_tools()
            schemas = {t.name: t.args_schema for t in tools}
            if not {"vault_list", "vault_read", "search_simple"} <= schemas.keys():
                self.state = "incompatible"
                return self.status()
            write = schemas.get("vault_write", {}).get("properties", {})
            self.write_supported = "ifMatch" in write and "ifNoneMatch" in write
            self.adapter = adapter
            self.state = "ready"
        except Exception as error:  # noqa: BLE001 — SDK wraps transport errors; never expose credential-bearing details.
            name = type(error).__name__.lower()
            self.state = "tls_error" if "ssl" in name or "certificate" in str(error).lower() else "unavailable"
        return self.status()

    async def call(self, name, arguments):
        if self.state != "ready" or self.adapter is None:
            raise ToolException("Obsidian未连接，请检查本机插件、凭据和证书。")
        async with asyncio.timeout(20 if name == "vault_write" else 15):
            async with self.adapter.client:
                result = await self.adapter.client.call_tool(name, arguments, raise_on_error=False)
        if result.is_error:
            raise ToolException("Obsidian拒绝操作：可能是文件不存在或版本冲突，请重新读取，不能覆盖已有改动。")
        data = result.structured_content
        if data is None:
            texts = [b.text for b in result.content if getattr(b, "type", None) == "text"]
            text = "\n".join(texts)
            try:
                data = json.loads(text)
            except ValueError:
                data = {"result": text}
        return data

    async def read(self, path):
        validate_path(path)
        data = await self.call("vault_read", {"path": path})
        if not isinstance(data, dict) or not isinstance(data.get("content"), str) or not data.get("version"):
            raise ToolException("插件返回的笔记格式不兼容，无法安全修改。")
        if len(data["content"].encode()) > 128 * 1024:
            raise ToolException("笔记超过128KiB，本版不截断读取或覆盖。")
        return {"path": path, "content": data["content"], "version": data["version"]}

    async def write(self, path, content, version, call_id):
        validate_path(path)
        if len(content.encode()) > 128 * 1024:
            raise ToolException("笔记超过128KiB，未执行写入。")
        if not self.write_supported:
            raise ToolException("插件不支持条件写，已禁用笔记修改。")
        ctx = current_run.get()
        if ctx is None:
            raise ToolException("笔记写入必须在持久会话中执行。")
        store, rid = ctx["store"], ctx["id"]
        args_hash = digest(json.dumps([path, content, version], ensure_ascii=False))
        receipts = await asyncio.to_thread(store.receipts, rid)
        receipt = receipts.get(call_id)
        if receipt:
            if receipt["args_hash"] != args_hash:
                raise UnknownMutationError("Mutation identity conflict")
            if receipt["status"] in ("succeeded", "reconciled"):
                return {"status": receipt["status"], "path": path,
                        "version": receipt.get("result_version"),
                        "execution_confirmed": receipt["status"] == "succeeded"}
            if receipt["status"] in ("executing", "unknown"):
                raise UnknownMutationError("Write result requires reconciliation")
        if version:
            # Re-read immediately before writing: a graph resume does not retain in-memory read state.
            fresh = await self.read(path)
            if fresh["version"] != version:
                raise ToolException("笔记已变化，请重新读取并重新申请修改确认。")
        receipt = {"path": path, "args_hash": args_hash, "expected_version": version,
                       "content_hash": digest(content), "status": "executing"}
        await asyncio.to_thread(store.receipt, rid, call_id, receipt)
        try:
            result = await self.call("vault_write", {"path": path, "content": content,
                **({"ifMatch": version} if version else {"ifNoneMatch": "*"})})
        except ToolException:
            receipt["status"] = "failed"
            await asyncio.to_thread(store.receipt, rid, call_id, receipt)
            raise
        except BaseException:  # noqa: BLE001 — cancellation can happen after a real write; persist uncertainty too.
            receipt["status"] = "unknown"
            await asyncio.shield(asyncio.to_thread(store.receipt, rid, call_id, receipt))
            raise UnknownMutationError("Write result requires reconciliation") from None
        receipt.update(status="succeeded", result_version=result.get("version") if isinstance(result, dict) else None)
        await asyncio.to_thread(store.receipt, rid, call_id, receipt)
        return {"status": "succeeded", "path": path, "version": receipt.get("result_version")}

    def tools(self):
        @tool
        async def obsidian_list_notes(path: str = "") -> str:
            """List a relative directory of the local Obsidian vault."""
            validate_path(path, directory=True)
            return json.dumps(await self.call("vault_list", {"path": path}), ensure_ascii=False)

        @tool
        async def obsidian_read_note(path: str) -> str:
            """Read a Markdown note and its version before proposing an update."""
            return json.dumps(await self.read(path), ensure_ascii=False)

        @tool
        async def obsidian_search_notes(query: str) -> str:
            """Search Obsidian notes; results are bounded to 20 files and 5 matches each."""
            return json.dumps(await self.call("search_simple", {"query": query,
                "maxResults": 20, "maxMatchesPerFile": 5, "contextLength": 200}), ensure_ascii=False)

        @tool
        async def obsidian_create_note(path: str, content: str,
                tool_call_id: Annotated[str, InjectedToolCallId]) -> str:
            """Create a new Markdown note only if the path does not already exist."""
            return json.dumps(await self.write(path, content, None, tool_call_id), ensure_ascii=False)

        @tool
        async def obsidian_update_note(path: str, content: str, expected_version: str,
                tool_call_id: Annotated[str, InjectedToolCallId]) -> str:
            """Replace an existing Markdown note after user approval; use the version from read."""
            if not expected_version or expected_version == "*":
                raise ToolException("必须提供读取到的具体版本。")
            return json.dumps(await self.write(path, content, expected_version, tool_call_id), ensure_ascii=False)

        tools = [obsidian_list_notes, obsidian_read_note, obsidian_search_notes,
                 obsidian_create_note, obsidian_update_note]
        for entry in tools:
            entry.handle_tool_error = True
        return tools
