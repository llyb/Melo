import asyncio
import hashlib
import sqlite3
from typing import Annotated
from uuid import UUID

from fastapi import Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.agent import AgentRunner, InvalidOutputError


class NewSession(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Title(NewSession):
    title: str = Field(min_length=1, max_length=80)

    @field_validator("title", mode="before")
    @classmethod
    def trim(cls, value):
        if not isinstance(value, str):
            return value
        if not value.strip():
            raise ValueError("Empty title")
        return value.strip()


class Turn(NewSession):
    turn_id: str
    expected_revision: int = Field(ge=0)
    content: str = Field(min_length=1, max_length=8000)

    @field_validator("turn_id")
    @classmethod
    def valid_id(cls, value):
        return str(UUID(value))

    @field_validator("content")
    @classmethod
    def not_blank(cls, value):
        if not value.strip():
            raise ValueError("Empty input")
        return value


def register_sessions(app, settings, Error):
    async def db(method, *args):
        try:
            return await asyncio.to_thread(getattr(app.state.catalog, method), *args)
        except KeyError:
            raise Error(404, "SESSION_NOT_FOUND", "会话不存在。") from None
        except (sqlite3.Error, OSError):
            raise Error(503, "STORAGE_UNAVAILABLE", "本地存储暂不可用，请重试。", True) from None

    def graph():
        if app.state.runner is None:
            app.state.runner = AgentRunner(settings, checkpointer=app.state.saver)
        return app.state.runner

    async def pair(turn):
        messages = []
        for role, cp, mid in (("user", "input_checkpoint_id", "user_message_id"),
                              ("assistant", "result_checkpoint_id", "assistant_message_id")):
            state = await graph().graph.aget_state({"configurable": {
                "thread_id": turn["session_id"], "checkpoint_id": turn[cp]}})
            message = next((m for m in state.values.get("messages", []) if m.id == turn[mid]), None)
            content = message.content if message is not None else None
            if role == "assistant" and isinstance(content, list) and all(
                    isinstance(b, dict) and b.get("type") == "text"
                    and isinstance(b.get("text"), str) for b in content):
                content = "".join(b["text"] for b in content)
            if not isinstance(content, str) or not content.strip():
                raise Error(503, "STORAGE_UNAVAILABLE", "历史记录读取失败。", True)
            messages.append({"id": message.id, "role": role, "content": content})
        return messages

    async def recover(sid):
        for turn in await db("requests", sid):
            if turn["status"] != "running":
                continue
            try:
                result = await graph().find_result(sid, turn["turn_id"], turn["attempt_no"])
            except InvalidOutputError:
                turn["status"] = "failed"
                await db("save_request", turn)
            else:
                content = (await pair({**turn, **result}))[0]["content"]
                await db("publish", turn, result, content)

    async def cleanup():
        for session in await db("all"):
            if session["lifecycle"] == "deleting":
                await app.state.saver.adelete_thread(session["id"])
                await db("remove", session["id"])
            else:
                await recover(session["id"])
    app.state.recover_sessions = cleanup

    def guard():
        if app.state.busy:
            raise Error(429, "RATE_LIMITED", "请等待当前操作完成。", True)

    @app.get("/api/v1/sessions")
    async def listing(request: Request, limit: Annotated[int, Query(ge=1, le=100)] = 50,
                      offset: Annotated[int, Query(ge=0)] = 0):
        if set(request.query_params) - {"limit", "offset"}:
            raise Error(422, "INVALID_REQUEST", "分页参数无效。")
        return await db("list", limit, offset)

    @app.post("/api/v1/sessions", status_code=201)
    async def create(payload: NewSession):
        guard()
        app.state.busy = True
        try:
            return await db("create")
        finally:
            app.state.busy = False

    @app.get("/api/v1/sessions/{sid}")
    async def detail(sid: UUID, request: Request,
                     limit: Annotated[int, Query(ge=1, le=50)] = 20,
                     before_seq: Annotated[int | None, Query(ge=1)] = None):
        if set(request.query_params) - {"limit", "before_seq"}:
            raise Error(422, "INVALID_REQUEST", "分页参数无效。")
        if not app.state.busy:
            app.state.busy = True
            try:
                await recover(str(sid))
            finally:
                app.state.busy = False
        session = await db("get", str(sid))
        turns = await db("requests", str(sid))
        completed = sorted((t for t in turns if t["status"] == "completed"
                            and (before_seq is None or t["seq"] < before_seq)),
                           key=lambda t: t["seq"])
        page = completed[-limit:]
        messages = []
        for turn in page:
            messages.extend(await pair(turn))
        pending = next((t for t in reversed(turns) if t["status"] != "completed"
                        and t["expected_revision"] == session["revision"]), None)
        pending_view = None
        if pending:
            pending_view = {"turn_id": pending["turn_id"], "status": pending["status"],
                            "expected_revision": pending["expected_revision"], "content": None}
            async for snapshot in graph().graph.aget_state_history(
                    {"configurable": {"thread_id": str(sid)}}):
                message = next((m for m in snapshot.values.get("messages", [])
                                if m.id == pending["turn_id"]), None)
                if message is not None and isinstance(message.content, str):
                    pending_view["content"] = message.content
                    break
        return {"session": app.state.catalog.summary(session), "messages": messages,
                "has_more": len(completed) > limit,
                "next_before_seq": page[0]["seq"] if len(completed) > limit else None,
                "pending_turn": pending_view}

    @app.patch("/api/v1/sessions/{sid}")
    async def rename(sid: UUID, payload: Title):
        guard()
        app.state.busy = True
        try:
            return await db("rename", str(sid), payload.title)
        finally:
            app.state.busy = False

    @app.delete("/api/v1/sessions/{sid}")
    async def delete(sid: UUID):
        guard()
        app.state.busy = True
        try:
            await db("mark_deleting", str(sid))
            await app.state.saver.adelete_thread(str(sid))
            await db("remove", str(sid))
            return {"deleted_id": str(sid)}
        finally:
            app.state.busy = False

    @app.post("/api/v1/sessions/{sid}/turns")
    async def send(sid: UUID, payload: Turn, request: Request):
        guard()
        app.state.busy = True
        try:
            sid = str(sid)
            if not app.state.runner_injected and not settings.model_configured:
                raise Error(503, "MODEL_NOT_CONFIGURED", "请在后端配置模型 API Key。")
            runner = graph()
            await db("get", sid)
            await recover(sid)
            session = await db("get", sid)
            digest = hashlib.sha256(payload.content.encode()).hexdigest()
            turn = await db("request", payload.turn_id)
            if turn and (turn["session_id"] != sid or turn["input_hash"] != digest
                         or turn["expected_revision"] != payload.expected_revision):
                raise Error(409, "TURN_CONFLICT", "请求编号已用于不同输入。")
            if not turn or turn["status"] != "completed":
                if payload.expected_revision != session["revision"]:
                    raise Error(409, "SESSION_CONFLICT", "会话已更新，请刷新后重试。")
                if session["head_checkpoint_id"] is None:
                    session["head_checkpoint_id"] = await runner.initialize_thread(sid)
                    await db("save", session)
                turn = {"turn_id": payload.turn_id, "session_id": sid, "input_hash": digest,
                            "expected_revision": payload.expected_revision,
                            "base_checkpoint_id": session["head_checkpoint_id"], "status": "running",
                            "attempt_no": (turn["attempt_no"] + 1 if turn else 1)}
                await db("save_request", turn)
                async with asyncio.timeout(app.state.chat_timeout):
                    result = await runner.run_turn(sid, payload.turn_id, turn["attempt_no"],
                        turn["base_checkpoint_id"], payload.content, request.state.request_id)
                await db("publish", turn, result, payload.content)
            return {"request_id": request.state.request_id, "turn_id": payload.turn_id,
                    "session": app.state.catalog.summary(await db("get", sid)),
                    "messages": await pair(await db("request", payload.turn_id))}
        finally:
            app.state.busy = False
