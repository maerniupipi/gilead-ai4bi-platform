"""Workflow saves recover duplicate requests and reject genuinely stale writers."""
from copy import deepcopy

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.agent_app import AgentApp, AgentAppVersion
from app.models.agent_app_folder import AgentAppFolder
from app.repositories.agent_app.repository import get_version_for_app, update_version_workflow
from app.schemas.agent_app import WorkflowPutBody, WorkflowUndoStack
from app.services.agent_app import service


def graph(text="original"):
    return {"nodes": [{"id": "output", "data": {"kind": "output", "output_config": {"content_template": text}}}], "edges": []}


@pytest.fixture
def persistence(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'workflow.db'}")
    Base.metadata.create_all(engine, tables=[AgentAppFolder.__table__, AgentApp.__table__, AgentAppVersion.__table__])
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as db:
        db.add(AgentAppFolder(id=1, name="Test"))
        db.add(AgentApp(id=1, folder_id=1, name="Test"))
        db.add(AgentAppVersion(id=1, agent_app_id=1, name="v1", workflow_rev=0, workflow_json=graph()))
        db.commit()
    undo = {}
    monkeypatch.setattr(service, "workflow_undo_get", lambda *args: deepcopy(undo.get("value")))
    monkeypatch.setattr(service, "workflow_undo_set", lambda app_id, version_id, value: undo.update(value=deepcopy(value)))
    yield factory, undo
    engine.dispose()


def test_cached_stale_session_cannot_overwrite_a_committed_save(persistence):
    factory, _ = persistence
    with factory() as first, factory() as stale:
        cached = get_version_for_app(stale, 1, 1)
        assert cached.workflow_rev == 0
        assert update_version_workflow(first, 1, 1, workflow_json=graph("first"), expected_rev=0)
        first.commit()
        assert update_version_workflow(stale, 1, 1, workflow_json=graph("stale"), expected_rev=0) is None
        stale.rollback()
    with factory() as db:
        saved = get_version_for_app(db, 1, 1)
        assert saved.workflow_rev == 1
        assert saved.workflow_json == graph("first")


def test_repeated_identical_request_returns_saved_revision_without_conflict(persistence):
    factory, _ = persistence
    body = WorkflowPutBody(**graph("saved"), expected_rev=0)
    with factory() as db:
        first = service.put_workflow_version_service(db, 1, 1, body)
    with factory() as db:
        repeated = service.put_workflow_version_service(db, 1, 1, body)
    assert first.workflow_rev == repeated.workflow_rev == 1
    assert repeated.workflow == graph("saved")


def test_different_stale_request_is_still_a_conflict_and_preserves_winner(persistence):
    factory, _ = persistence
    with factory() as db:
        service.put_workflow_version_service(db, 1, 1, WorkflowPutBody(**graph("winner"), expected_rev=0))
    with factory() as db, pytest.raises(HTTPException) as error:
        service.put_workflow_version_service(db, 1, 1, WorkflowPutBody(**graph("stale"), expected_rev=0))
    assert error.value.status_code == 409
    with factory() as db:
        assert get_version_for_app(db, 1, 1).workflow_json == graph("winner")


def test_undo_history_is_written_only_after_database_commit(persistence, monkeypatch):
    factory, undo = persistence
    body = WorkflowPutBody(**graph("saved"), expected_rev=0, undo_stack=WorkflowUndoStack(states=[graph("saved")], index=0))
    with factory() as db:
        monkeypatch.setattr(db, "commit", lambda: (_ for _ in ()).throw(RuntimeError("commit failed")))
        with pytest.raises(RuntimeError, match="commit failed"):
            service.put_workflow_version_service(db, 1, 1, body)
        db.rollback()
    assert undo == {}


def test_save_response_uses_its_own_revision_if_another_writer_commits(persistence, monkeypatch):
    factory, _ = persistence
    with factory() as first:
        commit = first.commit

        def commit_then_competing_write():
            commit()
            with factory() as second:
                service.put_workflow_version_service(second, 1, 1, WorkflowPutBody(**graph("second"), expected_rev=1))

        monkeypatch.setattr(first, "commit", commit_then_competing_write)
        response = service.put_workflow_version_service(first, 1, 1, WorkflowPutBody(**graph("first"), expected_rev=0))
    assert response.workflow_rev == 1
    assert response.workflow == graph("first")
    with factory() as db:
        assert get_version_for_app(db, 1, 1).workflow_json == graph("second")
