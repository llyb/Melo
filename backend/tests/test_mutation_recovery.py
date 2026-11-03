import asyncio
import sqlite3
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.agent import AgentRunner
from app.main import ChatError, create_app
from app.obsidian import UnknownMutationError, current_run, digest
from app.sessions import SessionCatalog
from app.settings import Settings
from tests.test_agent import LocalModel
from tests.test_background_api import terminal
from tests.test_obsidian_approval import FakeObsidian


async def test_lost_write_response_never_repeats_and_reconciliation_is_explicit(tmp_path):
    store = SessionCatalog(tmp_path / 'catalog.sqlite3')
    sid = store.create()['id']
    store.accept_run(sid, 'run', 0, 'input')
    obsidian = FakeObsidian(Settings(local_token='t'))
    await obsidian.connect()
    native = obsidian.call

    async def lost(name, args):
        result = await native(name, args)
        if name == 'vault_write':
            raise TimeoutError('private response detail')
        return result

    obsidian.call = lost
    token = current_run.set({'id': 'run', 'store': store})
    try:
        for _ in range(2):
            with pytest.raises(UnknownMutationError):
                await obsidian.write('test.md', 'new', 'v1', 'call')
        assert obsidian.writes == 1
        receipt = store.receipts('run')['call']
        assert receipt['status'] == 'unknown'
        assert 'new' not in receipt.values()
        receipt.update(status='reconciled', result_version='v2')
        store.receipt('run', 'call', receipt)
        result = await obsidian.write('test.md', 'new', 'v1', 'call')
        assert result['execution_confirmed'] is False
        assert obsidian.writes == 1
    finally:
        current_run.reset(token)


async def test_end_during_note_inspection_cannot_resurrect_run(tmp_path):
    settings = Settings(local_token='t', data_dir=tmp_path)
    obsidian = FakeObsidian(settings)
    app = create_app(settings, AgentRunner(settings, model=LocalModel()), obsidian)
    async with app.router.lifespan_context(app):
        store, manager = app.state.catalog, app.state.runs
        sid = store.create()['id']
        store.accept_run(sid, 'run', 0, 'input')
        store.patch_run('run', status='needs_reconciliation')
        store.receipt('run', 'call', {'status': 'unknown', 'path': 'test.md', 'content_hash': digest('old')})
        started, release = asyncio.Event(), asyncio.Event()
        original = obsidian.read

        async def delayed(path):
            started.set()
            await release.wait()
            return await original(path)

        obsidian.read = delayed
        task = asyncio.create_task(manager.reconcile('run', 'call', 'v1'))
        await started.wait()
        await manager.end('run')
        release.set()
        with pytest.raises(ChatError):
            await task
        assert store.request('run')['status'] == 'abandoned'
        assert store.receipts('run')['call']['status'] == 'unknown'


async def test_startup_recovers_pre_checkpoint_outbox_without_calling_model(tmp_path):
    settings = Settings(local_token='t', data_dir=tmp_path)
    app = create_app(settings, AgentRunner(settings, model=LocalModel()))
    rid = str(uuid4())
    async with app.router.lifespan_context(app):
        sid = app.state.catalog.create()['id']
        app.state.catalog.accept_run(sid, rid, 0, 'durable input')
    model = LocalModel()
    restored = create_app(settings, AgentRunner(settings, model=model))
    async with restored.router.lifespan_context(restored), AsyncClient(
            transport=ASGITransport(app=restored), base_url='http://test',
            headers={'Authorization': 'Bearer t'}) as client:
        state = (await client.get(f'/api/v1/runs/{rid}')).json()
        assert state['status'] == 'interrupted'
        assert state['content'] == 'durable input'
        assert not model.seen
        restored.state.catalog.patch_run(rid, spent=1000000)
        assert (await client.post(f'/api/v1/runs/{rid}/resume', json={})).status_code == 200
        assert (await terminal(client, rid))['status'] == 'completed'


async def test_orphan_launch_and_stale_resume_are_recoverable_without_overwriting_new_head(tmp_path, monkeypatch):
    settings = Settings(local_token='t', data_dir=tmp_path)
    app = create_app(settings, AgentRunner(settings, model=LocalModel()))
    async with app.router.lifespan_context(app), AsyncClient(
            transport=ASGITransport(app=app), base_url='http://test',
            headers={'Authorization': 'Bearer t'}) as client:
        sid = app.state.catalog.create()['id']
        manager = app.state.runs
        original = manager.launch
        def broken(*args):
            raise RuntimeError('cannot schedule')
        monkeypatch.setattr(manager, 'launch', broken)
        rid = str(uuid4())
        response = await client.post(f'/api/v1/sessions/{sid}/turns', json={
            'turn_id': rid, 'expected_revision': 0, 'content': 'saved'})
        assert response.status_code == 202
        assert response.json()['status'] == 'interrupted'
        assert app.state.catalog.input(rid) == 'saved'
        monkeypatch.setattr(manager, 'launch', original)
        app.state.catalog.patch_run(rid, status='failed')
        newer = str(uuid4())
        await client.post(f'/api/v1/sessions/{sid}/turns', json={
            'turn_id': newer, 'expected_revision': 0, 'content': 'new round'})
        assert (await terminal(client, newer))['status'] == 'completed'
        assert (await client.post(f'/api/v1/runs/{rid}/resume', json={})).status_code == 409
        app.state.catalog.patch_run(rid, status='interrupted')
        with app.state.catalog.connection() as db:
            db.execute('PRAGMA user_version=1')
    restored_model = LocalModel()
    restored = create_app(settings, AgentRunner(settings, model=restored_model))
    async with restored.router.lifespan_context(restored):
        assert restored.state.catalog.request(rid)['status'] == 'failed'
        assert restored.state.catalog.request(newer)['status'] == 'completed'
        assert restored.state.catalog.get(sid)['revision'] == 1
        assert not restored_model.seen


def test_event_ring_reports_only_safe_projection_and_keeps_latest_200(tmp_path):
    store = SessionCatalog(tmp_path / 'catalog.sqlite3')
    sid = store.create()['id']
    store.accept_run(sid, 'run', 0, 'private input')
    for i in range(210):
        store.event('run', 'heartbeat', str(i))
    events = store.events('run', 0)
    assert len(events) == 200
    assert events[0]['seq'] == 12 and events[-1]['seq'] == 211
    assert 'private input' not in str(events)


def test_reconciliation_receipt_and_run_transition_rollback_together(tmp_path):
    store = SessionCatalog(tmp_path / 'catalog.sqlite3')
    sid = store.create()['id']
    store.accept_run(sid, 'run', 0, 'input')
    store.patch_run('run', status='needs_reconciliation')
    store.receipt('run', 'call', {'status': 'unknown'})
    with store.connection() as db:
        db.execute("CREATE TRIGGER fail_run BEFORE UPDATE ON turn_requests BEGIN SELECT RAISE(ABORT, 'fault'); END")
    with pytest.raises(sqlite3.IntegrityError):
        store.reconcile_receipt('run', 'call', 'v2')
    assert store.receipts('run')['call']['status'] == 'unknown'
    with store.connection() as db:
        db.execute('DROP TRIGGER fail_run')
    store.reconcile_receipt('run', 'call', 'v2')
    assert store.receipts('run')['call']['status'] == 'reconciled'
    assert store.request('run')['status'] == 'interrupted'
