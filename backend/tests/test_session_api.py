import asyncio
import sqlite3
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.agent import AgentRunner
from app.main import create_app
from app.settings import Settings
from tests.test_agent import LocalModel


async def test_sessions_send_replay_restart_and_delete(tmp_path):
    settings = Settings(local_token="t", data_dir=tmp_path)
    model = LocalModel()
    for restart in range(2):
        app = create_app(settings, AgentRunner(settings, model=model))
        async with app.router.lifespan_context(app), AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test",
                headers={"Authorization": "Bearer t"}) as c:
                if not restart:
                    a = (await c.post('/api/v1/sessions', json={})).json()
                    sid = a['id']
                    payload = {"turn_id": str(uuid4()), "expected_revision": 0, "content": "小明"}
                    url = f'/api/v1/sessions/{sid}/turns'
                    sent = await c.post(url, json=payload)
                    assert sent.status_code == 200, sent.text
                    count = len(model.seen)
                    assert (await c.post(url, json=payload)).status_code == 200
                    assert len(model.seen) == count
                    conflict = {**payload, 'content': 'other'}
                    assert (await c.post(url, json=conflict)).status_code == 409
                else:
                    detail = (await c.get(f'/api/v1/sessions/{sid}')).json()
                    assert [m['content'] for m in detail['messages']] == ['小明', '小明']
                    assert (await c.delete(f'/api/v1/sessions/{sid}')).status_code == 200
                    assert (await c.get(f'/api/v1/sessions/{sid}')).status_code == 404


async def test_finished_checkpoint_recovers_after_catalog_publish_failure(tmp_path, monkeypatch):
    settings = Settings(local_token="t", data_dir=tmp_path)
    model = LocalModel()
    app = create_app(settings, AgentRunner(settings, model=model))
    async with app.router.lifespan_context(app), AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test",
            headers={"Authorization": "Bearer t"}) as client:
        sid = (await client.post('/api/v1/sessions', json={})).json()['id']
        original = app.state.catalog.publish
        def unavailable(*args):
            raise sqlite3.OperationalError('private storage detail')
        monkeypatch.setattr(app.state.catalog, 'publish', unavailable)
        body = {"turn_id": str(uuid4()), "expected_revision": 0, "content": "safe"}
        url = f'/api/v1/sessions/{sid}/turns'
        failed = await client.post(url, json=body)
        assert failed.status_code == 503
        assert 'private storage detail' not in failed.text
        count = len(model.seen)
        monkeypatch.setattr(app.state.catalog, 'publish', original)
        replay = await client.post(url, json=body)
        assert replay.status_code == 200, replay.text
        assert len(model.seen) == count
        assert replay.json()['session']['revision'] == 1


@pytest.mark.parametrize('patch', [
    {'content': ' '}, {'content': 'x' * 8001}, {'turn_id': '../bad'},
    {'expected_revision': True}, {'expected_revision': -1}, {'extra': 1},
])
async def test_strict_new_turn_boundary(tmp_path, patch):
    app = create_app(Settings(local_token="t", data_dir=tmp_path))
    async with app.router.lifespan_context(app), AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test",
            headers={"Authorization": "Bearer t"}) as client:
        sid = (await client.post('/api/v1/sessions', json={})).json()['id']
        body = {"turn_id": str(uuid4()), "expected_revision": 0, "content": "hello", **patch}
        assert (await client.post(f'/api/v1/sessions/{sid}/turns', json=body)).status_code == 422


async def test_text_blocks_remain_readable_and_legacy_first_keeps_saver(tmp_path, monkeypatch):
    from langchain_core.messages import AIMessage
    from langchain_core.outputs import ChatGeneration, ChatResult
    class BlocksModel(LocalModel):
        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            return ChatResult(generations=[ChatGeneration(message=AIMessage(
                content=[{"type": "text", "text": "answer"}]))])
    monkeypatch.setattr('app.agent.ChatOpenAI', lambda **kwargs: BlocksModel())
    settings = Settings(local_token="t", model_api_key="offline", data_dir=tmp_path)
    app = create_app(settings)
    async with app.router.lifespan_context(app), AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test",
            headers={"Authorization": "Bearer t"}) as client:
        assert (await client.post('/api/v1/chat', json={
            "messages": [{"role": "user", "content": "legacy"}]})).status_code == 200
        sid = (await client.post('/api/v1/sessions', json={})).json()['id']
        body = {"turn_id": str(uuid4()), "expected_revision": 0, "content": "blocks"}
        sent = await client.post(f'/api/v1/sessions/{sid}/turns', json=body)
        assert sent.status_code == 200, sent.text
        assert sent.json()['messages'][1]['content'] == 'answer'
        assert (await client.get(f'/api/v1/sessions/{sid}')).json()['messages'][1]['content'] == 'answer'


async def test_native_turn_timeout_releases_gate_and_retry_does_not_append_twice(tmp_path, monkeypatch):
    settings = Settings(local_token="t", data_dir=tmp_path)
    runner = AgentRunner(settings, model=LocalModel())
    app = create_app(settings, runner)
    started, release = asyncio.Event(), asyncio.Event()
    original = runner.run_turn
    async def delayed(*args):
        started.set()
        await release.wait()
        return await original(*args)
    monkeypatch.setattr(runner, 'run_turn', delayed)
    async with app.router.lifespan_context(app), AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test",
            headers={"Authorization": "Bearer t"}) as client:
        sid = (await client.post('/api/v1/sessions', json={})).json()['id']
        url = f'/api/v1/sessions/{sid}/turns'
        body = {"turn_id": str(uuid4()), "expected_revision": 0, "content": "hi"}
        app.state.chat_timeout = 0.05
        first = asyncio.create_task(client.post(url, json=body))
        await started.wait()
        assert (await client.post(url, json=body)).status_code == 429
        assert (await client.delete(f'/api/v1/sessions/{sid}')).status_code == 429
        assert (await first).status_code == 504
        release.set()
        app.state.chat_timeout = 60
        assert (await client.post(url, json=body)).status_code == 200
        assert len((await client.get(f'/api/v1/sessions/{sid}')).json()['messages']) == 2


async def test_interrupted_deletion_is_finished_at_startup_without_model_key(tmp_path):
    settings = Settings(local_token="t", data_dir=tmp_path)
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        a = app.state.catalog.create()
        b = app.state.catalog.create()
        app.state.catalog.mark_deleting(a['id'])
    restored = create_app(settings)
    async with restored.router.lifespan_context(restored), AsyncClient(
            transport=ASGITransport(app=restored), base_url="http://test",
            headers={"Authorization": "Bearer t"}) as client:
        assert (await client.get(f"/api/v1/sessions/{a['id']}")).status_code == 404
        assert (await client.get(f"/api/v1/sessions/{b['id']}")).status_code == 200
        title = await client.patch(f"/api/v1/sessions/{b['id']}", json={'title': ' ' + '😀' * 80 + ' '})
        assert title.status_code == 200
        assert title.json()['title'] == '😀' * 80
