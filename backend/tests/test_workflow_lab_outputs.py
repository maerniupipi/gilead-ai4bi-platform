from unittest.mock import AsyncMock
"""Lab SQL and empty branches behave the same in JSON and streaming workflows."""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.agent_app import workflow_engine
from app.services.agent_app.executors import lab
from app.services.agent_app.workflow_run_ctx import WorkflowRunContext
from app.services.autobi import lab_pipeline_runner as pipeline
from app.services.autobi import lab_bailian_gateway


SQL = "SELECT sales FROM facts WHERE user_id = '123'"
EMPTY = {"trace_id": "", "summary": "", "sql": "", "error": None}


def context(stream=False):
    return WorkflowRunContext(db=MagicMock(), run_id="test", agent_app_id=1, version_id=1,
        inputs={}, call_stack=[], nodes_by_id={}, nodes=[], edges=[], stream=stream,
        var_to_id={"上游": "up"}, id_to_var={"up": "上游"},
        context={"up": {"question": None}})


def config(mapping=None, **kwargs):
    return {"project_id": 1, "input_mapping": mapping if mapping is not None else [
        {"target_field": "content", "source_mode": "const", "const_value": "销量"}], **kwargs}


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("mapping", [
    [], [{"target_field": "content", "source_mode": "const", "const_value": None}],
    [{"target_field": "content", "source_mode": "const", "const_value": ""}],
    [{"target_field": "content", "source_mode": "const", "const_value": " \n\t "}],
    [{"target_field": "content", "source_var": "上游.question"}],
    [{"target_field": "query", "source_mode": "const", "const_value": None}],
    [{"target_field": "content", "source_mode": "ref", "source_ref": ""}],
])
def test_empty_query_short_circuits_all_lab_work(stream, mapping):
    # Unused features must not resolve references, access projects, or allocate traces.
    mapping = mapping + [{"target_field": "features", "source_mode": "const",
                          "const_value": {"unused": "{{不存在.value}}"}}]
    ctx = context(stream)
    with patch.object(lab, "build_lab_run_spec_from_project_id") as build, \
            patch.object(lab, "collect_lab_run_json", AsyncMock()) as collect, \
            patch.object(lab, "stream_lab_bailian_sse") as events, \
            patch.object(lab, "new_lab_trace_context") as trace:
        result = asyncio.run(lab.execute(ctx, {"data": {"lab_config": config(mapping)}}))
    assert result == EMPTY
    assert ctx.thought_events == []
    build.assert_not_called()
    collect.assert_not_awaited()
    events.assert_not_called()
    trace.assert_not_called()


def test_empty_query_respects_output_selection_and_does_not_require_project_loading():
    cfg = config([], project_id=None, output_vars=[{"key": "summary"}, "sql", "error"])
    assert asyncio.run(lab.execute(context(), {"data": {"lab_config": cfg}})) == {
        "summary": "", "sql": "", "error": None}


def test_nonempty_query_still_rejects_invalid_references_and_features():
    with pytest.raises(ValueError, match="未找到"):
        lab.resolve_lab_inputs(context(), config([{"source_var": "不存在.question"}]))
    with pytest.raises(ValueError, match="features"):
        lab.resolve_lab_inputs(context(), config([
            {"source_mode": "const", "const_value": "销量"},
            {"target_field": "features", "source_mode": "const", "const_value": "[1]"}]))


def test_query_alias_and_legacy_content_ref_resolve_nonempty_questions():
    ctx = context()
    ctx.context["up"]["question"] = "销量"
    mapping = [{"target_field": "query", "source_ref": "上游.question"}]
    for cfg in [config(mapping), config([], content_ref="上游.question")]:
        assert lab.resolve_lab_inputs(ctx, cfg) == {"project_id": 1, "content": "销量",
                                                    "features": {"history_question": "当前是新问题"}}


@pytest.mark.parametrize("stream,hidden", [(False, False), (True, False), (True, True)])
@pytest.mark.parametrize("failure", [False, True])
def test_sql_is_available_with_hidden_thoughts_and_after_later_failure(stream, hidden, failure):
    ctx = context(stream)
    error = "查询失败" if failure else None

    async def events(*args, **kwargs):
        yield 'data: ' + json.dumps({"message": {"type": "sql_citations", "features": {
            "sql_citations": [{"query": "销量", "sql": SQL}]}}}) + '\n\n'
        yield 'data: ' + json.dumps({"message": {"type": "text", "content": "总结"}}) + '\n\n'
        if failure:
            yield 'data: ' + json.dumps({"status_code": "FAILED", "message": {
                "type": "text", "content": error}}) + '\n\n'

    cfg = config(output_vars=["summary", "sql", "error"], sse_output_thoughts=not hidden)
    with patch.object(lab, "build_lab_run_spec_from_project_id"), \
            patch.object(lab, "stream_lab_bailian_sse", events), \
            patch.object(lab, "collect_lab_run_json", AsyncMock(return_value={
                "trace_id": "trace", "summary": "总结", "sql": SQL, "error": error})):
        assert asyncio.run(lab.execute(ctx, {"data": {"lab_config": cfg}})) == {
            "summary": "总结", "sql": SQL, "error": error}


def test_json_collector_preserves_final_sql_without_summary(monkeypatch):
    async def events(*args, **kwargs):
        for event in [{"type": "trace_id", "trace_id": "trace"},
                      {"type": "bailian_sql", "sql": SQL}, {"type": "done"}]:
            yield 'data: ' + json.dumps(event) + '\n\n'
    monkeypatch.setattr(pipeline, "run_autobi_lab_gateway_sse", events)
    result = asyncio.run(pipeline.collect_autobi_lab_gateway_json(None, user_message="销量",
        lab_config={}, kb_id=1, project_id=1, project_name="lab", trace_id="trace", trace_started_at=1))
    assert result["sql"] == SQL
    assert result["summary"] == ""
    assert result["error"] is None


def test_real_pipeline_returns_identical_executed_sql_in_json_and_sse(monkeypatch):
    original = 'SELECT SUM(sell_out_value) FROM facts'
    final = original + " WHERE user_id = '123'"
    spec = SimpleNamespace(content="shell_out 销量", project_id=1, project_name="lab",
        knowledge_base_id=1, features={},
        lab_config={"request": {"advanced_config": {"bi_summary_config": {"enable": False}}}})

    async def dispatch(db, sid, user_message, cfg, kb_id, acc, by_step, **kwargs):
        if sid in (14, 15):
            acc["generated_sql"] = original if sid == 14 else final
            return {}, {"sql": acc["generated_sql"]}
        return {}, {"skipped": True}
    monkeypatch.setattr(pipeline, "_dispatch_step", dispatch)
    monkeypatch.setattr(pipeline, "_persist_trace", AsyncMock(side_effect=lambda *args: None))
    monkeypatch.setattr(lab_bailian_gateway, "trace_get", lambda *args: {})
    monkeypatch.setattr(lab, "build_lab_run_spec_from_project_id", lambda *args, **kwargs: spec)
    node = {"data": {"lab_config": config(output_vars=["summary", "sql", "error"])}}
    ordinary = asyncio.run(lab.execute(context(), node))
    streaming = asyncio.run(lab.execute(context(True), node))
    assert ordinary == streaming == {"summary": "", "sql": final, "error": None}


@pytest.mark.parametrize("stream", [False, True])
def test_parallel_empty_branch_completes_and_downstream_can_reference_sql(monkeypatch, stream):
    def node(nid, kind, **kwargs):
        return {"id": nid, "data": {"kind": kind, "label": nid, **kwargs}}
    nodes = [node("start", "start"), node("questions", "userInput", fields=[
        {"variable": "q1", "type": "string"}, {"variable": "q2", "type": "string"}])]
    for index in (1, 2):
        nodes.append(node(f"lab{index}", "lab", lab_config=config([
            {"target_field": "content", "source_var": f"questions.q{index}"}])))
    nodes.append(node("out", "output", output_config={"content_fields": [
        {"source_ref": "lab1.summary"}, {"source_ref": "lab2.summary"}], "metadata_fields": [
        {"name": "sql", "type": "string", "source_ref": "lab1.sql"},
        {"name": "empty_sql", "type": "string", "source_ref": "lab2.sql"}]}))
    edges = [{"source": source, "target": target} for source, target in [
        ("start", "questions"), ("questions", "lab1"), ("questions", "lab2"),
        ("lab1", "out"), ("lab2", "out")]]
    version = SimpleNamespace(workflow_json={"nodes": nodes, "edges": edges})
    build = MagicMock(return_value=SimpleNamespace())
    monkeypatch.setattr(lab, "build_lab_run_spec_from_project_id", build)
    monkeypatch.setattr(lab, "collect_lab_run_json", AsyncMock(return_value={
        "trace_id": "trace", "summary": "有结果", "sql": SQL, "error": None}))

    async def events(*args, **kwargs):
        yield 'data: ' + json.dumps({"message": {"type": "sql_citations", "features": {
            "sql_citations": [{"sql": SQL}]}}}) + '\n\n'
        yield 'data: ' + json.dumps({"message": {"type": "text", "content": "有结果"}}) + '\n\n'
    monkeypatch.setattr(lab, "stream_lab_bailian_sse", events)
    monkeypatch.setattr(workflow_engine, "get_version_for_app", lambda *args: version)
    monkeypatch.setattr(workflow_engine, "save_workflow_trace", lambda *args: None)
    monkeypatch.setattr(workflow_engine, "agent_run_trace_set", lambda *args: None)

    async def run():
        if stream:
            frames = [json.loads(frame[6:]) async for frame in workflow_engine.run_agent_workflow_stream(
                MagicMock(), 1, 1, {"q1": "销量", "q2": None})]
            assert frames[-1]["status"] == "done"
            skipped = next(frame for frame in frames if frame.get("node_id") == "lab2" and frame.get("status") == "done")
            assert skipped["output_snapshot"] == EMPTY
            output = next(frame for frame in frames if frame.get("node_id") == "out" and frame.get("status") == "done")
            assert output["output_snapshot"]["metadata"] == {"sql": SQL, "empty_sql": ""}
            return frames[-1]
        return await workflow_engine.run_nested_agent_workflow(MagicMock(), agent_app_id=1,
            version_id=1, inputs={"q1": "销量", "q2": None}, call_stack=[])

    result = asyncio.run(run())
    assert result["output"] == "有结果\n\n"
    if not stream:
        assert result["exports"]["lab1.sql"] == SQL
        assert result["exports"]["lab2.sql"] == ""
    assert build.call_count == 1
