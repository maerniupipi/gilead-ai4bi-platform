"""Trace previews must match the inputs/outputs actually used by executors."""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.agent_app import service, workflow_engine as engine
from app.services.agent_app.executors import atomic, external_api, lab, llm, output, script
from app.services.agent_app.workflow_run_ctx import WorkflowRunContext


def context():
    return WorkflowRunContext(db=MagicMock(), run_id="test", agent_app_id=1, version_id=1,
                              inputs={}, call_stack=[], nodes_by_id={}, nodes=[], edges=[],
                              var_to_id={"来源": "up"}, id_to_var={"up": "来源"},
                              context={"up": {"value": '带"引号\n换行', "flag": False, "items": [0, 1]}})


def node(kind, cfg):
    config_key = "api_config" if kind == "externalApi" else f"{kind}_config"
    return {"id": "node", "data": {"kind": kind, config_key: cfg}}


def test_script_snapshot_uses_typed_executable_kwargs():
    cfg = {"code": "def main(flag, count, items):\n    return {'seen': [flag, count, items]}", "input_vars": [
        {"name": "flag", "source_mode": "const", "const_value": "false", "type": "boolean"},
        {"name": "count", "source_mode": "const", "const_value": "0", "type": "number"},
        {"name": "items", "source_mode": "ref", "ref": "来源.items", "type": "array_number"},
    ]}
    ctx = context()
    step = node("script", cfg)
    snap = engine._step_input_snapshot(ctx, step, "script")
    result = asyncio.run(script.execute(ctx, step))
    assert snap["kwargs"] == {"flag": False, "count": 0, "items": [0, 1]}
    assert result["seen"] == list(snap["kwargs"].values())
    assert type(snap["kwargs"]["flag"]) is bool
    assert type(snap["kwargs"]["count"]) is int


def test_llm_snapshot_matches_provider_request_and_empty_slot_does_not_override():
    cfg = {"provider_id": 1, "model_name": "mock", "system_prompt": "系统 {{input}}", "use_user_prompt_template": True,
           "user_prompt": "用户 {{ input }}", "stop_words": ["END"],
           "input_params": [{"variable": "input", "source_mode": "const", "default": "问题"}],
           "param_bindings": {"input": {"source_mode": "ref", "ref": ""}}}
    ctx = context()
    step = node("llm", cfg)
    snap = engine._step_input_snapshot(ctx, step, "llm")
    chat = AsyncMock(return_value=SimpleNamespace(content="answer"))
    with patch.object(llm.ChatService, "send_chat", chat):
        asyncio.run(llm.execute(ctx, step))
    request = chat.call_args.args[1]
    assert snap["system_prompt"] == request.system == "系统 问题"
    assert snap["user_prompt"] == request.message == "用户 问题"
    assert snap["input_values"] == {"input": "问题"}
    assert snap["model_params"]["stop_words"] == request.stop_words == ["END"]


def test_external_api_snapshot_matches_native_json_body_and_redacts_credentials():
    ctx = context()
    cfg = {"base_url": "https://example.test", "method": "POST",
           "headers": [{"key": "Authorization", "value": "Bearer dummy-secret"}, {"key": "x-request-id", "value": "public"}],
           "body_template": {"text": "{{来源.value}}", "items": "{{来源.items}}", "flag": "{{来源.flag}}"}}
    snap = engine._step_input_snapshot(ctx, node("externalApi", cfg), "externalApi")
    actual = external_api.build_api_request(ctx, cfg)
    assert snap["body"] == actual["body"] == {"text": '带"引号\n换行', "items": [0, 1], "flag": False}
    assert snap["body_kind"] == actual["body_kind"] == "json"
    assert snap["headers"] == {"Authorization": "[REDACTED]", "x-request-id": "public"}
    assert actual["headers"]["Authorization"] == "Bearer dummy-secret"
    assert "dummy-secret" not in json.dumps(snap)


def test_output_snapshot_matches_typed_metadata_and_template_content():
    ctx = context()
    cfg = {"content_template": "答案 {{来源.value}}", "metadata_fields": [
        {"name": "ok", "source_mode": "const", "const_value": "false", "type": "BOOLEAN"},
        {"name": "count", "source_mode": "const", "const_value": "0", "type": "NUMBER"},
    ]}
    step = node("output", cfg)
    snap = engine._step_input_snapshot(ctx, step, "output")
    result = asyncio.run(output.execute(ctx, step))
    assert snap["rendered_content"] == result["content"]
    assert snap["metadata"] == result["metadata"] == {"ok": False, "count": 0}
    assert type(snap["metadata"]["ok"]) is bool
    assert type(snap["metadata"]["count"]) is int


def test_missing_reference_snapshot_identifies_field_instead_of_empty_value():
    step = node("output", {"content_fields": [{"source_ref": "来源.missing"}]})
    snapshot = engine._safe_step_input_snapshot(context(), step, "output")
    assert "来源.missing" in snapshot["error"]
    assert "不存在" in snapshot["error"]


def test_version_params_have_one_canonical_content_and_metadata_contract():
    version = SimpleNamespace(workflow_json={"nodes": [
        {"id": "input", "data": {"kind": "userInput", "fields": [{"variable": "flag", "type": "boolean", "default": False}]}},
        {"id": "a", "data": {"kind": "output"}}, {"id": "b", "data": {"kind": "output"}},
    ]})
    with patch("app.repositories.agent_app.repository.get_version_for_app", return_value=version):
        params = service.get_agent_version_params_service(MagicMock(), 1, 1)
    assert [(p["name"], p["type"]) for p in params["output_params"]] == [("content", "STRING"), ("metadata", "OBJECT")]
    assert params["input_params"][0]["default_value"] is False


def test_nested_exports_canonical_values_come_from_executed_output_branch():
    nodes = [
        {"id": "start", "data": {"kind": "start", "label": "开始"}},
        {"id": "input", "data": {"kind": "userInput", "label": "输入", "fields": [{"variable": "flag", "type": "boolean"}]}},
        {"id": "select", "data": {"kind": "selector", "label": "选择", "selector_config": {"cases": [{"id": "yes", "conditions": [{"ref": "输入.flag", "op": "eq", "value": "true"}]}]}}},
        {"id": "a", "data": {"kind": "output", "label": "未执行输出", "output_config": {"content_template": "wrong"}}},
        {"id": "b", "data": {"kind": "output", "label": "实际输出", "output_config": {"content_template": "selected", "metadata_fields": [{"name": "ok", "source_mode": "const", "const_value": "false", "type": "BOOLEAN"}]}}},
    ]
    edges = [{"source": "start", "target": "input"}, {"source": "input", "target": "select"},
             {"source": "select", "target": "a", "sourceHandle": "yes"}, {"source": "select", "target": "b", "sourceHandle": "else"}]
    version = SimpleNamespace(id=1, workflow_json={"nodes": nodes, "edges": edges})
    with patch.object(engine, "get_version_for_app", return_value=version), patch.object(engine, "agent_run_trace_set"), patch.object(engine, "save_workflow_trace"):
        result = asyncio.run(engine.run_nested_agent_workflow(MagicMock(), agent_app_id=1, version_id=1, inputs={"flag": False}, call_stack=[]))
    assert result["output"] == result["exports"]["output"] == result["exports"]["content"] == "selected"
    assert result["exports"]["metadata"] == {"ok": False}
    assert "未执行输出.content" not in result["exports"]


def test_lab_snapshot_matches_features_types_and_rejects_invalid_features():
    cfg = {"project_id": 1, "input_mapping": [
        {"target_field": "content", "source_mode": "const", "const_value": "question"},
        {"target_field": "features", "source_mode": "const", "const_value": {"items": "{{来源.items}}", "flag": "{{来源.flag}}"}},
    ]}
    ctx = context()
    step = node("lab", cfg)
    snap = engine._step_input_snapshot(ctx, step, "lab")
    with patch.object(lab, "build_lab_run_spec_from_project_id") as build, patch.object(lab, "collect_lab_run_json", AsyncMock(return_value={"summary": "answer"})):
        asyncio.run(lab.execute(ctx, step))
    assert snap["features"] == build.call_args.kwargs["features"] == {"items": [0, 1], "flag": False,
                                                                  "history_question": "当前是新问题"}
    cfg["input_mapping"][1]["const_value"] = "[]"
    invalid = engine._safe_step_input_snapshot(ctx, node("lab", cfg), "lab")
    assert "features" in invalid["error"] and "对象" in invalid["error"]


def test_atomic_snapshot_keeps_declared_string_and_omits_blank_optional_value():
    cfg = {"capability": "sql-template-retriever", "input_vars": [
        {"key": "knowledge_base_id", "type": "NUMBER", "const_value": "1"},
        {"key": "query", "type": "STRING", "const_value": "123"},
        {"key": "score_threshold", "type": "NUMBER", "const_value": ""},
    ]}
    ctx = context()
    snap = engine._step_input_snapshot(ctx, node("atomic", cfg), "atomic")
    assert snap["request_body"] == atomic._build_request_body(ctx, cfg) == {"query": "123"}
    assert snap["knowledge_base_id"] == 1
    assert type(snap["request_body"]["query"]) is str


def test_atomic_generate_sql_snapshot_resolves_context_without_external_lookup():
    cfg = {"capability": "generate-sql", "input_vars": [
        {"key": "knowledge_base_id", "const_value": "1"},
        {"key": "query", "type": "STRING", "const_value": "123"},
    ], "context_vars": [{"name": "flag", "source_mode": "ref", "source_ref": "来源.flag"}]}
    with patch.object(atomic, "get_knowledge_base_database_type_service", side_effect=AssertionError("snapshot must not query DB")):
        snap = engine._step_input_snapshot(context(), node("atomic", cfg), "atomic")
    assert snap["request_body"]["context"] == {"flag": False}
    assert snap["knowledge_base_id"] == 1
