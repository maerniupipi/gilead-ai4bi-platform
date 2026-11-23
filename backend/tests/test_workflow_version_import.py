"""Version imports commit the graph and version together without changing history."""
from copy import deepcopy

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.agent_app import AgentApp, AgentAppVersion
from app.models.agent_app_folder import AgentAppFolder
from app.schemas.agent_app import AgentVersionCreate
from app.services.agent_app import service


GRAPH = {"nodes": [{"id": "start", "data": {"kind": "start", "label": "开始"}},
                   {"id": "out", "data": {"kind": "output", "label": "输出",
                    "output_config": {"content_template": "导入版本"}}}],
         "edges": [{"id": "e", "source": "start", "target": "out"}]}


@pytest.fixture
def database(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'versions.db'}")
    Base.metadata.create_all(engine, tables=[AgentAppFolder.__table__, AgentApp.__table__, AgentAppVersion.__table__])
    factory = sessionmaker(engine)
    with factory() as db:
        db.add(AgentAppFolder(id=1, name="Test"))
        db.add(AgentApp(id=1, folder_id=1, name="目标工作流", api_token="unchanged"))
        db.add(AgentAppVersion(id=1, agent_app_id=1, name="v1", status="online", is_output=True,
                              workflow_rev=7, workflow_json={"nodes": [], "edges": []}))
        db.commit()
    undo = {}
    monkeypatch.setattr(service, "workflow_undo_set", lambda aid, vid, value: undo.update({(aid, vid): deepcopy(value)}))
    yield factory, undo
    engine.dispose()


def test_import_creates_editable_version_with_graph_and_preserves_current_version(database):
    factory, undo = database
    payload = {"name": " v2 ", "workflow": deepcopy(GRAPH),
               "undo_stack": {"states": [GRAPH], "index": 0}, "workflow_rev": 99,
               "status": "online", "is_output": True, "app": {"id": 88, "name": "来源"}}
    with factory() as db:
        app = service.create_version_service(db, 1, AgentVersionCreate.model_validate(payload))
        detail = service.to_detail(app)
        assert len(detail.versions) == 2
        new_id = next(v.id for v in detail.versions if v.name == "v2")
    with factory() as db:
        new = db.get(AgentAppVersion, new_id)
        assert new.agent_app_id == 1
        assert new.workflow_json == GRAPH
        assert new.workflow_rev == 0
        assert new.status == "designing"
        assert new.is_output is False
        assert new.mode == "导入"
        old = db.get(AgentAppVersion, 1)
        assert (old.status, old.is_output, old.workflow_rev) == ("online", True, 7)
        assert old.workflow_json == {"nodes": [], "edges": []}
        app = db.get(AgentApp, 1)
        assert (app.name, app.api_token) == ("目标工作流", "unchanged")
    assert undo == {(1, new_id): {"states": [GRAPH], "index": 0}}
    assert payload["workflow"] == GRAPH


@pytest.mark.parametrize("fields,match", [
    ({"name": "v1", "workflow": GRAPH}, "已存在"),
    ({"name": " ", "workflow": GRAPH}, "不能为空"),
    ({"name": "v2", "workflow": GRAPH, "clone_from_version_id": 1}, "同时"),
])
def test_invalid_import_is_rejected_before_any_new_version(database, fields, match):
    factory, undo = database
    with factory() as db, pytest.raises(HTTPException, match=match):
        service.create_version_service(db, 1, AgentVersionCreate.model_validate(fields))
    with factory() as db:
        assert db.query(AgentAppVersion).count() == 1
    assert undo == {}


@pytest.mark.parametrize("workflow", [None, [], {"nodes": None, "edges": []},
    {"nodes": [], "edges": "invalid"}, {"nodes": [None], "edges": []},
    {"nodes": [], "edges": [7]}, {"nodes": []}])
def test_import_schema_rejects_invalid_graph_shapes(workflow):
    if workflow is None:
        # Absent workflow still means the original, intentional blank-version action.
        assert AgentVersionCreate(name="v2").model_dump().get("workflow") is None
        return
    with pytest.raises(ValidationError):
        AgentVersionCreate.model_validate({"name": "v2", "workflow": workflow})


def test_database_failure_leaves_no_version_graph_or_undo(database, monkeypatch):
    factory, undo = database
    with factory() as db:
        def fail_commit():
            db.flush()
            raise RuntimeError("database unavailable")
        monkeypatch.setattr(db, "commit", fail_commit)
        with pytest.raises(RuntimeError, match="database unavailable"):
            service.create_version_service(db, 1, AgentVersionCreate.model_validate({
                "name": "v2", "workflow": GRAPH, "undo_stack": {"states": [GRAPH], "index": 0}}))
        db.rollback()
    with factory() as db:
        assert db.query(AgentAppVersion).count() == 1
        assert db.get(AgentAppVersion, 1).workflow_rev == 7
    assert undo == {}


def test_undo_cache_failure_does_not_report_a_committed_import_as_failed(database, monkeypatch):
    factory, _ = database
    def unavailable(*args):
        raise RuntimeError("cache unavailable")
    monkeypatch.setattr(service, "workflow_undo_set", unavailable)
    with factory() as db:
        app = service.create_version_service(db, 1, AgentVersionCreate.model_validate({
            "name": "v2", "workflow": GRAPH, "undo_stack": {"states": [GRAPH], "index": 0}}))
        assert len(app.versions) == 2
    with factory() as db:
        assert db.query(AgentAppVersion).filter_by(name="v2").one().workflow_json == GRAPH


def test_original_blank_and_clone_creation_still_work(database):
    factory, _ = database
    with factory() as db:
        service.create_version_service(db, 1, AgentVersionCreate(name="blank"))
    with factory() as db:
        app = service.create_version_service(db, 1, AgentVersionCreate(name="clone", clone_from_version_id=1))
        versions = {v.name: v for v in app.versions}
        assert versions["blank"].workflow_json is None
        assert versions["clone"].workflow_json == {"nodes": [], "edges": []}
        assert versions["v1"].is_output
        assert not versions["clone"].is_output
