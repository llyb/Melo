from deepagents import (
    FilesystemMiddleware,
    GeneralPurposeSubagentProfile,
    HarnessProfile,
    create_deep_agent,
    register_harness_profile,
)
from deepagents.backends import StateBackend
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_openai import ChatOpenAI
from langsmith import tracing_context

from app.schemas import Message
from app.settings import Settings


class InvalidOutputError(Exception):
    pass


class AgentRunner:
    def __init__(self, settings: Settings, model: BaseChatModel | None = None):
        model = model or ChatOpenAI(
            model=settings.model_name, api_key=settings.model_api_key,
            base_url=settings.model_base_url, use_responses_api=False,
            max_tokens=2048, timeout=55, max_retries=0,
            extra_body={"thinking": {"type": "disabled"}},
        )
        # Plain chat must not inherit Deep Agents' automatic subagent and filesystem tools.
        register_harness_profile("openai", HarnessProfile(
            excluded_tools=frozenset({"read_file"}),
            general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False)))
        backend = StateBackend()
        self.graph = create_deep_agent(
            model=model,
            system_prompt="你是 Melo，一个简洁、可靠的中文助手。根据当前对话回答用户。",
            backend=backend,
            middleware=[FilesystemMiddleware(backend=backend, tools=["read_file"])],
        )

    async def reply(self, messages: list[Message]) -> str:
        with tracing_context(enabled=False):
            result = await self.graph.ainvoke(
                {"messages": [m.model_dump() for m in messages]},
                config={"recursion_limit": 10, "callbacks": []},
            )
        final = result["messages"][-1]
        if not isinstance(final, AIMessage) or final.tool_calls:
            raise InvalidOutputError
        content = final.content
        if isinstance(content, list):
            if not all(isinstance(b, dict) and b.get("type") == "text"
                       and isinstance(b.get("text"), str) for b in content):
                raise InvalidOutputError
            content = "".join(b["text"] for b in content)
        if not isinstance(content, str) or not content.strip() or len(content) > 16000:
            raise InvalidOutputError
        return content
