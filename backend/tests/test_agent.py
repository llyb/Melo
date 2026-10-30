from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field


class LocalModel(BaseChatModel):
    seen: list = Field(default_factory=list)
    offered_tools: list = Field(default_factory=list)
    model_name: str = "melo-test"

    @property
    def _llm_type(self):
        return "melo-test"

    def _get_ls_params(self, **kwargs):
        return {"ls_provider": "openai"}

    def bind_tools(self, tools, **kwargs):
        self.offered_tools = list(tools)
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.seen.append(messages)
        users = [m.content for m in messages if isinstance(m, HumanMessage)]
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=users[0]))])


async def test_real_deep_agent_no_tools_and_no_cross_request_state():
    from app.agent import AgentRunner
    from app.schemas import Message
    from app.settings import Settings

    model = LocalModel()
    runner = AgentRunner(Settings(local_token="t"), model=model)
    first = [Message(role="user", content="小明")]
    assert await runner.reply(first) == "小明"
    second = [*first, Message(role="assistant", content="小明"),
              Message(role="user", content="我是谁")]
    assert await runner.reply(second) == "小明"
    assert await runner.reply([Message(role="user", content="全新会话")]) == "全新会话"
    assert not model.offered_tools
    assert runner.graph.checkpointer is None
    assert len(model.seen[1]) == 4  # one system and three client messages


async def test_ambient_tracing_cannot_export_conversations(monkeypatch):
    from unittest.mock import patch

    from langchain_core.tracers.langchain import LangChainTracer

    from app.agent import AgentRunner
    from app.schemas import Message
    from app.settings import Settings

    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "true")
    with patch.object(LangChainTracer, "__init__", side_effect=RuntimeError("tracing forbidden")) as tracer:
        runner = AgentRunner(Settings(local_token="t"), model=LocalModel())
        assert await runner.reply([Message(role="user", content="private")]) == "private"
        assert tracer.call_count == 0
