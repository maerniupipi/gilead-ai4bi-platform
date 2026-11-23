"""Service auth/error contract; no business database or external model."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.exceptions import register_exception_handlers
from app.routers.chatbi.router import router
from app.core.database import Base, get_db
from app.models.chatbi import ChatBIAPIKey

KEYS = {env: f"app-{env}-" + char * 43 for env, char in (("uat", "u"), ("prod", "p"))}


@pytest.fixture
def api(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "dev")
    monkeypatch.setenv("CHATBI_ENV", "uat")
    monkeypatch.setenv("CHATBI_API_KEY", KEYS["uat"])
    monkeypatch.setenv("CHATBI_API_ENABLED", "true")
    monkeypatch.setenv("CHATBI_AUTOBI_PROJECT_ID", "1")
    engine = create_engine(f"sqlite:///{tmp_path / 'auth.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine, tables=[ChatBIAPIKey.__table__])
    factory = sessionmaker(engine, expire_on_commit=False)
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router)
    def database_session():
        with factory() as db:
            yield db
    app.dependency_overrides[get_db] = database_session

    @app.get("/api/service/test-failure")
    def failure():
        raise RuntimeError("private database password must not leak")

    @app.get("/api/service/test-database")
    def database():
        raise OperationalError("SELECT secret", {}, Exception("private password"))

    @app.get("/api/test-failure")
    def management_failure():
        raise RuntimeError("private")

    with TestClient(app, raise_server_exceptions=False) as client:
        yield client
    engine.dispose()


@pytest.mark.parametrize("environment", ["uat", "prod"])
def test_environment_isolation_and_info(api, monkeypatch, environment):
    monkeypatch.setenv("APP_ENV", environment)
    monkeypatch.setenv("CHATBI_ENV", environment)
    monkeypatch.setenv("CHATBI_API_KEY", KEYS[environment])
    response = api.get("/api/service/info", headers={"Authorization": "Bearer " + KEYS[environment]})
    assert response.status_code == 200
    assert response.json() == {"name": "AI4BI Platform", "description": "数据问答与 PPT、XLSX 导出",
                               "tags": ["ChatBI"], "mode": "advanced-chat", "author_name": "ChatBI"}
    assert KEYS[environment] not in response.text
    other = "prod" if environment == "uat" else "uat"
    response = api.get("/api/service/info", headers={"Authorization": "Bearer " + KEYS[other]})
    assert response.status_code == 401
    assert response.json()["code"] == "unauthorized"


@pytest.mark.parametrize("header", [None, "", "Bearer", "Basic abc", "Bearer wrong", "Bearer " + KEYS["uat"] + "extra"])
def test_invalid_auth_is_service_401(api, header):
    response = api.get("/api/service/info", headers={} if header is None else {"Authorization": header})
    assert response.status_code == 401
    assert set(response.json()) == {"status", "code", "message"}
    assert response.json()["status"] == 401 and response.json()["code"] == "unauthorized"


def test_service_case_insensitive_bearer_scheme(api):
    assert api.get("/api/service/info", headers={"Authorization": "bearer " + KEYS["uat"]}).status_code == 200


def test_service_disabled_is_403(api, monkeypatch):
    monkeypatch.setenv("CHATBI_API_ENABLED", "false")
    response = api.get("/api/service/info", headers={"Authorization": "Bearer " + KEYS["uat"]})
    assert response.status_code == 403
    assert response.json()["code"] == "forbidden"


@pytest.mark.parametrize("config", [
    {"CHATBI_API_KEY": ""}, {"CHATBI_API_KEY": "weak"}, {"CHATBI_API_KEY": KEYS["prod"]},
    {"CHATBI_ENV": "unknown"}, {"APP_ENV": "prod", "CHATBI_ENV": "uat"},
])
def test_bad_deployment_fails_closed(api, monkeypatch, config):
    for name, value in config.items():
        monkeypatch.setenv(name, value)
    response = api.get("/api/service/info", headers={"Authorization": "Bearer " + KEYS["uat"]})
    assert response.status_code == 503
    assert response.json()["code"] == "not_configured"


@pytest.mark.parametrize("method,path,status,code", [
    ("GET", "/api/service/nonexistent", 404, "not_found"),
    ("POST", "/api/service/info", 405, "method_not_allowed"),
    ("GET", "/api/service/test-failure", 500, "internal_server_error"),
    ("GET", "/api/service/test-database", 503, "service_unavailable"),
])
def test_framework_errors_keep_service_envelope(api, method, path, status, code):
    response = api.request(method, path)
    assert response.status_code == status
    assert set(response.json()) == {"status", "code", "message"}
    assert response.json()["status"] == status and response.json()["code"] == code
    assert "private" not in response.text and "password" not in response.text


def test_management_api_keeps_existing_envelope(api):
    response = api.get("/api/test-failure")
    assert response.status_code == 500
    assert response.json() == {"code": "INTERNAL_ERROR", "message": "服务器内部错误", "data": None}
