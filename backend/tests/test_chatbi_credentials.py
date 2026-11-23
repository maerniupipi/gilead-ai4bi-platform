"""Key bindings over real routes/storage, with an explicitly fake analysis engine."""
import asyncio
import importlib
import json
import hashlib
from io import BytesIO
from types import SimpleNamespace
from uuid import uuid4
from zipfile import ZipFile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.core.exceptions import register_exception_handlers
from app.core import middleware
from app.models.agent_app import AgentApp, AgentAppVersion
from app.models.agent_app_folder import AgentAppFolder
from app.models.chatbi import TABLES, ChatBIAPIKey, ChatBIMessage
from app.models.user import User
from app.routers.chatbi.router import router
from app.routers.chatbi.admin import router as admin_router
from app.routers.user.router import router as user_router
from app.services.chatbi import chat, exports
from app.services.chatbi.config import identity
from app.services.chatbi.config import APIError

ADMIN = {"X-User-Id": "1"}
USER = "admin123"
LEGACY_KEY = "app-uat-" + "l" * 43
ADMIN_PATH = "/api/chatbi/keys"


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "dev")
    monkeypatch.setenv("CHATBI_ENV", "uat")
    monkeypatch.setenv("CHATBI_API_ENABLED", "true")
    monkeypatch.setenv("CHATBI_EXPORT_REQUEST_WORKER_ENABLED", "false")
    monkeypatch.setenv("CHATBI_API_KEY", LEGACY_KEY)
    monkeypatch.setenv("CHATBI_AUTOBI_PROJECT_ID", "1")
    monkeypatch.setenv("CHATBI_STORAGE_DIR", str(tmp_path / "exports"))
    monkeypatch.setenv("CHATBI_PUBLIC_BASE_URL", "http://testserver")
    monkeypatch.setenv("CHATBI_DOWNLOAD_SIGNING_KEY", "isolated-test-signing-secret")
    monkeypatch.setattr(middleware, "_audit_db_enabled", False)
    engine = create_engine(f"sqlite:///{tmp_path / 'keys.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine, tables=TABLES + [User.__table__, AgentAppFolder.__table__, AgentApp.__table__, AgentAppVersion.__table__])
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as db:
        db.add_all([User(id=1, username="admin", system_role="super_admin", is_active=True, password_hash=hashlib.sha256(b"test-admin-password").hexdigest()),
                    User(id=2, username="member", system_role="member", is_active=True),
                    AgentAppFolder(id=1, name="测试工作流"),
                    AgentApp(id=1, folder_id=1, name="工作流 A"), AgentApp(id=2, folder_id=1, name="工作流 B")])
        workflow = {"nodes": [{"id": "start", "data": {"kind": "start"}}, {"id": "out", "data": {"kind": "output"}}],
                    "edges": [{"source": "start", "target": "out"}]}
        db.add_all([AgentAppVersion(id=11, agent_app_id=1, name="v1", status="published", workflow_rev=3, workflow_json=workflow),
                    AgentAppVersion(id=12, agent_app_id=1, name="v2", status="online", workflow_rev=4, is_output=True, workflow_json=workflow),
                    AgentAppVersion(id=13, agent_app_id=1, name="草稿", status="designing", workflow_rev=1, workflow_json=workflow),
                    AgentAppVersion(id=21, agent_app_id=2, name="v1", status="published", workflow_rev=7, workflow_json=workflow)])
        db.commit()
    calls = []
    async def fake_analysis(db, runtime, query, inputs, conversation_id, history, user):
        calls.append({"runtime": runtime, "history": history, "user": user})
        yield {"type": "text", "content": "模拟销售数据"}
        yield {"type": "data_citations", "features": {"data_citations": [{"id": 1, "query": "区域销售",
            "columns": [{"key": "city", "name": "城市"}, {"key": "sales", "name": "销售额"}],
            "data": [{"city": "上海", "sales": 100}], "total_count": 1}]}}
    monkeypatch.setattr(chat, "run_analysis", fake_analysis)
    monkeypatch.setattr(chat, "SessionLocal", factory)
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router); app.include_router(admin_router)
    app.include_router(user_router)
    app.add_middleware(middleware.ResponseEnvelopeMiddleware)
    def session():
        with factory() as db:
            yield db
    app.dependency_overrides[get_db] = session
    with TestClient(app) as client:
        login = client.post("/api/users/login", json={"username": "admin", "password": "test-admin-password"})
        assert login.status_code == 200
        assert "chatbi_key_admin=" not in login.headers.get("set-cookie", "")
        yield SimpleNamespace(client=client, factory=factory, calls=calls)
    engine.dispose()


def make_key(api, environment="uat", workflow_id=1, version_id=11, **extra):
    response = api.client.post(ADMIN_PATH, headers=ADMIN, json={"name": "platform client " + environment,
        "environment": environment, "workflow_id": workflow_id, "version_id": version_id, **extra})
    assert response.status_code == 201, response.text
    data = response.json()["data"]
    return data["key"], data["api_key"]


def headers(key):
    return {"Authorization": "Bearer " + key}


def ask(api, key, conversation_id=None):
    r = api.client.post("/api/service/chat-messages", headers=headers(key), json={"user": USER, "query": "上海销售额？",
        "inputs": {}, "response_mode": "streaming", "conversation_id": conversation_id})
    assert r.status_code == 200, r.text
    events = [json.loads(line[6:]) for line in r.text.splitlines() if line.startswith("data: ")]
    assert events[-1]["data"]["status"] == "succeeded"
    return {**events[0], "data_ref": next(e["data"]["outputs"]["data_ref"] for e in events
        if e["event"] == "node_finished" and e["data"]["node_type"] == "table")}


def test_key_pins_specific_version_and_platform_assembles_history(api):
    row, key = make_key(api)
    first = ask(api, key)
    ask(api, key, first["conversation_id"])
    assert [call["runtime"] for call in api.calls] == ["agent:1:11:3", "agent:1:11:3"]
    assert api.calls[1]["history"] == [{"role": "user", "content": "上海销售额？"}, {"role": "assistant", "content": "模拟销售数据"}]
    assert api.calls[0]["user"].user_id == "admin123"
    with api.factory() as db:
        stored = db.get(ChatBIAPIKey, row["id"])
        assert stored.key_hash != key and key not in repr(stored.__dict__)
    listed = api.client.get(ADMIN_PATH, headers=ADMIN)
    assert key not in listed.text and "key_hash" not in listed.text
    assert next(item for item in listed.json()["data"] if item["id"] == row["id"])["version_id"] == 11


@pytest.mark.parametrize("path,method", [
    ("/api/service/info", "GET"), ("/api/service/chat-messages", "POST"),
    ("/api/service/chat-messages/11111111-1111-4111-8111-111111111111/stop", "POST"),
    ("/api/service/export-tasks/11111111-1111-4111-8111-111111111111?user=x", "GET"),
    ("/api/service/files/11111111-1111-4111-8111-111111111111/download-url?user=x", "GET"),
])
def test_every_business_endpoint_rejects_disabled_key(api, path, method):
    row, key = make_key(api)
    assert api.client.get("/api/service/info", headers=headers(key)).status_code == 200
    assert api.client.patch(f"{ADMIN_PATH}/{row['id']}/enabled", headers=ADMIN, json={"enabled": False}).status_code == 200
    response = api.client.request(method, path, headers=headers(key), json={})
    assert response.status_code == 403 and response.json()["code"] == "forbidden"


def test_same_user_id_isolated_between_keys_for_chat_stop_results_exports_files(api):
    _, key = make_key(api)
    _, other = make_key(api)
    first = ask(api, key)
    r = api.client.post("/api/service/chat-messages", headers=headers(other), json={"user": USER, "query": "追问", "conversation_id": first["conversation_id"]})
    assert r.status_code == 404
    assert api.client.post(f"/api/service/chat-messages/{first['task_id']}/stop", headers=headers(other), json={"user": USER}).status_code == 404
    for kind in ("ppt", "xlsx"):
        body = {"user": USER, "conversation_id": first["conversation_id"]}
        if kind == 'ppt': body['summaryType'] = 'FULL_SUMMARY'
        if kind == "xlsx": body.update(message_id=first["message_id"], data_ref=first["data_ref"])
        assert api.client.post(f"/api/service/exports/{kind}", headers=headers(other), json=body).status_code == 404
        accepted = api.client.post(f"/api/service/exports/{kind}", headers=headers(key), json=body)
        assert accepted.status_code == 202
        task = accepted.json()
        assert api.client.get(f"/api/service/export-tasks/{task['task_id']}", headers=headers(other), params={"user": USER}).status_code == 404
        assert api.client.get(f"/api/service/files/{task['file_id']}/download-url", headers=headers(other), params={"user": USER}).status_code == 404
        asyncio.run(exports.process_export(task["task_id"], factory=api.factory))
        link = api.client.get(f"/api/service/files/{task['file_id']}/download-url", headers=headers(key), params={"user": USER})
        assert link.status_code == 200
        file = api.client.get(link.json()["url"])  # Browser download intentionally carries no service Key.
        assert file.status_code == 200
        with ZipFile(BytesIO(file.content)) as archive:
            names = archive.namelist()
            name = next(n for n in names if n == "xl/worksheets/sheet1.xml" or n == "ppt/slides/slide1.xml")
            assert b"admin123" not in archive.read(name)


def test_rebinding_requires_new_chat_but_old_exports_remain_accessible(api):
    row, key = make_key(api)
    first = ask(api, key)
    changed = api.client.put(f"{ADMIN_PATH}/{row['id']}", headers=ADMIN, json={"name": "改用 v2", "workflow_id": 1, "version_id": 12})
    assert changed.status_code == 200
    r = api.client.post("/api/service/chat-messages", headers=headers(key), json={"user": USER, "query": "继续", "conversation_id": first["conversation_id"]})
    assert r.status_code == 409 and r.json()["code"] == "runtime_changed"
    ask(api, key)
    assert api.calls[-1]["runtime"] == "agent:1:12:4"
    assert api.client.post("/api/service/exports/ppt", headers=headers(key), json={"user": USER, "conversation_id": first["conversation_id"], "summaryType": "FULL_SUMMARY"}).status_code == 202


def test_changed_or_deleted_version_fails_closed_without_switching_to_output(api):
    _, key = make_key(api)
    with api.factory() as db:
        db.get(AgentAppVersion, 11).workflow_rev = 99
        db.commit()
    r = api.client.post("/api/service/chat-messages", headers=headers(key), json={"user": USER, "query": "销售"})
    assert r.status_code == 503 and r.json()["code"] == "workflow_unavailable"
    assert not api.calls


def test_pinned_runtime_reaches_the_exact_engine_version(api, monkeypatch):
    from app.services.chatbi.runtime import run_analysis
    from app.services.agent_app import workflow_engine
    seen = []
    async def engine(db, app_id, version_id, trusted, **kwargs):
        seen.append((app_id, version_id, trusted["user_id"], trusted["history_messages"]))
        yield 'data: {"status":"done","output":"ok"}\n\n'
    monkeypatch.setattr(workflow_engine, "run_agent_workflow_stream", engine)
    async def invoke(runtime):
        with api.factory() as db:
            return [event async for event in run_analysis(db, runtime, "question", {}, "cid", [{"role": "user", "content": "previous"}], identity(USER))]
    asyncio.run(invoke("agent:1:11:3"))
    assert seen == [(1, 11, "admin123", [{"role": "user", "content": "previous"}])]
    with pytest.raises(APIError) as error:
        asyncio.run(invoke("agent:1:11:999"))
    assert error.value.code == "workflow_unavailable"
    assert len(seen) == 1  # Never switched to the current output version 12.




def test_environment_isolation_and_managed_keys_without_env_secret(api, monkeypatch):
    _, uat = make_key(api)
    _, prod = make_key(api, environment="prod")
    assert api.client.get("/api/service/info", headers=headers(prod)).status_code == 401
    monkeypatch.delenv("CHATBI_API_KEY")
    assert api.client.get("/api/service/info", headers=headers(uat)).status_code == 200
    monkeypatch.setenv("CHATBI_ENV", "prod")
    assert api.client.get("/api/service/info", headers=headers(prod)).status_code == 200
    assert api.client.get("/api/service/info", headers=headers(uat)).status_code == 401


@pytest.mark.parametrize("body", [{"workflow_id": 1, "version_id": 13}, {"workflow_id": 2, "version_id": 11}, {"workflow_id": 1, "version_id": 999}])
def test_admin_rejects_drafts_and_mismatched_versions(api, body):
    r = api.client.post(ADMIN_PATH, headers=ADMIN, json={"name": "bad", "environment": "uat", **body})
    assert r.status_code == 400


def test_workflow_options_exclude_drafts_and_import_does_not_echo_key(api):
    options = api.client.get(ADMIN_PATH + "/workflow-options", headers=ADMIN).json()["data"]
    assert [v["id"] for v in options[0]["versions"]] == [11, 12]
    raw = "app-uat-" + "i" * 43
    row, returned = make_key(api, api_key=raw)
    assert returned is None
    assert api.client.get("/api/service/info", headers=headers(raw)).status_code == 200
    assert raw not in api.client.get(ADMIN_PATH, headers=ADMIN).text
    duplicate = api.client.post(ADMIN_PATH, headers=ADMIN, json={"name": "repeat", "environment": "uat", "workflow_id": 1, "version_id": 11, "api_key": raw})
    assert duplicate.status_code == 409


@pytest.mark.parametrize("admin_headers,status", [({}, 401), ({"X-User-Id": "bogus"}, 401)])
def test_management_uses_the_normal_platform_login(api, admin_headers, status):
    api.client.cookies.clear()
    assert api.client.get(ADMIN_PATH, headers=admin_headers).status_code == status
    assert api.client.post(ADMIN_PATH, headers=admin_headers, json={}).status_code == status


def test_inactive_admin_cannot_manage_keys(api):
    with api.factory() as db:
        db.get(User, 1).is_active = False; db.commit()
    assert api.client.get(ADMIN_PATH, headers=ADMIN).status_code == 403




def test_external_caller_cannot_override_binding_via_inputs_or_top_level(api, monkeypatch):
    _, key = make_key(api)
    monkeypatch.setenv("CHATBI_ALLOWED_INPUTS", '["workflow_id", "version_id"]')
    for params in ({"workflow_id": 2}, {"inputs": {"workflow_id": 2}}, {"inputs": {"version_id": 12}}):
        r = api.client.post("/api/service/chat-messages", headers=headers(key), json={"user": USER, "query": "销售", **params})
        assert r.status_code == 400
    assert not api.calls


def test_keys_are_redacted_from_real_audit_input_and_output(api, monkeypatch, caplog):
    audit = []
    monkeypatch.setattr(middleware, "_audit_db_enabled", True)
    monkeypatch.setattr(middleware, "_persist_audit_log", lambda **kwargs: audit.append(kwargs))
    monkeypatch.setattr(middleware, "_audit_executor", SimpleNamespace(submit=lambda fn: fn()))
    _, generated = make_key(api)
    imported = "app-uat-" + "x" * 43
    make_key(api, api_key=imported)
    invalid = api.client.post(ADMIN_PATH, headers=ADMIN, json={"api_key": imported, "extra": {"api_key": imported}})
    assert invalid.status_code == 400
    assert audit and generated not in repr(audit) and imported not in repr(audit)
    assert imported not in caplog.text and generated not in caplog.text
