import json
import sqlite3
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from app.agent import AgentRunner
from app.main import create_app
from app.obsidian import Obsidian
from app.settings import Settings
from tests.test_agent import LocalModel
from tests.test_background_api import terminal


class FakeObsidian(Obsidian):
    def __init__(self, settings):
        super().__init__(settings)
        self.body, self.version, self.writes = 'old', 'v1', 0

    async def connect(self):
        self.state, self.write_supported = 'ready', True
        return self.status()

    async def call(self, name, arguments):
        if name == 'vault_read':
            return {'content': self.body, 'version': self.version}
        if name == 'vault_write':
            assert arguments['ifMatch'] == self.version
            self.body, self.version = arguments['content'], 'v2'
            self.writes += 1
            return {'version': self.version}
        return {}


class UpdateModel(LocalModel):
    actions: int = 1
    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        last = messages[-1]
        if isinstance(last, ToolMessage):
            message = AIMessage(content='done')
        else:
            message = AIMessage(content='', tool_calls=[{'id': f'call_update_{i}',
                'name': 'obsidian_update_note', 'args': {
                    'path': f'test{i}.md', 'content': 'new', 'expected_version': 'v1'}} for i in range(self.actions)])
        return ChatResult(generations=[ChatGeneration(message=message)])


async def test_native_hitl_requires_approval_and_reuses_write_receipt(tmp_path):
    settings = Settings(local_token='t', data_dir=tmp_path, obsidian_enabled=True)
    obsidian = FakeObsidian(settings)
    runner = AgentRunner(settings, model=UpdateModel(), obsidian=obsidian)
    app = create_app(settings, runner, obsidian)
    async with app.router.lifespan_context(app), AsyncClient(
            transport=ASGITransport(app=app), base_url='http://test',
            headers={'Authorization': 'Bearer t'}) as client:
        sid = (await client.post('/api/v1/sessions', json={})).json()['id']
        rid = str(uuid4())
        response = await client.post(f'/api/v1/sessions/{sid}/turns', json={
            'turn_id': rid, 'expected_revision': 0, 'content': 'update test note'})
        assert response.status_code == 202
        paused = await terminal(client, rid)
        assert paused['status'] == 'awaiting_approval', paused
        assert obsidian.writes == 0
        card = paused['approvals'][0]
        assert '-old' in card['diff'] and '+new' in card['diff']
        approved = await client.post(f"/api/v1/runs/{rid}/approvals/{card['id']}", json={'decision': 'approve'})
        assert approved.status_code == 200, approved.text
        completed = await terminal(client, rid)
        assert completed['status'] == 'completed', json.dumps(completed)
        assert obsidian.writes == 1
        assert obsidian.body == 'new'
        repeated = await client.post(f"/api/v1/runs/{rid}/approvals/{card['id']}", json={'decision': 'approve'})
        assert repeated.status_code == 200
        assert obsidian.writes == 1


@pytest.mark.parametrize('reopen', [False, True])
async def test_group_reject_and_expired_approval_survive_restart(tmp_path, reopen):
    settings = Settings(local_token='t', data_dir=tmp_path, obsidian_enabled=True)
    obsidian = FakeObsidian(settings)
    def build():
        return create_app(settings, AgentRunner(settings, model=UpdateModel(actions=2), obsidian=obsidian), obsidian)
    app = build()
    async with app.router.lifespan_context(app), AsyncClient(
            transport=ASGITransport(app=app), base_url='http://test',
            headers={'Authorization': 'Bearer t'}) as client:
        sid = (await client.post('/api/v1/sessions', json={})).json()['id']
        rid = str(uuid4())
        await client.post(f'/api/v1/sessions/{sid}/turns', json={
            'turn_id': rid, 'expected_revision': 0, 'content': 'update two notes'})
        paused = await terminal(client, rid)
        assert len(paused['approvals']) == 2
        if not reopen:
            cards = paused['approvals']
            assert (await client.post(f"/api/v1/runs/{rid}/approvals/{cards[0]['id']}", json={'decision': 'reject'})).status_code == 200
            assert app.state.catalog.request(rid)['status'] == 'awaiting_approval'
            assert obsidian.writes == 0
            assert (await client.post(f"/api/v1/runs/{rid}/approvals/{cards[1]['id']}", json={'decision': 'reject'})).status_code == 200
            assert (await terminal(client, rid))['status'] == 'completed'
            assert obsidian.writes == 0
    if reopen:
        restored = build()
        async with restored.router.lifespan_context(restored), AsyncClient(
                transport=ASGITransport(app=restored), base_url='http://test',
                headers={'Authorization': 'Bearer t'}) as client:
            run = restored.state.catalog.request(rid)
            assert run['status'] == 'awaiting_approval'
            run['approvals'][0]['expires_at'] = 0
            restored.state.catalog.patch_run(rid, approvals=run['approvals'])
            aid = run['approvals'][0]['id']
            assert (await client.post(f'/api/v1/runs/{rid}/approvals/{aid}', json={'decision': 'approve'})).status_code == 409
            assert (await client.post(f'/api/v1/runs/{rid}/reprepare-approval', json={})).status_code == 200
            assert (await terminal(client, rid))['status'] == 'completed'
            assert obsidian.writes == 0


async def test_receipt_commit_failure_requires_reconciliation_before_resume(tmp_path, monkeypatch):
    settings = Settings(local_token='t', data_dir=tmp_path, obsidian_enabled=True)
    obsidian = FakeObsidian(settings)
    app = create_app(settings, AgentRunner(settings, model=UpdateModel(), obsidian=obsidian), obsidian)
    async with app.router.lifespan_context(app), AsyncClient(
            transport=ASGITransport(app=app), base_url='http://test',
            headers={'Authorization': 'Bearer t'}) as client:
        sid = app.state.catalog.create()['id']
        rid = str(uuid4())
        await client.post(f'/api/v1/sessions/{sid}/turns', json={
            'turn_id': rid, 'expected_revision': 0, 'content': 'write'})
        paused = await terminal(client, rid)
        original = app.state.catalog.receipt
        def fail_success(rid, call_id, data):
            if data['status'] == 'succeeded':
                raise sqlite3.OperationalError('cannot commit receipt')
            return original(rid, call_id, data)
        monkeypatch.setattr(app.state.catalog, 'receipt', fail_success)
        aid = paused['approvals'][0]['id']
        await client.post(f'/api/v1/runs/{rid}/approvals/{aid}', json={'decision': 'approve'})
        uncertain = await terminal(client, rid)
        assert uncertain['status'] == 'needs_reconciliation', uncertain
        assert obsidian.writes == 1
        assert (await client.post(f'/api/v1/runs/{rid}/resume', json={})).status_code == 409
