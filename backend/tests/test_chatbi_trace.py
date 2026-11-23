"""Real execution IDs must survive the ChatBI SSE adapter."""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.chatbi import TABLES, ChatBIMessage
from app.schemas.chatbi import ChatRequest
from app.services.chatbi import chat, runtime
from app.services.chatbi.config import identity

USER = identity("user-001")
TRACE = "316f91e4-d96d-441b-95cd-0f920f270256"


@pytest.fixture
def factory(tmp_path, monkeypatch):
    monkeypatch.setenv("CHATBI_AUTOBI_PROJECT_ID", "1")
    monkeypatch.delenv("CHATBI_AGENT_APP_ID", raising=False)
    engine = create_engine(f"sqlite:///{tmp_path / 'trace.db'}")
    Base.metadata.create_all(engine, tables=TABLES)
    yield sessionmaker(engine, expire_on_commit=False)
    engine.dispose()


@pytest.mark.parametrize("outcome", ["succeeded", "failed", "stopped"])
def test_execution_trace_reaches_terminal_events(factory, outcome):
    body = ChatRequest(user=USER.user, query="sales")
    with factory() as db:
        mid = chat.prepare_chat(db, body, USER)

    async def runner(*args):
        yield {"type": "trace_id", "trace_id": TRACE}
        yield {"type": "step_started", "step_id": "sql", "title": "查询数据"}
        if outcome == "failed":
            raise RuntimeError("query failed")
        if outcome == "stopped":
            with factory() as db:
                db.get(ChatBIMessage, mid).stop_requested = True
                db.commit()
            # Let stream_chat's control poll observe the stop flag.
            await asyncio.Event().wait()
        yield {"type": "text", "content": "done"}

    async def collect():
        return [json.loads(frame[6:]) async for frame in chat.stream_chat(
            mid, body, USER, factory=factory, runner=runner
        ) if frame.startswith("data: ")]

    events = asyncio.run(asyncio.wait_for(collect(), timeout=4))
    assert events[0]["event"] == "workflow_started"
    assert events[0]["workflow_run_id"] != TRACE
    assert all(event["trace_id"] == TRACE for event in events[1:])
    finished = next(event for event in events if event["event"] == "workflow_finished")
    assert finished["data"]["status"] == outcome
    assert events[-1]["event"] == ("error" if outcome == "failed" else "workflow_finished")


def test_autobi_runtime_retains_native_trace(monkeypatch):
    from app.services.autobi import lab_runtime

    monkeypatch.setattr(runtime, "model_bindings", lambda: {})
    monkeypatch.setattr(lab_runtime, "build_lab_run_spec_from_project_id", lambda *a, **kw: SimpleNamespace(lab_config={}))

    async def stream(*args, **kwargs):
        yield 'data: ' + json.dumps({"type": "trace_id", "trace_id": TRACE})
        yield 'data: {"type":"done"}'

    monkeypatch.setattr(lab_runtime, "stream_lab_native_sse", stream)

    async def collect():
        return [event async for event in runtime.run_analysis(None, "autobi:1", "sales", {}, "cid", [], USER)]

    assert asyncio.run(collect())[0] == {"type": "trace_id", "trace_id": TRACE}


def test_agent_runtime_uses_the_trace_saved_by_the_engine(monkeypatch):
    from app.repositories.agent_app import repository
    from app.services.agent_app import workflow_engine

    version = SimpleNamespace(id=101, workflow_json={
        "nodes": [
            {"id": "start", "data": {"kind": "start"}},
            {"id": "out", "data": {"kind": "output"}},
        ],
        "edges": [{"id": "e", "source": "start", "target": "out"}],
    })
    saved = []
    monkeypatch.setattr(repository, "get_version_for_app", lambda *a: version)
    monkeypatch.setattr(workflow_engine, "get_version_for_app", lambda *a: version)
    monkeypatch.setattr(workflow_engine, "save_workflow_trace", lambda tid, payload: saved.append((tid, payload)))

    async def collect():
        return [event async for event in runtime.run_analysis(MagicMock(), "agent:1:101", "sales", {}, "cid", [], USER)]

    events = asyncio.run(collect())
    trace_events = [event for event in events if event.get("type") == "trace_id"]
    assert len(trace_events) == 1
    assert saved and all(tid == trace_events[0]["trace_id"] for tid, _ in saved)


def test_nested_agent_trace_does_not_replace_root_trace(monkeypatch):
    from app.repositories.agent_app import repository
    from app.services.agent_app import workflow_engine

    monkeypatch.setattr(repository, "get_version_for_app", lambda *a: SimpleNamespace(id=101))

    async def stream(*args, **kwargs):
        yield 'data: ' + json.dumps({"type": "trace_id", "trace_id": TRACE})
        yield 'data: ' + json.dumps({"type": "thought", "thought": {
            "payload": {"type": "trace_id", "trace_id": "child-trace"}
        }})
        yield 'data: {"status":"done","output":"ok"}'

    monkeypatch.setattr(workflow_engine, "run_agent_workflow_stream", stream)

    async def collect():
        return [event async for event in runtime.run_analysis(None, "agent:1:101", "sales", {}, "cid", [], USER)]

    events = asyncio.run(collect())
    assert [event["trace_id"] for event in events if event.get("type") == "trace_id"] == [TRACE]
