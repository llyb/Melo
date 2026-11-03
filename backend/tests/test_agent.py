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


async def run_turn(runner, session_id, turn_id, attempt_no, base_checkpoint_id, content, request_id):
    async def ignore_event(*_args):
        pass
    return await runner.execute_run({'session_id': session_id, 'turn_id': turn_id,
        'attempt_no': attempt_no, 'base_checkpoint_id': base_checkpoint_id,
        'request_id': request_id}, content, ignore_event)


async def run_text(runner, messages, *, request_id=None):
    from uuid import uuid4

    from langgraph.checkpoint.memory import InMemorySaver
    if runner.graph.checkpointer is None:
        runner.graph.checkpointer = InMemorySaver()
    sid = str(uuid4())
    base = await runner.initialize_thread(sid)
    result = await run_turn(runner, sid, str(uuid4()), 1, base, messages[-1], request_id or str(uuid4()))
    return result['text']


async def test_ambient_tracing_cannot_export_conversations(monkeypatch):
    from unittest.mock import patch

    from langchain_core.tracers.langchain import LangChainTracer

    from app.agent import AgentRunner
    from app.settings import Settings

    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "true")
    with patch.object(LangChainTracer, "__init__", side_effect=RuntimeError("tracing forbidden")) as tracer:
        runner = AgentRunner(Settings(local_token="t"), model=LocalModel())
        assert await run_text(runner, ["private"]) == "private"
        assert tracer.call_count == 0


async def test_only_one_graph_is_built_with_obsidian():
    from unittest.mock import patch

    from deepagents import create_deep_agent

    from app.agent import AgentRunner
    from app.obsidian import Obsidian
    from app.settings import Settings
    settings = Settings(local_token='t', obsidian_enabled=True)
    with patch('app.agent.create_deep_agent', wraps=create_deep_agent) as build:
        runner = AgentRunner(settings, model=LocalModel(), obsidian=Obsidian(settings))
    assert build.call_count == 1
    assert not hasattr(runner, 'legacy_graph')


async def test_native_graph_can_finish_after_more_than_25_tool_steps():
    from uuid import uuid4

    from langchain_core.messages import ToolMessage

    from app.agent import AgentRunner
    from app.settings import Settings

    class ManyTools(LocalModel):
        calls: int = 0
        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            self.calls += 1
            if self.calls <= 30:
                message = AIMessage(content='', tool_calls=[{
                    'name': 'ls', 'args': {'path': '/'}, 'id': str(uuid4())}])
            else:
                assert isinstance(messages[-1], ToolMessage)
                message = AIMessage(content='finished')
            return ChatResult(generations=[ChatGeneration(message=message)])
    model = ManyTools()
    runner = AgentRunner(Settings(local_token='t'), model=model)
    assert await run_text(runner, ['go']) == 'finished'
    assert model.calls == 31
