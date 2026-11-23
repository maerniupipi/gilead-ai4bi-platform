"""Admin model selection and queued AI PPT jobs, using isolated data and a fake LLM."""
import asyncio
import json

import pytest

from app.models.chatbi import ChatBIExport, ChatBIPPTModelConfig
from app.models.model_provider import ModelProvider
from app.models.user import User
from app.routers.chatbi.ppt_model import router
from app.services.chatbi import exports
from app.services.chatbi.config import APIError
from app.services.chatbi.ppt_settings import resolve_ppt_model
from app.services.chat.service import ChatService
from test_chatbi_credentials import api, ask, make_key, headers, ADMIN, USER

PATH = "/api/chatbi/ppt-model"


@pytest.fixture
def managed(api, monkeypatch):
    monkeypatch.delenv("CHATBI_SUMMARY_PROVIDER_ID", raising=False)
    monkeypatch.delenv("CHATBI_SUMMARY_MODEL", raising=False)
    api.client.app.include_router(router)
    with api.factory() as db:
        ModelProvider.__table__.create(db.get_bind())
        for pid, active, protocol, secret, models in [
            (1, True, "openai", "private-model-secret", '["alpha","beta"]'),
            (2, False, "openai", "disabled-secret", '["alpha"]'),
            (3, True, "openai", "", '["alpha"]'),
            (4, True, "anthropic", "other-secret", '["alpha"]'),
            (5, True, "openai", "bad-models-secret", '{bad json'),
        ]:
            db.add(ModelProvider(id=pid, name=f"模型供应商 {pid}", is_active=active, protocol=protocol,
                api_key=secret, models=models, base_url="https://model.example.test/v1"))
        db.commit()
    return api


def save(managed, model="alpha"):
    response = managed.client.put(PATH, headers=ADMIN, json={"provider_id": 1, "model": model})
    assert response.status_code == 200, response.text
    return response.json()["data"]


def test_options_only_expose_usable_existing_language_models(managed):
    response = managed.client.get(PATH + "/options", headers=ADMIN)
    assert response.status_code == 200
    assert response.json()["data"] == [{"id": 1, "name": "模型供应商 1", "models": ["alpha", "beta"]}]
    assert "secret" not in response.text and "api_key" not in response.text and "base_url" not in response.text
    assert not managed.client.get(PATH, headers=ADMIN).json()["data"]["configured"]


def test_saved_model_survives_new_sessions_and_wins_over_environment(managed, monkeypatch):
    selected = save(managed, "beta")
    assert selected["available"] and selected["source"] == "platform"
    with managed.factory() as db:
        row = db.get(ChatBIPPTModelConfig, 1)
        assert row.updated_by == 1 and row.model == "beta"
    monkeypatch.setenv("CHATBI_SUMMARY_PROVIDER_ID", "999")
    monkeypatch.setenv("CHATBI_SUMMARY_MODEL", "stale-env-model")
    with managed.factory() as db:
        assert resolve_ppt_model(db) == {"provider_id": 1, "model": "beta"}
    assert managed.client.get(PATH, headers=ADMIN).json()["data"]["model"] == "beta"


@pytest.mark.parametrize("body", [
    {"provider_id": 999, "model": "alpha"}, {"provider_id": 2, "model": "alpha"},
    {"provider_id": 3, "model": "alpha"}, {"provider_id": 4, "model": "alpha"},
    {"provider_id": 1, "model": "invented"}, {"provider_id": 1, "model": ""},
    {"provider_id": 1, "model": "alpha", "api_key": "browser-key"},
    {"provider_id": "1", "model": "alpha"},
])
def test_invalid_or_unavailable_selection_is_rejected_without_saving(managed, body):
    response = managed.client.put(PATH, headers=ADMIN, json=body)
    assert response.status_code == 400, response.text
    with managed.factory() as db:
        assert db.get(ChatBIPPTModelConfig, 1) is None


def test_removed_or_disabled_provider_is_visible_as_unavailable(managed):
    save(managed)
    with managed.factory() as db:
        db.get(ModelProvider, 1).is_active = False
        db.commit()
    state = managed.client.get(PATH, headers=ADMIN).json()["data"]
    assert state["configured"] and not state["available"] and "停用" in state["reason"]
    with managed.factory() as db:
        db.delete(db.get(ModelProvider, 1)); db.commit()
        with pytest.raises(APIError) as error:
            resolve_ppt_model(db)
        assert error.value.status == 503 and error.value.code == "summary_model_unavailable"


def test_legacy_environment_is_readable_but_must_also_reference_a_valid_model(managed, monkeypatch):
    monkeypatch.setenv("CHATBI_SUMMARY_PROVIDER_ID", "1")
    monkeypatch.setenv("CHATBI_SUMMARY_MODEL", "alpha")
    state = managed.client.get(PATH, headers=ADMIN).json()["data"]
    assert state["source"] == "environment" and state["available"]
    monkeypatch.setenv("CHATBI_SUMMARY_MODEL", "old-unregistered-model")
    state = managed.client.get(PATH, headers=ADMIN).json()["data"]
    assert not state["available"]
    with managed.factory() as db:
        with pytest.raises(APIError): resolve_ppt_model(db)


@pytest.mark.parametrize("method,path", [("GET", PATH), ("GET", PATH + "/options"), ("PUT", PATH)])
def test_normal_platform_identity_can_manage_models_without_second_cookie(managed, method, path):
    _, secret = make_key(managed)
    managed.client.cookies.clear()
    response = managed.client.request(method, path, headers={**ADMIN, **headers(secret)}, json={"provider_id": 1, "model": "alpha"})
    assert response.status_code == 200


def test_member_role_can_save_model_configuration(managed):
    with managed.factory() as db:
        db.get(User, 1).system_role = "member"; db.commit()
    assert managed.client.put(PATH, headers=ADMIN, json={"provider_id": 1, "model": "alpha"}).status_code == 200


def test_queued_export_uses_submitted_model_and_idempotent_retry_keeps_it(managed, monkeypatch):
    _, key = make_key(managed)
    answer = ask(managed, key)
    save(managed, "alpha")
    body = {"user": USER, "conversation_id": answer["conversation_id"], "summaryType": "AI_SUMMARY", "idempotency_key": "first-click"}
    first = managed.client.post("/api/service/exports/ppt", headers=headers(key), json=body)
    assert first.status_code == 202, first.text
    task_id = first.json()["task_id"]
    save(managed, "beta")
    repeated = managed.client.post("/api/service/exports/ppt", headers=headers(key), json=body)
    assert repeated.json()["task_id"] == task_id
    second = managed.client.post("/api/service/exports/ppt", headers=headers(key), json={**body, "idempotency_key": "second-click"})
    with managed.factory() as db:
        assert db.get(ChatBIExport, task_id).payload["summary_model"]["model"] == "alpha"
        assert db.get(ChatBIExport, second.json()["task_id"]).payload["summary_model"]["model"] == "beta"
    calls = []
    async def complete(db, **kwargs):
        calls.append({"provider_id": kwargs["provider_id"], "model": kwargs["model"]})
        return {"content": json.dumps({"agenda": ["总结"], "slides": [{"title": "总结", "insights": ["模拟回答只用于验证模型选择。"]}]})}
    monkeypatch.setattr(ChatService, "chat_completion_openai", complete)
    asyncio.run(exports.process_export(task_id, factory=managed.factory))
    assert calls == [{"provider_id": 1, "model": "alpha"}]
    with managed.factory() as db:
        job = db.get(ChatBIExport, task_id)
        assert job.status == "succeeded" and exports.file_path(job).is_file()


def test_plain_ppt_does_not_require_ai_model_but_ai_ppt_does(managed):
    _, key = make_key(managed)
    answer = ask(managed, key)
    body = {"user": USER, "conversation_id": answer["conversation_id"]}
    assert managed.client.post("/api/service/exports/ppt", headers=headers(key), json={**body, "summaryType": "FULL_SUMMARY"}).status_code == 202
    response = managed.client.post("/api/service/exports/ppt", headers=headers(key), json={**body, "summaryType": "AI_SUMMARY"})
    assert response.status_code == 503 and response.json()["code"] == "summary_not_configured"


def test_request_worker_reserves_only_its_job_and_does_not_repeat_idempotent_requests(managed, monkeypatch):
    monkeypatch.setenv("CHATBI_EXPORT_REQUEST_WORKER_ENABLED", "true")
    _, key = make_key(managed)
    answer = ask(managed, key)
    calls = []
    async def process(job_id):
        with managed.factory() as db:
            job = db.get(ChatBIExport, job_id)
            assert job.status == "running" and job.started_at and job.lease_until
            assert db.query(ChatBIExport).filter_by(status="pending").count() == 0
        calls.append(job_id)
    monkeypatch.setattr(exports, "process_requested_export", process)
    body = {"user": USER, "conversation_id": answer["conversation_id"], "summaryType": "FULL_SUMMARY", "idempotency_key": "local-click"}
    first = managed.client.post("/api/service/exports/ppt", headers=headers(key), json=body)
    assert first.status_code == 202 and first.json()["status"] == "running"
    second = managed.client.post("/api/service/exports/ppt", headers=headers(key), json=body)
    assert second.json()["task_id"] == first.json()["task_id"]
    assert calls == [first.json()["task_id"]]
