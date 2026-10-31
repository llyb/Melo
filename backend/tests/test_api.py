import asyncio

import httpx
import pytest


async def test_health_and_chat_contract():
    from app.main import create_app
    from app.settings import Settings

    class Runner:
        async def reply(self, messages, *, request_id=None):
            return messages[-1].content

    app = create_app(Settings(local_token="local-test"), Runner())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        assert (await c.get("/api/v1/health")).status_code == 401
        headers = {"Authorization": "Bearer local-test"}
        health = await c.get("/api/v1/health", headers=headers)
        assert health.json() == {"status": "ok", "model_configured": False}
        response = await c.post("/api/v1/chat", headers=headers, json={
            "messages": [{"role": "user", "content": "你好"}]})
        assert response.status_code == 200
        assert response.json()["message"] == {"role": "assistant", "content": "你好"}
        assert response.headers["x-request-id"] == response.json()["request_id"]


@pytest.mark.parametrize("messages", [[], [{"role": "system", "content": "x"}],
    [{"role": "user", "content": " "}], [{"role": "user", "content": "x" * 8001}],
    [{"role": "assistant", "content": "x"}],
    [{"role": "user", "content": "x", "extra": 1}],
    [{"role": "user", "content": "x"}] * 3])
async def test_invalid_messages(messages):
    from app.main import create_app
    from app.settings import Settings
    app = create_app(Settings(local_token="t"))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/api/v1/chat", headers={"Authorization": "Bearer t"},
                         json={"messages": messages})
        assert r.status_code == 422
        assert r.json()["error"]["code"] == "INVALID_REQUEST"
        assert "messages" not in r.json()["error"]


async def test_missing_config_and_body_limit():
    from app.main import create_app
    from app.settings import Settings
    app = create_app(Settings(local_token="t"))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        headers = {"Authorization": "Bearer t"}
        r = await c.post("/api/v1/chat", headers=headers,
                         json={"messages": [{"role": "user", "content": "hi"}]})
        assert r.status_code == 503
        assert r.json()["error"]["code"] == "MODEL_NOT_CONFIGURED"
        r = await c.post("/api/v1/chat", headers=headers, content=b"x" * (1024 * 1024 + 1))
        assert r.status_code == 413
        r = await c.post("/api/v1/chat", headers=headers, content="{")
        assert r.status_code == 422


async def test_concurrency_and_timeout_release():
    from app.main import create_app
    from app.settings import Settings

    started = asyncio.Event()
    release = asyncio.Event()

    class Runner:
        async def reply(self, messages, *, request_id=None):
            started.set()
            await release.wait()
            return "ok"

    app = create_app(Settings(local_token="t"), Runner())
    app.state.chat_timeout = 0.05
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        async def send():
            return await c.post("/api/v1/chat", headers={"Authorization": "Bearer t"},
                                json={"messages": [{"role": "user", "content": "hi"}]})
        first = asyncio.create_task(send())
        await started.wait()
        assert (await send()).status_code == 429
        assert (await first).status_code == 504
        release.set()
        assert (await send()).status_code == 200


@pytest.mark.parametrize("kind,status,code", [
    ("auth", 502, "MODEL_AUTH_ERROR"), ("permission", 502, "MODEL_AUTH_ERROR"),
    ("rate", 429, "RATE_LIMITED"), ("upstream", 502, "UPSTREAM_ERROR"),
    ("timeout", 504, "MODEL_TIMEOUT"), ("blank", 502, "UPSTREAM_ERROR"),
    ("large", 502, "UPSTREAM_ERROR"), ("unknown", 500, "INTERNAL_ERROR")])
async def test_error_mapping_and_slot_release(kind, status, code, caplog):
    import openai

    from app.main import create_app
    from app.settings import Settings

    response = httpx.Response(400, request=httpx.Request("POST", "https://example.test"))

    class Runner:
        failed = False

        async def reply(self, messages, *, request_id=None):
            if self.failed:
                return "recovered"
            self.failed = True
            errors = {
                "auth": openai.AuthenticationError("private-input", response=response, body=None),
                "permission": openai.PermissionDeniedError("private-input", response=response, body=None),
                "rate": openai.RateLimitError("private-input", response=response, body=None),
                "upstream": openai.APIConnectionError(request=response.request),
                "timeout": openai.APITimeoutError(request=response.request),
                "unknown": RuntimeError("private-input"),
            }
            if kind in errors:
                raise errors[kind]
            return " " if kind == "blank" else "x" * 16001

    caplog.set_level("INFO", logger="melo")
    app = create_app(Settings(local_token="private-token"), Runner())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        async def send():
            return await c.post("/api/v1/chat", headers={"Authorization": "Bearer private-token"},
                                json={"messages": [{"role": "user", "content": "private-input"}]})
        first = await send()
        assert first.status_code == status
        assert first.json()["error"]["code"] == code
        if status == 429:
            assert first.headers["retry-after"] == "5"
        assert (await send()).status_code == 200
        assert "private-input" not in first.text + caplog.text
        assert "private-token" not in first.text + caplog.text


async def test_chunked_limit_unicode_and_total_context():
    from app.main import create_app
    from app.settings import Settings

    class Runner:
        async def reply(self, messages, *, request_id=None):
            return "ok"

    app = create_app(Settings(local_token="t"), Runner())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        headers = {"Authorization": "Bearer t"}

        async def oversized():
            yield b"x" * (1024 * 1024)
            yield b"x"

        assert (await c.post("/api/v1/chat", headers=headers, content=oversized())).status_code == 413
        emoji = [{"role": "user", "content": "😀" * 8000}]
        assert (await c.post("/api/v1/chat", headers=headers, json={"messages": emoji})).status_code == 200
        long = [{"role": "user" if i % 2 == 0 else "assistant", "content": "x" * 8000} for i in range(9)]
        assert (await c.post("/api/v1/chat", headers=headers, json={"messages": long})).status_code == 422


async def test_successful_long_assistant_reply_can_be_replayed():
    from app.main import create_app
    from app.settings import Settings

    class Runner:
        async def reply(self, messages, *, request_id=None):
            return "a" * 9000

    app = create_app(Settings(local_token="t"), Runner())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        headers = {"Authorization": "Bearer t"}
        first = await c.post("/api/v1/chat", headers=headers,
                             json={"messages": [{"role": "user", "content": "hello"}]})
        history = [{"role": "user", "content": "hello"}, first.json()["message"],
                   {"role": "user", "content": "continue"}]
        second = await c.post("/api/v1/chat", headers=headers, json={"messages": history})
        assert second.status_code == 200
