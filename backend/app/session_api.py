import asyncio
import sqlite3
from typing import Annotated, Literal
from uuid import UUID

from fastapi import Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.runs import ACTIVE


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


class ApprovalDecision(NewSession):
    decision: Literal["approve", "reject"]


class Reconciliation(NewSession):
    decision: Literal["accept_current"]
    observed_version: str = Field(min_length=1, max_length=1024)


def register_sessions(app, settings, Error):
    async def db(method, *args):
        try:
            return await asyncio.to_thread(getattr(app.state.catalog, method), *args)
        except KeyError:
            raise Error(404, "SESSION_NOT_FOUND", "会话不存在。") from None
        except (sqlite3.Error, OSError):
            raise Error(503, "STORAGE_UNAVAILABLE", "本地存储暂不可用，请重试。", True) from None

    async def summary(session):
        view = app.state.catalog.summary(session)
        pending = next((r for r in reversed(await db("requests", session["id"]))
                        if r["status"] in ACTIVE), None)
        view["active_run"] = app.state.runs.accepted(pending) if pending else None
        return view

    @app.get("/api/v1/sessions")
    async def listing(request: Request, limit: Annotated[int, Query(ge=1, le=100)] = 50,
                      offset: Annotated[int, Query(ge=0)] = 0):
        if set(request.query_params) - {"limit", "offset"}:
            raise Error(422, "INVALID_REQUEST", "分页参数无效。")
        data = await db("list", limit, offset)
        data["items"] = [await summary(item) for item in data["items"]]
        return data

    @app.post("/api/v1/sessions", status_code=201)
    async def create(payload: NewSession):
        session = await db("create")
        return await summary(session)

    @app.get("/api/v1/sessions/{sid}")
    async def detail(sid: UUID, request: Request,
                     limit: Annotated[int, Query(ge=1, le=50)] = 20,
                     before_seq: Annotated[int | None, Query(ge=1)] = None):
        if set(request.query_params) - {"limit", "before_seq"}:
            raise Error(422, "INVALID_REQUEST", "分页参数无效。")
        session = await db("get", str(sid))
        turns = await db("requests", str(sid))
        completed = sorted((t for t in turns if t["status"] == "completed"
                            and (before_seq is None or t["seq"] < before_seq)),
                           key=lambda t: t["seq"])
        page = completed[-limit:]
        messages = []
        for turn in page:
            messages.extend(await app.state.runs.pair(turn))
        pending = next((t for t in reversed(turns) if t["status"] != "completed"
                        and t["status"] != "abandoned"
                        and t["expected_revision"] == session["revision"]), None)
        pending_view = None
        if pending:
            try:
                content = await app.state.runs.content(pending)
            except Error:
                content = None
            pending_view = {"turn_id": pending["turn_id"], "status": pending["status"],
                            "expected_revision": pending["expected_revision"], "content": content}
        failed_turns = []
        for failed in [t for t in turns if t["status"] == "failed"][-20:]:
            try:
                text = await app.state.runs.content(failed)
            except Error:
                continue
            failed_turns.append({"run_id": failed["turn_id"], "content": text})
        return {"session": await summary(session), "messages": messages,
                "has_more": len(completed) > limit,
                "next_before_seq": page[0]["seq"] if len(completed) > limit else None,
                "pending_turn": pending_view, "failed_turns": failed_turns}

    @app.patch("/api/v1/sessions/{sid}")
    async def rename(sid: UUID, payload: Title):
        return await summary(await db("rename", str(sid), payload.title))

    @app.delete("/api/v1/sessions/{sid}")
    async def delete(sid: UUID):
        # Acceptance and deletion share the same short lifecycle lock.
        async with app.state.runs.lock:
            await db("get", str(sid))
            if any(r["status"] in ACTIVE for r in await db("requests", str(sid))):
                raise Error(409, "RUN_ACTIVE", "请先完成或结束该会话的未决运行。")
            await db("mark_deleting", str(sid))
            await app.state.saver.adelete_thread(str(sid))
            await db("remove", str(sid))
        return {"deleted_id": str(sid)}

    @app.post("/api/v1/sessions/{sid}/turns", status_code=202)
    async def send(sid: UUID, payload: Turn, request: Request):
        await db("get", str(sid))
        return await app.state.runs.accept(str(sid), payload, request.state.request_id)

    @app.get("/api/v1/runs/{rid}")
    async def run_state(rid: UUID, request: Request,
                        after_seq: Annotated[int, Query(ge=0)] = 0):
        if set(request.query_params) - {"after_seq"}:
            raise Error(422, "INVALID_REQUEST", "游标参数无效。")
        return await app.state.runs.snapshot(str(rid), after_seq)

    @app.post("/api/v1/runs/{rid}/approvals/{aid}")
    async def decide(rid: UUID, aid: UUID, payload: ApprovalDecision):
        return await app.state.runs.decide(str(rid), str(aid), payload.decision)

    @app.post("/api/v1/runs/{rid}/resume")
    async def resume(rid: UUID, payload: NewSession):
        return await app.state.runs.resume(str(rid))

    @app.post("/api/v1/runs/{rid}/reprepare-approval")
    async def reprepare(rid: UUID, payload: NewSession):
        return await app.state.runs.resume(str(rid), reprepare=True)

    @app.post("/api/v1/runs/{rid}/end")
    async def end(rid: UUID, payload: NewSession):
        return await app.state.runs.end(str(rid))

    @app.get("/api/v1/runs/{rid}/reconciliation/{call_id}")
    async def inspect(rid: UUID, call_id: str):
        return await app.state.runs.reconcile(str(rid), call_id)

    @app.post("/api/v1/runs/{rid}/reconciliation/{call_id}")
    async def reconcile(rid: UUID, call_id: str, payload: Reconciliation):
        return await app.state.runs.reconcile(str(rid), call_id, payload.observed_version)

    @app.get("/api/v1/obsidian/status")
    async def obsidian_status():
        return app.state.obsidian.status()

    @app.post("/api/v1/obsidian/recheck")
    async def obsidian_recheck(payload: NewSession):
        return await app.state.obsidian.connect()
