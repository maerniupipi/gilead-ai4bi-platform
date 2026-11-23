import asyncio
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pptx import Presentation

from app.core.database import get_db
from app.models.chatbi import ChatBIExport, ChatBIMessage
from app.routers.chatbi.router import router
from app.schemas.chatbi import PPTRequest
from app.services.chatbi import exports
from app.services.chatbi.config import APIError
from app.services.chatbi.summary import AISummaryPPTService
from tests.test_chatbi_integration import factory, analysis, USER, OTHER


@pytest.mark.parametrize('raw,expected', [(None, 'ALL'), ('', 'ALL'), ('ALL', 'ALL'), ('default', 'ALL'),
    ('AI', 'AI_SUMMARY'), ('AI_SUMMARY', 'AI_SUMMARY'), ('Summary', 'FULL_SUMMARY'), ('FULL_SUMMARY', 'FULL_SUMMARY')])
def test_modes_are_normalized(raw, expected):
    assert PPTRequest(user=USER.user, conversation_id=uuid4(), summaryType=raw).summary_type == expected
    assert PPTRequest(user=USER.user, conversation_id=uuid4()).summary_type == 'ALL'


@pytest.mark.parametrize('mode', [None, 'ALL'])
def test_default_and_all_make_two_unwatermarked_files_with_one_snapshot(factory, monkeypatch, mode):
    async def summary(*args, **kwargs):
        return {'agenda': ['销售'], 'slides': [{'title': '销售', 'insights': ['本次测试结论']}]}
    monkeypatch.setattr(AISummaryPPTService, 'build_summary', summary)
    events, _ = analysis(factory)
    with factory() as db:
        values = {'summaryType': mode} if mode is not None else {}
        body = PPTRequest(user=USER.user, conversation_id=events[0]['conversation_id'], idempotency_key='dual', **values)
        job = exports.create_export(db, 'ppt', body, USER)
        state = exports.export_state(job, db)
        assert state['file_id'] is None and state['summaryType'] == 'ALL'
        assert {f['summaryType'] for f in state['files']} == {'FULL_SUMMARY', 'AI_SUMMARY'}
        child_ids = job.payload['child_task_ids']
        children = [db.get(ChatBIExport, identifier) for identifier in child_ids]
        assert children[0].payload['message_ids'] == children[1].payload['message_ids'] == job.payload['message_ids']
        again = exports.create_export(db, 'ppt', body, USER)
        assert again.id == job.id and db.query(ChatBIExport).count() == 3
        parent_id = job.id
        claimed = exports.claim_export(factory)
        assert claimed in child_ids and claimed != parent_id
    asyncio.run(exports.process_export(parent_id, factory=factory))
    with factory() as db:
        state = exports.export_state(db.get(ChatBIExport, parent_id), db)
        assert state['status'] == 'succeeded' and len(state['files']) == 2
        assert not state['downloadable']
        for file in state['files']:
            assert file['downloadable']
            job = db.get(ChatBIExport, file['task_id'])
            assert exports.download_url(db, file['file_id'], USER, 'http://local')['url']
            with pytest.raises(APIError) as err:
                exports.download_url(db, file['file_id'], OTHER, 'http://local')
            assert err.value.status == 404
            deck = Presentation(str(exports.file_path(job)))
            assert len(deck.slides) > 1
            for slide in deck.slides:
                assert all(USER.user_id not in shape.text for shape in slide.shapes if shape.has_text_frame)


def test_missing_model_creates_neither_parent_nor_partial_files(factory, monkeypatch):
    events, _ = analysis(factory)
    def missing(*args):
        raise APIError(503, 'summary_not_configured', '请配置摘要模型')
    monkeypatch.setattr(exports, 'resolve_ppt_model', missing)
    with factory() as db:
        with pytest.raises(APIError) as err:
            exports.create_export(db, 'ppt', PPTRequest(user=USER.user, conversation_id=events[0]['conversation_id']), USER)
        assert err.value.code == 'summary_not_configured'
        assert db.query(ChatBIExport).count() == 0


def test_partial_failure_is_visible_while_successful_child_can_download(factory):
    events, _ = analysis(factory)
    with factory() as db:
        job = exports.create_export(db, 'ppt', PPTRequest(user=USER.user, conversation_id=events[0]['conversation_id']), USER)
        children = [db.get(ChatBIExport, value) for value in job.payload['child_task_ids']]
        children[0].status = 'succeeded'
        children[1].status, children[1].error = 'failed', '摘要生成失败'
        db.commit()
        result = exports.export_state(job, db)
        assert result['status'] == 'failed'
        assert [f['status'] for f in result['files']] == ['succeeded', 'failed']


def test_same_key_cannot_change_single_to_dual_request(factory):
    events, _ = analysis(factory)
    with factory() as db:
        values = {'user': USER.user, 'conversation_id': events[0]['conversation_id'], 'idempotency_key': 'same'}
        exports.create_export(db, 'ppt', PPTRequest(**values, summaryType='FULL_SUMMARY'), USER)
        with pytest.raises(APIError) as err:
            exports.create_export(db, 'ppt', PPTRequest(**values, summaryType='ALL'), USER)
        assert err.value.status == 409 and db.query(ChatBIExport).count() == 1


def test_dual_http_poll_preserves_files_and_owner_checks(factory, monkeypatch):
    from app.services.chatbi import chat
    monkeypatch.setattr(chat, 'SessionLocal', factory)
    events, _ = analysis(factory)
    # Directly-created fixture state uses an unscoped internal identity. The HTTP
    # service deliberately scopes ownership to its authenticated service Key.
    import os
    from app.models.chatbi import ChatBIConversation, ChatBIResult
    from app.services.chatbi.credentials import resolve_credential
    with factory() as db:
        caller = resolve_credential(db, 'Bearer ' + os.environ['CHATBI_API_KEY']).user(USER.user)
        for model in (ChatBIConversation, ChatBIMessage, ChatBIResult):
            db.query(model).filter_by(owner=USER.owner).update({'owner': caller.owner})
        db.commit()
    app = FastAPI()
    app.include_router(router)
    def database():
        with factory() as db:
            yield db
    app.dependency_overrides[get_db] = database
    import os
    headers = {'Authorization': 'Bearer ' + os.environ['CHATBI_API_KEY']}
    with TestClient(app) as client:
        response = client.post('/api/service/exports/ppt', headers=headers,
                               json={'user': USER.user, 'conversation_id': events[0]['conversation_id']})
        assert response.status_code == 202, response.text
        state = response.json()
        assert len(state['files']) == 2 and state['file_id'] is None
        poll = client.get(f"/api/service/export-tasks/{state['task_id']}", headers=headers, params={'user': USER.user})
        assert poll.status_code == 200 and len(poll.json()['files']) == 2
        denied = client.get(f"/api/service/export-tasks/{state['task_id']}", headers=headers, params={'user': OTHER.user})
        assert denied.status_code == 404


def test_second_request_worker_renews_its_lease_when_generation_starts(factory, monkeypatch):
    import time
    from fastapi import BackgroundTasks
    events, _ = analysis(factory)
    monkeypatch.setenv('CHATBI_EXPORT_REQUEST_WORKER_ENABLED', 'true')
    monkeypatch.setattr(exports, 'SessionLocal', factory)
    with factory() as db:
        job = exports.create_export(db, 'ppt', PPTRequest(user=USER.user, conversation_id=events[0]['conversation_id']),
                                    USER, background_tasks=BackgroundTasks())
        child_id = job.payload['child_task_ids'][1]
        child = db.get(ChatBIExport, child_id)
        child.lease_until = int(time.time()) + 1
        db.commit()
    calls = []
    async def render(identifier):
        with factory() as db:
            child = db.get(ChatBIExport, identifier)
            assert child.lease_until >= int(time.time()) + 890
            calls.append(identifier)
    monkeypatch.setattr(exports, 'process_export', render)
    asyncio.run(exports.process_requested_export(child_id))
    assert calls == [child_id]
