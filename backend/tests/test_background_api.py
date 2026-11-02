import asyncio
from uuid import uuid4

from httpx import ASGITransport, AsyncClient

from app.agent import AgentRunner
from app.main import create_app
from app.settings import Settings
from tests.test_agent import LocalModel


async def terminal(client, rid):
    async with asyncio.timeout(20):
        while True:
            response = await client.get(f"/api/v1/runs/{rid}")
            assert response.status_code == 200, response.text
            data = response.json()
            if data["status"] not in ("accepted", "running"):
                await asyncio.sleep(0.02)  # Let final elapsed-time persistence release the lifecycle slot.
                return data
            await asyncio.sleep(0.02)


async def test_five_sessions_background_navigation_and_atomic_rename(tmp_path, monkeypatch):
    settings = Settings(local_token="t", data_dir=tmp_path)
    model = LocalModel()
    runner = AgentRunner(settings, model=model)
    gate = asyncio.Event()
    original = runner.execute_run
    async def slow(*args, **kwargs):
        await gate.wait()
        return await original(*args, **kwargs)
    monkeypatch.setattr(runner, "execute_run", slow)
    app = create_app(settings, runner)
    async with app.router.lifespan_context(app), AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test",
            headers={"Authorization": "Bearer t"}) as client:
        ids, bodies = [], []
        for i in range(6):
            sid = (await client.post("/api/v1/sessions", json={})).json()["id"]
            ids.append(sid)
            body = {"turn_id": str(uuid4()), "expected_revision": 0, "content": f"user {i}"}
            bodies.append(body)
            response = await client.post(f"/api/v1/sessions/{sid}/turns", json=body)
            assert response.status_code == (202 if i < 5 else 429), response.text
        assert (await client.get(f"/api/v1/sessions/{ids[0]}")).status_code == 200
        assert (await client.patch(f"/api/v1/sessions/{ids[0]}", json={"title": "manual"})).status_code == 200
        assert (await client.delete(f"/api/v1/sessions/{ids[0]}")).status_code == 409
        assert (await client.post('/api/v1/chat', json={'messages': [{'role': 'user', 'content': 'legacy'}]})).status_code == 429
        assert (await client.post(f"/api/v1/sessions/{ids[0]}/turns", json=bodies[0])).status_code == 202
        gate.set()
        for body in bodies[:5]:
            result = await terminal(client, body["turn_id"])
            assert result["status"] == "completed", result
            assert result["events"]
        assert len(model.seen) == 5
        detail = (await client.get(f"/api/v1/sessions/{ids[0]}")).json()
        assert detail["session"]["title"] == "manual"
        assert detail["messages"][0]["content"] == "user 0"
