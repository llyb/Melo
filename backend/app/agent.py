import logging
from uuid import UUID, uuid4

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
from langsmith import Client, agent_address, traceable, tracing_context
from langsmith.utils import LangSmithError
from urllib3.util import Retry

from app.schemas import Message
from app.settings import Settings

logger = logging.getLogger("melo")

class InvalidOutputError(Exception):
    pass


def metrics_only(data: dict) -> dict:
    # SDK hiding covers messages; errors and inherited metadata need their own filter.
    if "error" in data:
        return {"error": "Agent request failed"}
    result = {key: data[key] for key in
              ("request_id", "ls_provider", "ls_model_name", "ls_model_type") if key in data}
    usage = data.get("usage_metadata")
    if isinstance(usage, dict):
        result["usage_metadata"] = {key: value for key in
            ("input_tokens", "output_tokens", "total_tokens")
            if isinstance(value := usage.get(key), int) and not isinstance(value, bool) and value >= 0}
    return result


class AgentRunner:
    def __init__(self, settings: Settings, model: BaseChatModel | None = None):
        self._trace_address = agent_address(settings.langsmith_agent_id,
            settings.langsmith_agent_environment
        ) if settings.langsmith_enabled and settings.langsmith_agent_id else None
        self._trace_project = None if self._trace_address else settings.langsmith_project
        self._trace_client = None
        if settings.langsmith_enabled:
            try:
                self._trace_client = Client(
                    api_url=settings.langsmith_endpoint, api_key=settings.langsmith_api_key,
                    workspace_id=settings.langsmith_workspace_id or None,
                    hide_inputs=True, hide_outputs=True, anonymizer=metrics_only,
                    omit_traced_runtime_info=True, timeout_ms=2000, retry_config=Retry(total=0),
                )
            except LangSmithError:
                logger.warning("LangSmith monitoring disabled: SDK configuration error.")
        # GLM-5.3 requires thinking; other compatible models receive no GLM-specific fields.
        model_options = {"reasoning_effort": "low", "extra_body": {"thinking": {"type": "enabled"}}}
        model = model or ChatOpenAI(
            model=settings.model_name, api_key=settings.model_api_key,
            base_url=settings.model_base_url, use_responses_api=False,
            max_tokens=2048, timeout=55, max_retries=0,
            **(model_options if settings.model_name.lower().startswith("glm-5.3") else {}),
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

    async def reply(self, messages: list[Message], *, request_id: str | None = None) -> str:
        run_id = UUID(request_id) if request_id else uuid4()
        with tracing_context(enabled=self._trace_client is not None, client=self._trace_client,
                             project_name=self._trace_project, address=self._trace_address,
                             metadata={"request_id": str(run_id)}, tags=["melo"],
                             parent=False, replicas=[]):
            return await self._reply(messages, langsmith_extra={
                "client": self._trace_client, "run_id": run_id,
                "metadata": {"request_id": str(run_id)}, "tags": ["melo"],
            })

    @traceable(name="Melo chat", process_inputs=lambda _: {}, process_outputs=lambda _: {})
    async def _reply(self, messages: list[Message]) -> str:
        result = await self.graph.ainvoke(
            {"messages": [m.model_dump() for m in messages]},
            config={"recursion_limit": 10, "callbacks": [], "run_name": "Deep Agents"},
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

    def close(self):
        if self._trace_client is not None:
            self._trace_client.close(timeout=2)
