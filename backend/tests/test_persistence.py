from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from app.agent import AgentRunner
from app.settings import Settings
from tests.test_agent import LocalModel


class FileModel(LocalModel):
    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        if isinstance(messages[-1], ToolMessage):
            if any(isinstance(m, HumanMessage) and m.content == "write:fail"
                   for m in messages):
                raise RuntimeError("simulated crash after file write")
            content = messages[-1].content
            answer = AIMessage(content=str(content))
        else:
            user = [m.content for m in messages if isinstance(m, HumanMessage)][-1]
            args = {"file_path": "/note.txt"}
            if user.startswith("write:"):
                args["content"] = user[6:]
            answer = AIMessage(content="", tool_calls=[{
                "name": "write_file" if "content" in args else "read_file",
                "args": args, "id": str(uuid4())}])
        return ChatResult(generations=[ChatGeneration(message=answer)])


async def test_real_file_tools_survive_restart_and_same_path_is_isolated(tmp_path):
    path = str(tmp_path / "files.sqlite3")
    sid = str(uuid4())
    async with AsyncSqliteSaver.from_conn_string(path) as saver:
        runner = AgentRunner(Settings(local_token="t"), model=FileModel(), checkpointer=saver)
        base = await runner.initialize_thread(sid)
        result = await runner.run_turn(sid, str(uuid4()), 1, base, "write:private-note", str(uuid4()))
    async with AsyncSqliteSaver.from_conn_string(path) as saver:
        runner = AgentRunner(Settings(local_token="t"), model=FileModel(), checkpointer=saver)
        read = await runner.run_turn(sid, str(uuid4()), 1,
                                    result["result_checkpoint_id"], "read", str(uuid4()))
        assert "private-note" in read["text"]
        with pytest.raises(RuntimeError, match="simulated crash"):
            await runner.run_turn(sid, str(uuid4()), 1,
                                  read["result_checkpoint_id"], "write:fail", str(uuid4()))
        stable = await runner.run_turn(sid, str(uuid4()), 1,
                                      read["result_checkpoint_id"], "read", str(uuid4()))
        assert "private-note" in stable["text"]
        other = str(uuid4())
        base = await runner.initialize_thread(other)
        empty = await runner.run_turn(other, str(uuid4()), 1, base, "read", str(uuid4()))
        assert "private-note" not in empty["text"]
        await saver.adelete_thread(sid)
        assert await saver.aget_tuple({"configurable": {"thread_id": sid}}) is None


async def test_thread_checkpoint_survives_restart_and_isolates_sessions(tmp_path):
    path = str(tmp_path / "checkpoints.sqlite3")
    session = str(uuid4())
    async with AsyncSqliteSaver.from_conn_string(path) as saver:
        model = LocalModel()
        runner = AgentRunner(Settings(local_token="t"), model=model, checkpointer=saver)
        base = await runner.initialize_thread(session)
        assert model.seen == []
        first = await runner.run_turn(session, str(uuid4()), 1, base, "小明", str(uuid4()))
        assert first["text"] == "小明"
    async with AsyncSqliteSaver.from_conn_string(path) as saver:
        runner = AgentRunner(Settings(local_token="t"), model=LocalModel(), checkpointer=saver)
        second = await runner.run_turn(
            session, str(uuid4()), 1, first["result_checkpoint_id"], "我是谁", str(uuid4())
        )
        assert second["text"] == "小明"
        other = str(uuid4())
        base = await runner.initialize_thread(other)
        result = await runner.run_turn(other, str(uuid4()), 1, base, "独立", str(uuid4()))
        assert result["text"] == "独立"


async def test_native_summary_keeps_referenced_original_history(tmp_path, monkeypatch):
    from deepagents.middleware.summarization import SummarizationMiddleware
    monkeypatch.setattr("app.agent.SummarizationMiddleware", lambda **kwargs:
        SummarizationMiddleware(model=kwargs["model"], backend=kwargs["backend"],
                                trigger=("messages", 4), keep=("messages", 2)))
    async with AsyncSqliteSaver.from_conn_string(str(tmp_path / "summary.sqlite3")) as saver:
        runner = AgentRunner(Settings(local_token="t"), model=LocalModel(), checkpointer=saver)
        sid = str(uuid4())
        base = await runner.initialize_thread(sid)
        first_id = str(uuid4())
        first = await runner.run_turn(sid, first_id, 1, base, "original", str(uuid4()))
        head = first["result_checkpoint_id"]
        for i in range(4):
            result = await runner.run_turn(sid, str(uuid4()), 1, head, f"next {i}", str(uuid4()))
            head = result["result_checkpoint_id"]
        state = await runner.graph.aget_state({"configurable": {
            "thread_id": sid, "checkpoint_id": head}})
        assert state.values.get("_summarization_event")
        original = await runner.graph.aget_state({"configurable": {
            "thread_id": sid, "checkpoint_id": first["input_checkpoint_id"]}})
        assert any(m.id == first_id and m.content == "original"
                   for m in original.values["messages"])
