import json
from unittest.mock import patch

import httpx
import pytest
from langchain_openai import ChatOpenAI

from app.agent import AgentRunner
from app.schemas import Message
from app.settings import Settings


@pytest.mark.parametrize("model_name", ["glm-5.3", "custom-chat"])
async def test_configured_provider_request_returns_only_answer(model_name):
    def completion(request):
        assert str(request.url) == "https://gateway.example/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer offline-key"
        payload = json.loads(request.content)
        assert payload["model"] == model_name
        if model_name == "glm-5.3" and (
                payload.get("thinking", {}).get("type") != "enabled"
                or payload.get("reasoning_effort") != "low"):
            return httpx.Response(400, json={"error": {
                "code": "1210", "message": "This model always engages in thinking"}})
        if model_name == "custom-chat":
            assert "thinking" not in payload
            assert "reasoning_effort" not in payload
        return httpx.Response(200, json={
            "id": "offline", "object": "chat.completion", "created": 0, "model": "glm-5.3",
            "choices": [{"index": 0, "finish_reason": "stop", "message": {
                "role": "assistant", "content": "OK", "reasoning_content": "private-reasoning"}}],
            "usage": {"prompt_tokens": 7, "completion_tokens": 4, "total_tokens": 11}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(completion)) as model_http:
        with patch("app.agent.ChatOpenAI", side_effect=lambda **kwargs:
                   ChatOpenAI(**kwargs, http_async_client=model_http)):
            runner = AgentRunner(Settings(local_token="t", model_api_key="offline-key",
                                          model_base_url="https://gateway.example/v1",
                                          model_name=model_name))
        try:
            assert await runner.reply([Message(role="user", content="Hello")]) == "OK"
        finally:
            runner.close()
