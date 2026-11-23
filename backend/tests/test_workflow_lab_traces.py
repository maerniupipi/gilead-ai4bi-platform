"""Real lab trace contexts survive streams, hidden thoughts and nested failures."""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.schemas.external_agent import ExternalAgentChatRequest
from app.services.agent_app import external_chat, workflow_engine
from app.services.agent_app.executors import lab, agent
from app.services.agent_app.workflow_run_ctx import WorkflowRunContext
from app.services.autobi import lab_bailian_gateway
from app.services.autobi.lab_runtime import LabTraceContext

TRACE = "316f91e4-d96d-441b-95cd-0f920f270256"


def context():
    return WorkflowRunContext(db=None, run_id="stream", agent_app_id=1, version_id=2, inputs={},
        call_stack=[(1, 2)], nodes_by_id={}, nodes=[], edges=[], var_to_id={}, id_to_var={}, stream=True)


@pytest.mark.parametrize("hidden", [False, True])
def test_lab_uses_real_trace_even_when_output_vars_hide_it(monkeypatch, hidden):
    ctx = context()
    trace = LabTraceContext(TRACE, 10)
    monkeypatch.setattr(lab, "new_lab_trace_context", lambda: trace)
    monkeypatch.setattr(lab, "build_lab_run_spec_from_project_id", lambda *a, **kw: SimpleNamespace())
    seen = []
    async def stream(db, spec, **kwargs):
        seen.append(kwargs["trace"])
        yield 'data: {"message":{"type":"text","content":"answer"}}\n\n'
    async def collect(db, spec, **kwargs):
        seen.append(kwargs["trace"])
        return {"summary": "answer", "trace_id": TRACE}
    monkeypatch.setattr(lab, "stream_lab_bailian_sse", stream)
    monkeypatch.setattr(lab, "collect_lab_run_json", collect)
    node = {"id": "lab-node", "data": {"lab_config": {"project_id": 5, "sse_output_thoughts": not hidden,
        "input_mapping": [{"target_field": "content", "source_mode": "const", "const_value": "question"}],
        "output_vars": ["summary"]}}}
    assert asyncio.run(lab.execute(ctx, node)) == {"summary": "answer"}
    assert seen == [trace]
    event = next(event for event in ctx.thought_events if event["payload"].get("type") == "lab_trace")
    assert event["payload"] == {"type": "lab_trace", "trace_id": TRACE, "node_id": "lab-node", "project_id": 5}


def test_lab_failure_retains_trace_before_request(monkeypatch):
    ctx = context()
    monkeypatch.setattr(lab, "new_lab_trace_context", lambda: LabTraceContext(TRACE, 1))
    monkeypatch.setattr(lab, "build_lab_run_spec_from_project_id", lambda *a, **kw: None)
    monkeypatch.setattr(lab, "collect_lab_run_json", AsyncMock(side_effect=RuntimeError("failed")))
    node = {"id": "lab", "data": {"lab_config": {"project_id": 5, "sse_output_thoughts": False,
        "input_mapping": [{"target_field": "content", "source_mode": "const", "const_value": "q"}]}}}
    with pytest.raises(RuntimeError):
        asyncio.run(lab.execute(ctx, node))
    assert ctx.thought_events[0]["payload"]["trace_id"] == TRACE


@pytest.mark.parametrize("failure", [False, True])
def test_hidden_nested_workflow_propagates_lab_traces_only(monkeypatch, failure):
    ctx = context()
    monkeypatch.setattr(agent, "get_version_for_app", lambda *a: SimpleNamespace(id=4))
    async def nested(*a, **kwargs):
        kwargs["thought_events"].extend([
            {"tag": "hidden", "payload": {"type": "summary", "delta": "private thought"}},
            {"tag": "实验室追踪", "payload": {"type": "lab_trace", "trace_id": TRACE}},
            {"tag": "实验室追踪", "payload": {"type": "lab_trace", "trace_id": "second-lab"}},
        ])
        if failure:
            raise ValueError("nested failed")
        return {"output": "ok", "child_trace_id": "child"}
    monkeypatch.setattr(workflow_engine, "run_nested_agent_workflow", nested)
    node = {"data": {"agent_config": {"target_app_id": 3, "target_version_id": 4, "sse_output_thoughts": False}}}
    if failure:
        with pytest.raises(ValueError):
            asyncio.run(agent.execute(ctx, node))
    else:
        assert asyncio.run(agent.execute(ctx, node))["output"] == "ok"
    assert [event["payload"]["trace_id"] for event in ctx.thought_events] == [TRACE, "second-lab"]


def test_bailian_gateway_uses_given_trace_context(monkeypatch):
    seen = []
    async def native(*a, **kwargs):
        seen.append((kwargs["trace_id"], kwargs["trace_started_at"]))
        yield 'data: ' + json.dumps({"type": "trace_id", "trace_id": TRACE}) + '\n\n'
        yield 'data: ' + json.dumps({"type": "summary", "delta": "ok"}) + '\n\n'
    monkeypatch.setattr(lab_bailian_gateway, "run_autobi_lab_gateway_sse", native)
    spec = SimpleNamespace(content="q", lab_config={}, knowledge_base_id=1, project_id=2, project_name="lab", features={})
    async def collect():
        return [json.loads(frame[6:]) async for frame in lab_bailian_gateway.stream_lab_bailian_sse(None, spec,
            trace=LabTraceContext(TRACE, 123))]
    events = asyncio.run(collect())
    assert seen == [(TRACE, 123)]
    assert events and all(event["trace_id"] == TRACE for event in events)


def test_external_sse_exposes_root_and_every_lab_trace_without_polluting_answer(monkeypatch):
    monkeypatch.setattr(external_chat, "get_agent_app_by_id", lambda *a: SimpleNamespace(id=1))
    monkeypatch.setattr(external_chat, "get_version_for_app", lambda *a: SimpleNamespace(id=2))
    monkeypatch.setattr(external_chat, "_create_log", lambda *a: SimpleNamespace())
    monkeypatch.setattr(external_chat, "_finish_log", lambda *a, **kw: None)
    async def workflow(*a, **kwargs):
        assert kwargs["emit_trace"] is True
        for event in [
            {"type": "trace_id", "trace_id": "root"},
            {"type": "thought", "thought": {"tag": "实验室追踪", "payload": {"type": "lab_trace", "trace_id": TRACE}}},
            {"type": "thought", "thought": {"tag": "实验室追踪", "payload": {"type": "lab_trace", "trace_id": "nested-lab"}}},
            {"status": "done", "output": "final answer"},
        ]:
            yield 'data: ' + json.dumps(event) + '\n\n'
    monkeypatch.setattr(external_chat, "run_agent_workflow_stream", workflow)
    async def collect():
        return [json.loads(frame[6:]) async for frame in external_chat.external_agent_chat_stream(None,
            ExternalAgentChatRequest(app_id=1, version_id=2, message="q"))]
    frames = asyncio.run(collect())
    messages = [message for frame in frames for message in frame["data"]["messages"] if message]
    trace_messages = [message["features"] for message in messages if message["type"] == "trace"]
    assert trace_messages[0]["workflow_trace_id"] == "root"
    assert [item["lab_trace_ids"][0] for item in trace_messages[1:]] == [TRACE, "nested-lab"]
    assert "".join(message["content"] for message in messages if message["type"] == "text") == "final answer"
    assert frames[-1]["data"]["end"] is True
