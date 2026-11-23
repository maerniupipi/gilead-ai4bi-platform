"""Lab configuration transfer uses isolated SQLite storage, without live services."""
import json
from copy import deepcopy

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.models.autobi_folder import AutobiFolder
from app.models.autobi_project import AutobiProject
from app.models.user import User
from app.routers.autobi.router import router
from app.services.autobi.lab_config_merge import merge_lab_config


@compiles(LONGTEXT, "sqlite")
def sqlite_longtext(type_, compiler, **kwargs):
    return "TEXT"


MODEL_KEYS = ("knowledge_rewrite", "nl2sql", "ner_retrieval", "bi_summary", "chart_drawing")
CONFIG = {
    "knowledge_base_id": 999,
    "model_bindings": {key: {"provider_id": 88, "model_name": "source-model"} for key in MODEL_KEYS},
    "disclaimer_acceptance": {"rewrite": True, "sql": True, "chart": False},
    "future_setting": {"preserve": [1, False, None]},
    "request": {
        "messages": [{"role": "user", "content": "保留原始内容"}], "stream": True,
        "advanced_config": {
            "nl2sql_config": {"prompt": "自定义 SQL {{region}}", "temperature": 0.23, "max_tokens": 1000},
            "knowledge_rewrite_config": {"enable": False, "prompt": "知识改写"},
            "ner_retrieval_config": {"enable": True, "top_k": 4},
            "sql_permission_rewrite_config": {"enable": True, "target_app_id": 5, "target_version_id": 6},
            "multi_rewrite_config": {"enable": False, "prompt": "隐藏配置"},
            "chart_drawing_config": {"enable": False},
        },
    },
}


def export_payload():
    return {"format": "chat-bi-lab-export", "formatVersion": 1, "exportedAt": "2026-10-27T00:00:00Z",
            "project": {"name": "来源实验室", "description": "配置迁移"}, "config_json": deepcopy(CONFIG)}


@pytest.fixture
def api(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'labs.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine, tables=[AutobiFolder.__table__, AutobiProject.__table__, User.__table__])
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as db:
        db.add_all([User(id=1, username="admin", system_role="super_admin", is_active=True),
                    User(id=2, username="visitor", system_role="visitor", is_active=True),
                    AutobiFolder(id=1, name="默认", is_system=True, space_id=1),
                    AutobiFolder(id=2, name="目标", space_id=1), AutobiFolder(id=3, name="其他空间", space_id=2)])
        db.add(AutobiProject(id=1, name="来源实验室", description="配置迁移", folder_id=1, space_id=1,
                            knowledge_base_id=999, config_json=json.dumps(CONFIG),
                            api_access_id="Source1234", share_token="private-source-share"))
        db.commit()
    app = FastAPI()
    app.include_router(router)
    def database():
        with factory() as db:
            yield db
    app.dependency_overrides[get_db] = database
    with TestClient(app, headers={"X-User-Id": "1"}) as client:
        yield client, factory
    engine.dispose()


def assert_portable(config):
    expected = deepcopy(CONFIG)
    expected["knowledge_base_id"] = None
    expected["model_bindings"] = {key: {"provider_id": None, "model_name": ""} for key in MODEL_KEYS}
    assert config == expected
    merged = merge_lab_config(config)
    assert merged["knowledge_base_id"] is None
    assert all(not binding["provider_id"] and not binding["model_name"] for binding in merged["model_bindings"].values())


def test_export_preserves_settings_clears_bindings_and_excludes_project_identifiers(api):
    client, factory = api
    response = client.get("/api/autobi/projects/1/export", params={"space_id": 1})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["format"] == "chat-bi-lab-export" and payload["formatVersion"] == 1
    assert payload["project"] == {"name": "来源实验室", "description": "配置迁移"}
    assert_portable(payload["config_json"])
    assert "Source1234" not in response.text and "private-source-share" not in response.text
    with factory() as db:
        assert json.loads(db.get(AutobiProject, 1).config_json) == CONFIG


def test_import_creates_complete_project_and_regenerates_api_id_in_one_request(api):
    client, factory = api
    payload = export_payload()
    payload["project"].update(id=1, api_access_id="Source1234", share_token="private-source-share")
    response = client.post("/api/autobi/projects/import?space_id=1", json={"payload": payload, "folder_id": 2, "name": " 导入的实验室 "})
    assert response.status_code == 200, response.text
    imported = response.json()
    assert imported["name"] == "导入的实验室" and imported["description"] == "配置迁移"
    assert imported["folder_id"] == 2 and imported["id"] != 1
    assert imported["knowledge_base_id"] is None
    assert len(imported["api_access_id"]) == 10 and imported["api_access_id"] != "Source1234"
    assert_portable(imported["config_json"])
    assert payload["config_json"] == CONFIG
    with factory() as db:
        assert db.get(AutobiProject, imported["id"]).share_token is None
        assert db.get(AutobiProject, imported["id"]).space_id == 1
        assert json.loads(db.get(AutobiProject, 1).config_json) == CONFIG
        assert db.query(AutobiProject).count() == 2


def test_exported_file_roundtrips_and_default_folder_and_name_work(api):
    client, _ = api
    payload = client.get("/api/autobi/projects/1/export?space_id=1").json()
    response = client.post("/api/autobi/projects/import?space_id=1", json={"payload": payload})
    assert response.status_code == 200, response.text
    assert response.json()["folder_id"] == 1 and response.json()["name"] == "来源实验室"
    assert_portable(response.json()["config_json"])


@pytest.mark.parametrize("change", [
    {"format": "chat-bi-agent-export"}, {"formatVersion": 2}, {"project": None}, {"config_json": []},
    {"config_json": {}}, {"config_json": {"request": []}},
    {"config_json": {"request": {"advanced_config": []}}},
    {"config_json": {"request": {"messages": "invalid"}}},
    {"config_json": {"request": {}, "model_bindings": []}},
    {"config_json": {"request": {}, "model_bindings": {"nl2sql": "invalid"}}},
])
def test_invalid_import_does_not_create_any_project(api, change):
    client, factory = api
    response = client.post("/api/autobi/projects/import?space_id=1", json={"payload": {**export_payload(), **change}, "folder_id": 2})
    assert response.status_code in (400, 422), response.text
    with factory() as db:
        assert db.query(AutobiProject).count() == 1


def test_transfer_preserves_space_scope_and_allows_all_logged_in_roles(api):
    client, factory = api
    assert client.get("/api/autobi/projects/1/export?space_id=2").status_code == 404
    assert client.post("/api/autobi/projects/import?space_id=1", json={"payload": export_payload(), "folder_id": 3}).status_code == 404
    assert client.post("/api/autobi/projects/import?space_id=1", headers={"X-User-Id": "2"}, json={"payload": export_payload()}).status_code == 200
    client.headers.clear()
    assert client.post("/api/autobi/projects/import?space_id=1", json={"payload": export_payload()}).status_code == 401
    with factory() as db:
        assert db.query(AutobiProject).count() == 2


def test_failed_import_rolls_back_project_with_configuration(api, monkeypatch):
    from app.schemas.autobi import AutobiProjectImport
    from app.services.autobi.project_transfer import import_autobi_project_service
    _, factory = api
    with factory() as db:
        def unavailable():
            db.flush()
            raise RuntimeError("database unavailable")
        monkeypatch.setattr(db, "commit", unavailable)
        with pytest.raises(RuntimeError, match="database unavailable"):
            import_autobi_project_service(db, AutobiProjectImport(payload=export_payload(), folder_id=2), 1)
        assert not db.new
    with factory() as db:
        assert db.query(AutobiProject).count() == 1
