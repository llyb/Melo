"""Durable asynchronous runs and per-session lifecycle; no model work in request handlers."""
import asyncio
import difflib
import json
import logging
import sqlite3
import time
from uuid import uuid4

import openai
from langchain_core.messages import HumanMessage
from langgraph.errors import GraphRecursionError

from app.agent import AgentRunner, InvalidOutputError
from app.obsidian import UnknownMutationError, current_run, digest

ACTIVE = {"accepted", "running", "awaiting_approval", "interrupted", "needs_reconciliation"}
TERMINAL = {"completed", "failed", "abandoned"}


class RunManager:
    limit = 5

    def __init__(self, app, settings, Error):
        self.app, self.settings, self.Error = app, settings, Error
        self.store = app.state.catalog
        self.tasks = {}
        self.lock = asyncio.Lock()
        self.previews = {}

    async def db(self, method, *args, **kwargs):
        return await asyncio.to_thread(getattr(self.store, method), *args, **kwargs)

    def runner(self):
        if self.app.state.runner is None:
            self.app.state.runner = AgentRunner(self.settings, checkpointer=self.app.state.saver,
                                                obsidian=self.app.state.obsidian)
        return self.app.state.runner

    def capacity(self):
        return sum(not t.done() for t in self.tasks.values()) < self.limit

    def conflict(self, code, message):
        return self.Error(409, code, message)

    async def record(self, rid):
        data = await self.db("request", rid)
        if data is None:
            raise self.Error(404, "RUN_NOT_FOUND", "运行不存在。")
        return data

    async def content(self, run):
        value = await self.db("input", run["turn_id"])
        if value is not None:
            return value
        # Outbox may have been replaced by a checkpoint while this read was awaiting SQLite.
        fresh = await self.record(run["turn_id"])
        checkpoint = fresh.get("input_checkpoint_id") or fresh.get("checkpoint_id")
        if checkpoint:
            state = await self.runner().graph.aget_state({"configurable": {
                "thread_id": run["session_id"], "checkpoint_id": checkpoint}})
            user = next((m for m in state.values.get("messages", [])
                         if isinstance(m, HumanMessage) and m.id == run["turn_id"]), None)
            if user:
                return user.content
        raise self.Error(503, "STORAGE_UNAVAILABLE", "已接受输入暂不可读，请勿重复发送。", True)

    def launch(self, run, decisions=None, resume=False):
        rid = run["turn_id"]
        task = asyncio.create_task(self.execute(run, decisions, resume))
        self.tasks[rid] = task
        task.add_done_callback(lambda done: self.tasks.pop(rid, None)
                               if self.tasks.get(rid) is done else None)

    async def accept(self, sid, payload, request_id):
        if not self.app.state.runner_injected and not self.settings.model_configured:
            raise self.Error(503, "MODEL_NOT_CONFIGURED", "请配置后端模型。")
        async with self.lock:
            old = await self.db("request", payload.turn_id)
            if not old and not self.capacity():
                raise self.Error(429, "RATE_LIMITED", "最多5个会话同时运行，请稍后重试。", True)
            try:
                run = await self.db("accept_run", sid, payload.turn_id,
                                    payload.expected_revision, payload.content, request_id)
            except ValueError as e:
                raise self.conflict(str(e), "会话状态或请求内容发生冲突，请刷新。") from None
            if not old:
                try:
                    self.launch(run)
                except RuntimeError:
                    run = await self.db("patch_run", payload.turn_id, status="interrupted")
            elif run["status"] == "accepted" and run["turn_id"] not in self.tasks:
                run = await self.db("patch_run", payload.turn_id, status="interrupted")
            return self.accepted(run)

    @staticmethod
    def accepted(run):
        return {"run_id": run.get("run_id", run["turn_id"]), "turn_id": run["turn_id"],
                "session_id": run["session_id"], "status": run["status"]}

    async def capture(self, rid):
        run = await self.record(rid)
        state = await self.runner().graph.aget_state({"configurable": {"thread_id": run["session_id"]}})
        cp = state.config.get("configurable", {}).get("checkpoint_id")
        if cp and (state.metadata or {}).get("melo_turn_id") == rid:
            fields = {"checkpoint_id": cp}
            if not run.get("input_checkpoint_id") and any(
                    m.id == rid for m in state.values.get("messages", [])):
                fields.update(input_checkpoint_id=cp, user_message_id=rid)
            await self.db("patch_run", rid, **fields)

    async def execute(self, run, decisions=None, resume=False):
        rid = run["turn_id"]
        start = time.monotonic()
        token = current_run.set({"id": rid, "store": self.store})
        heartbeat = None
        try:
            content = await self.content(run)
            if not run.get("base_checkpoint_id"):
                session = await self.db("get", run["session_id"])
                head = session["head_checkpoint_id"]
                if head is None:
                    head = await self.runner().initialize_thread(run["session_id"])
                    session["head_checkpoint_id"] = head
                    await self.db("save", session)
                run = await self.db("patch_run", rid, base_checkpoint_id=head)
            await self.db("patch_run", rid, status="running", error=None)
            await self.db("event", rid, "started", "正在运行")
            async def beat():
                while True:
                    await asyncio.sleep(5)
                    await self.db("event", rid, "heartbeat", "运行连接正常")
            heartbeat = asyncio.create_task(beat())
            async def event(kind, name, path):
                await self.capture(rid)
                label = "正在生成回答" if kind == "on_chat_model_start" else (
                    "工具调用完成：" if kind == "on_tool_end" else "正在调用工具：") + name
                if path is not None:
                    path = str(path).replace("\n", " ")[:240]
                await self.db("event", rid, kind, label, path)
            result = await self.runner().execute_run(run, content, event, decisions, resume)
            await self.capture(rid)
            if result.get("paused"):
                approvals = [{"id": str(uuid4()), "index": i, "decision": None,
                              "expires_at": time.time() + 900,
                              "args_hash": digest(json.dumps(action["args"], sort_keys=True))}
                             for i, action in enumerate(result["actions"])]
                await self.db("patch_run", rid, status="awaiting_approval", approvals=approvals,
                              checkpoint_id=result["checkpoint_id"])
                await self.db("event", rid, "awaiting_approval", "等待你确认修改笔记")
            else:
                latest = await self.record(rid)
                await self.db("publish", latest, result, content)
                await self.db("event", rid, "completed", "回复已完成")
        except BaseException as error:  # noqa: BLE001 — shutdown cancellation must retain the durable recovery state.
            try:
                await self.capture(rid)
                receipts = await self.db("receipts", rid)
                uncertain = any(r["status"] in ("executing", "unknown") for r in receipts.values())
                status = "needs_reconciliation" if uncertain or isinstance(error, UnknownMutationError) else (
                    "interrupted" if isinstance(error, asyncio.CancelledError) else "failed")
                code = "UPSTREAM_ERROR"
                message = "运行失败，请检查连接后手动恢复。"
                if isinstance(error, (TimeoutError, openai.APITimeoutError, GraphRecursionError)):
                    code, message = "MODEL_TIMEOUT", "运行超时，可手动恢复或结束本轮。"
                elif isinstance(error, (openai.AuthenticationError, openai.PermissionDeniedError)):
                    code, message = "MODEL_AUTH_ERROR", "模型认证失败，请检查配置。"
                elif isinstance(error, sqlite3.Error):
                    if not uncertain:
                        status = "interrupted"
                    code, message = "STORAGE_UNAVAILABLE", "本地存储失败，已接受输入仍保留，请手动恢复。"
                if status == "needs_reconciliation":
                    code, message = "WRITE_UNCERTAIN", "笔记可能已写入，请核对后恢复或结束本轮。"
                await self.db("patch_run", rid, status=status, error={"code": code, "message": message})
                await self.db("event", rid, status, message)
            except Exception:  # noqa: BLE001 — recovery must survive storage and checkpoint failures.
                # Leave durable running/outbox state for startup recovery if storage itself failed.
                logging.getLogger(__name__).warning("Run recovery state could not be persisted")
        finally:
            current_run.reset(token)
            if heartbeat:
                heartbeat.cancel()
                await asyncio.gather(heartbeat, return_exceptions=True)
            try:
                await self.db("patch_run", rid, spent=run.get("spent", 0) + time.monotonic() - start)
            except sqlite3.Error:
                logging.getLogger(__name__).warning("Run elapsed time could not be persisted")

    async def pair(self, run):
        result = []
        for role, key, message_id in (("user", "input_checkpoint_id", "user_message_id"),
                                      ("assistant", "result_checkpoint_id", "assistant_message_id")):
            state = await self.runner().graph.aget_state({"configurable": {
                "thread_id": run["session_id"], "checkpoint_id": run[key]}})
            message = next((m for m in state.values.get("messages", [])
                            if m.id == run[message_id]), None)
            if message is None:
                raise self.Error(503, "STORAGE_UNAVAILABLE", "历史读取失败。", True)
            text = message.content
            if isinstance(text, list) and all(isinstance(b, dict) and b.get("type") == "text" for b in text):
                text = "".join(b["text"] for b in text)
            if not isinstance(text, str):
                raise self.Error(503, "STORAGE_UNAVAILABLE", "历史格式不兼容。", True)
            result.append({"id": message.id, "role": role, "content": text})
        return result

    async def actions(self, run):
        state = await self.runner().graph.aget_state({"configurable": {
            "thread_id": run["session_id"], "checkpoint_id": run["checkpoint_id"]}})
        items = [i for task in state.tasks for i in task.interrupts]
        return items[0].value["action_requests"] if items else []

    async def cards(self, run):
        if run["status"] != "awaiting_approval":
            return []
        actions = await self.actions(run)
        if len(actions) != len(run.get("approvals", [])):
            return []
        cards = []
        for approval in run.get("approvals", []):
            action = actions[approval["index"]]
            args = action["args"]
            card = dict(approval, path=args.get("path"), tool=action["name"],
                        expected_version=args.get("expected_version"), stale=False)
            if approval["id"] not in self.previews:
                try:
                    note = await self.app.state.obsidian.read(args["path"])
                    diff = "".join(difflib.unified_diff(note["content"].splitlines(True),
                        args["content"].splitlines(True), fromfile=args["path"], tofile=args["path"]))
                    self.previews[approval["id"]] = {"diff": diff,
                        "stale": note["version"] != args.get("expected_version")}
                except Exception:  # noqa: BLE001 — unavailable preview must disable approval without leaking MCP errors.
                    self.previews[approval["id"]] = {"diff": "", "stale": True}
            card.update(self.previews[approval["id"]])
            card["expired"] = time.time() > approval["expires_at"]
            cards.append(card)
        return cards

    async def snapshot(self, rid, after=0):
        run = await self.record(rid)
        events = await self.db("events", rid, after)
        receipts = await self.db("receipts", rid)
        try:
            content = await self.content(run) if run["status"] not in ("completed", "abandoned") else None
        except self.Error:
            content = None
        return {**self.accepted(run), "revision": run.get("event_seq", 0),
                "session": self.store.summary(await self.db("get", run["session_id"])),
                "updated_at": run.get("updated_at"), "created_at": run.get("created_at"),
                "spent": run.get("spent", 0), "error": run.get("error"),
                "events": events, "cursor": events[-1]["seq"] if events else after,
                "gap": bool(events and events[0]["seq"] > after + 1),
                "messages": await self.pair(run) if run["status"] == "completed" else [],
                "content": content,
                "approvals": await self.cards(run),
                "mutations": [{"id": k, **v} for k, v in receipts.items()]}

    async def resume(self, rid, reprepare=False):
        async with self.lock:
            run = await self.record(rid)
            if any(r['status'] in ('executing', 'unknown') for r in (await self.db('receipts', rid)).values()):
                raise self.conflict('WRITE_UNCERTAIN', '请先核对未知笔记写入，再恢复运行。')
            if rid in self.tasks or run["status"] not in ("awaiting_approval", "interrupted", "failed"):
                raise self.conflict("RUN_ACTIVE", "当前状态不可恢复。")
            session = await self.db("get", run["session_id"])
            if session["revision"] != run["expected_revision"]:
                raise self.conflict("SESSION_CONFLICT", "已有后续成功轮次，不能恢复旧运行。")
            if any(other["turn_id"] != rid and other["status"] in ACTIVE
                   for other in await self.db("requests", run["session_id"])):
                raise self.conflict("RUN_ACTIVE", "本会话已有另一轮未决运行。")
            if not self.capacity():
                raise self.Error(429, "RATE_LIMITED", "最多5会话运行，请稍后手动继续。", True)
            decisions = None
            if run["status"] == "awaiting_approval":
                if reprepare:
                    decisions = [{"type": "reject", "message": "旧审批已过期，请重新读取笔记并提出新的修改确认。"}
                                 for _ in run["approvals"]]
                else:
                    if any(a["decision"] is None or a["expires_at"] < time.time() for a in run["approvals"]):
                        raise self.conflict("APPROVAL_PENDING", "请完成全部审批或重新准备过期修改。")
                    decisions = [{"type": a["decision"], **({"message": "用户拒绝修改，不得绕过确认。"}
                                  if a["decision"] == "reject" else {})} for a in run["approvals"]]
            checkpoint_resume = bool(run.get('checkpoint_id'))
            fields = {}
            if checkpoint_resume and decisions is None:
                state = await self.runner().graph.aget_state({'configurable': {
                    'thread_id': run['session_id'], 'checkpoint_id': run['checkpoint_id']}})
                if not state.next:
                    try:
                        await self.runner().find_result(run['session_id'], rid, run['attempt_no'])
                    except InvalidOutputError:
                        if run.get('approvals') or await self.db('receipts', rid):
                            raise self.conflict('RUN_CANNOT_RESUME', '回答无效且本轮涉及外部操作，请结束本轮；已有笔记不会回滚。') from None
                        checkpoint_resume = False
                        fields = {'attempt_no': run['attempt_no'] + 1, 'checkpoint_id': None}
            run = await self.db("patch_run", rid, request_id=str(uuid4()), status="accepted", **fields)
            try:
                self.launch(run, decisions, resume=checkpoint_resume)
            except RuntimeError:
                run = await self.db('patch_run', rid, status='interrupted')
            return self.accepted(run)

    async def decide(self, rid, aid, decision):
        async with self.lock:
            run = await self.record(rid)
            previous = run.get("approval_decisions", {}).get(aid)
            if previous is not None:
                if previous != decision:
                    raise self.conflict("APPROVAL_CONFLICT", "该审批已有不同决定。")
                return self.accepted(run)
            if run["status"] != "awaiting_approval":
                # Same recorded decision after completion remains idempotent.
                old = next((a for a in run.get("approvals", []) if a["id"] == aid), None)
                if old and old["decision"] == decision:
                    return self.accepted(run)
                raise self.conflict("APPROVAL_STALE", "审批状态已变化。")
            approval = next((a for a in run["approvals"] if a["id"] == aid), None)
            if not approval or approval["expires_at"] < time.time():
                raise self.conflict("APPROVAL_STALE", "审批不存在或已过期。")
            if approval["decision"] not in (None, decision):
                raise self.conflict("APPROVAL_CONFLICT", "该审批已有不同决定。")
            if decision == "approve":
                actions = await self.actions(run)
                args = actions[approval["index"]]["args"]
                note = await self.app.state.obsidian.read(args["path"])
                if note["version"] != args.get("expected_version"):
                    raise self.conflict("NOTE_CHANGED", "笔记已变化，请重新准备修改。")
            approval["decision"] = decision
            known = {**run.get("approval_decisions", {}), aid: decision}
            await self.db("patch_run", rid, approvals=run["approvals"], approval_decisions=known)
            ready = all(a["decision"] for a in run["approvals"])
        if ready and self.capacity():
            return await self.resume(rid)
        return self.accepted(run)

    async def end(self, rid):
        async with self.lock:
            run = await self.record(rid)
            if rid in self.tasks or run["status"] in ("accepted", "running", "completed"):
                raise self.conflict("RUN_ACTIVE", "运行中不能结束；请等待暂停或完成。")
            await self.db("patch_run", rid, status="abandoned")
            await self.db("event", rid, "abandoned", "用户已结束本轮；外部笔记未回滚")
            return self.accepted(await self.record(rid))

    async def reconcile(self, rid, call_id, observed_version=None):
        run = await self.record(rid)
        receipt = (await self.db("receipts", rid)).get(call_id)
        if run["status"] != "needs_reconciliation" or not receipt:
            raise self.conflict("RECEIPT_STALE", "写入状态已变化。")
        note = await self.app.state.obsidian.read(receipt["path"])
        observed = {"id": call_id, "path": receipt["path"], "observed_version": note["version"],
                    "matches_target": digest(note["content"]) == receipt["content_hash"]}
        if observed_version is None:
            return observed
        if observed_version != note["version"]:
            raise self.conflict("NOTE_CHANGED", "核对后笔记再次变化，请刷新。")
        async with self.lock:
            fresh = await self.record(rid)
            current = (await self.db("receipts", rid)).get(call_id)
            if fresh["status"] != "needs_reconciliation" or not current or current["status"] not in ("executing", "unknown"):
                raise self.conflict("RECEIPT_STALE", "运行或写入状态已变化。")
            await self.db("reconcile_receipt", rid, call_id, observed_version)
        return observed

    async def recover(self):
        for session in await self.db("all"):
            if session["lifecycle"] == "deleting":
                await self.app.state.saver.adelete_thread(session["id"])
                await self.db("remove", session["id"])
                continue
            for run in await self.db("requests", session["id"]):
                if run["status"] not in ("accepted", "running", "interrupted"):
                    continue
                rid = run["turn_id"]
                current = await self.db('get', session['id'])
                if run['expected_revision'] != current['revision']:
                    await self.db('patch_run', rid, status='failed', error={
                        'code': 'SESSION_CONFLICT', 'message': '已有后续成功轮次，旧运行不可继续。'})
                    continue
                # Capture the saver head before reconciliation so resume retains the original tool call ID.
                await self.capture(rid)
                receipts = await self.db("receipts", rid)
                if any(r["status"] in ("executing", "unknown") for r in receipts.values()):
                    await self.db("patch_run", rid, status="needs_reconciliation")
                    continue
                try:
                    fresh = await self.record(rid)
                    actions = await self.actions(fresh) if fresh.get("checkpoint_id") else []
                    if actions:
                        approvals = [{"id": str(uuid4()), "index": i, "decision": None,
                            "expires_at": time.time()+900,
                            "args_hash": digest(json.dumps(a["args"], sort_keys=True))}
                            for i, a in enumerate(actions)]
                        await self.db("patch_run", rid, status="awaiting_approval", approvals=approvals)
                    else:
                        result = await self.runner().find_result(session["id"], rid, run["attempt_no"])
                        await self.db("publish", await self.record(rid), result, await self.content(fresh))
                except InvalidOutputError:
                    await self.db("patch_run", rid, status="interrupted")

    async def close(self):
        for task in self.tasks.values():
            task.cancel()
        await asyncio.gather(*list(self.tasks.values()), return_exceptions=True)
