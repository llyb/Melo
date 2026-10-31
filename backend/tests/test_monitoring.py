import json
from unittest.mock import patch
from uuid import UUID

import httpx
import pytest
import requests
from langsmith import Client

from app.agent import AgentRunner
from app.schemas import Message
from app.settings import Settings
from tests.test_agent import LocalModel


class RecordingSession(requests.Session):
    def __init__(self, fail=False):
        super().__init__()
        self.payloads = []
        self.fail = fail
        self.closed = False

    def close(self):
        self.closed = True
        super().close()

    def request(self, method, url, **kwargs):
        if self.fail:
            raise requests.ConnectionError("offline")
        if kwargs.get("data"):
            payload = json.loads(kwargs["data"])
            if "post" in payload or "patch" in payload:
                self.payloads.extend(payload.get("post", []) + payload.get("patch", []))
            else:
                self.payloads.append(payload)
        response = requests.Response()
        response.status_code = 200
        response._content = b"{}"
        response.url = url
        response.request = requests.Request(method, url).prepare()
        return response


def configured_settings(**overrides):
    return Settings(local_token="local-secret", langsmith_enabled=True,
                    langsmith_api_key="test-langsmith-secret", **overrides)


def capture_client(session, batched=False):
    def factory(**kwargs):
        return Client(**kwargs, session=session, auto_batch_tracing=batched,
                      info={"version": "test", "batch_ingest_config": {
                          "use_multipart_endpoint": False, "size_limit": 100,
                          "scale_up_qsize_trigger": 1000, "scale_up_nthreads_limit": 1,
                          "scale_down_nempty_trigger": 1}})
    return patch("app.agent.Client", side_effect=factory)


def test_settings_defaults_and_validation(monkeypatch):
    assert not Settings(local_token="t").langsmith_enabled
    with pytest.raises(ValueError, match="LANGSMITH_API_KEY"):
        Settings(local_token="t", langsmith_enabled=True)
    monkeypatch.setattr("app.settings.load_dotenv", lambda *_args, **_kwargs: None)
    monkeypatch.setenv("MELO_LOCAL_TOKEN", "t")
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGSMITH_API_KEY", "test-langsmith-secret")
    monkeypatch.setenv("LANGSMITH_PROJECT", "my-project")
    monkeypatch.setenv("LANGSMITH_ENDPOINT", "https://eu.api.smith.langchain.com")
    result = Settings.from_env()
    assert result.langsmith_enabled
    assert result.langsmith_project == "my-project"
    assert result.langsmith_endpoint == "https://eu.api.smith.langchain.com"
    assert "test-langsmith-secret" not in repr(result)
    monkeypatch.setenv("LANGSMITH_TRACING", "typo")
    with pytest.raises(ValueError, match="LANGSMITH_TRACING"):
        Settings.from_env()


@pytest.mark.parametrize("agent_id", ["", "melo"])
@pytest.mark.parametrize("batched", [False, True])
async def test_metrics_only_real_sdk_transport_has_usage_and_request_id(agent_id, batched, monkeypatch):
    if agent_id:
        monkeypatch.setenv("LANGSMITH_PROJECT", "melo")
        monkeypatch.setenv("LANGSMITH_AGENT_ID", "melo")
        monkeypatch.setenv("LANGSMITH_AGENT_ENVIRONMENT", "development")
    class UsageModel(LocalModel):
        def _generate(self, *args, **kwargs):
            result = super()._generate(*args, **kwargs)
            result.generations[0].message.usage_metadata = {
                "input_tokens": 5, "output_tokens": 3, "total_tokens": 8}
            return result

    session = RecordingSession()
    request_id = str(UUID(int=1))
    with capture_client(session, batched=batched):
        runner = AgentRunner(configured_settings(langsmith_agent_id=agent_id), model=UsageModel())
        try:
            assert await runner.reply([Message(role="user", content="private-body")],
                                      request_id=request_id) == "private-body"
        finally:
            runner.close()
    text = json.dumps(session.payloads)
    for value in ("private-body", "local-secret", "test-langsmith-secret"):
        assert value not in text
    root = next(p for p in session.payloads if p.get("name") == "Melo chat")
    assert root["id"] == request_id
    if agent_id:
        assert root["address"] == "lrn:agents/melo/environments/development"
        assert not root.get("session_name")
    else:
        assert root["session_name"] == "melo"
    assert root["extra"]["metadata"]["request_id"] == request_id
    assert any(p.get("parent_run_id") == request_id for p in session.payloads)
    assert any(p.get("extra", {}).get("metadata", {}).get("usage_metadata", {}).get("total_tokens") == 8
               for p in session.payloads)
    assert any(p.get("end_time") for p in session.payloads)
    assert all(not p.get("inputs") and not p.get("outputs") for p in session.payloads)


async def test_error_trace_does_not_export_exception_body():
    class FailedModel(LocalModel):
        def _generate(self, *args, **kwargs):
            raise RuntimeError("private-body test-langsmith-secret")

    session = RecordingSession()
    with capture_client(session):
        runner = AgentRunner(configured_settings(), model=FailedModel())
        try:
            with pytest.raises(RuntimeError):
                await runner.reply([Message(role="user", content="private-body")])
        finally:
            runner.close()
    text = json.dumps(session.payloads)
    assert "private-body" not in text
    assert "test-langsmith-secret" not in text
    assert any(p.get("error") for p in session.payloads)


async def test_monitoring_upload_failure_does_not_break_chat():
    with capture_client(RecordingSession(fail=True)):
        runner = AgentRunner(configured_settings(), model=LocalModel())
        try:
            assert await runner.reply([Message(role="user", content="hello")]) == "hello"
        finally:
            runner.close()


async def test_http_request_id_matches_trace_and_shutdown_closes_client():
    from app.main import create_app

    session = RecordingSession()
    settings = configured_settings()
    with capture_client(session):
        runner = AgentRunner(settings, model=LocalModel())
        app = create_app(settings, runner)
        with pytest.raises(RuntimeError, match="shutdown"):
            async with app.router.lifespan_context(app):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                             base_url="http://test") as client:
                    response = await client.post("/api/v1/chat", headers={
                        "Authorization": "Bearer local-secret"}, json={
                        "messages": [{"role": "user", "content": "private-body"}]})
                    assert response.status_code == 200
                    request_id = response.json()["request_id"]
                    assert response.headers["x-request-id"] == request_id
                raise RuntimeError("shutdown")
    assert session.closed
    assert any(p.get("id") == request_id and p.get("name") == "Melo chat" for p in session.payloads)


async def test_disabled_monitoring_does_not_create_sdk_client():
    with patch("app.agent.Client") as client:
        runner = AgentRunner(Settings(local_token="t"), model=LocalModel())
        assert await runner.reply([Message(role="user", content="hello")]) == "hello"
        runner.close()
        client.assert_not_called()


async def test_disabled_monitoring_ignores_inactive_destination():
    runner = AgentRunner(Settings(local_token="t", langsmith_agent_id="INVALID ID"), model=LocalModel())
    assert await runner.reply([Message(role="user", content="hello")]) == "hello"


async def test_ambient_sdk_conflict_disables_only_monitoring(monkeypatch, caplog):
    monkeypatch.setenv("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com")
    monkeypatch.setenv("LANGSMITH_RUNS_ENDPOINTS", '{"https://other.test":"other-key"}')
    runner = AgentRunner(configured_settings(), model=LocalModel())
    assert await runner.reply([Message(role="user", content="hello")]) == "hello"
    assert runner._trace_client is None
    assert "LangSmith monitoring disabled" in caplog.text
    assert "test-langsmith-secret" not in caplog.text


async def test_actual_openai_compatible_model_serialization_is_metrics_only():
    from langchain_openai import ChatOpenAI

    def completion(_request):
        return httpx.Response(200, json={
            "id": "offline", "object": "chat.completion", "created": 0, "model": "glm-5.3",
            "choices": [{"index": 0, "finish_reason": "stop", "message": {
                "role": "assistant", "content": "private-reply"}}],
            "usage": {"prompt_tokens": 7, "completion_tokens": 4, "total_tokens": 11}})

    session = RecordingSession()
    async with httpx.AsyncClient(transport=httpx.MockTransport(completion)) as model_http:
        model = ChatOpenAI(model="glm-5.3", api_key="model-secret",
                           base_url="https://api.z.ai/api/paas/v4", use_responses_api=False,
                           http_async_client=model_http, max_retries=0)
        with capture_client(session):
            runner = AgentRunner(configured_settings(), model=model)
            try:
                assert await runner.reply([Message(role="user", content="private-prompt")]) == "private-reply"
            finally:
                runner.close()
    payload = json.dumps(session.payloads)
    assert all(value not in payload for value in
               ("private-prompt", "private-reply", "model-secret", "test-langsmith-secret"))
    assert any(p.get("extra", {}).get("metadata", {}).get("usage_metadata", {}).get("total_tokens") == 11
               for p in session.payloads)
