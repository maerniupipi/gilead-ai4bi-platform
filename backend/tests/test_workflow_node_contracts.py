"""Executor contracts; external providers/DB are mocked, HTTP uses MockTransport."""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import HTTPException

from app.services.agent_app.executors import agent, atomic, external_api, lab, llm, output, selector, start, user_input
from app.services.agent_app.executors._values import coerce_value
from app.services.agent_app.workflow_run_ctx import WorkflowRunContext


def context(**kwargs):
    values = dict(db=MagicMock(), run_id="test", agent_app_id=1, version_id=1, inputs={}, call_stack=[],
                  nodes_by_id={}, nodes=[], edges=[], var_to_id={"上游": "up"}, id_to_var={"up": "上游"},
                  context={"up": {"text": '他说"你好"\n下一行', "zero": 0, "flag": False, "items": [1, 2], "obj": {"ok": True}, "nil": None}})
    values.update(kwargs)
    return WorkflowRunContext(**values)


def run(executor, cfg=None, ctx=None, key=None):
    node = {"data": {key: cfg}} if key else {"data": cfg or {}}
    return asyncio.run(executor.execute(ctx or context(), node))


def test_start_is_side_effect_free():
    ctx = context()
    assert run(start, ctx=ctx) == {}
    assert ctx.context["up"]["zero"] == 0


@pytest.mark.parametrize(("kind", "value", "expected"), [
    ("number", "0", 0), ("boolean", "false", False), ("string", "false", "false"),
    ("object", '{"n":0}', {"n": 0}), ("array_string", '["a","b"]', ["a", "b"]),
    ("array_number", '[0,1.5]', [0, 1.5]), ("array_boolean", '[false,true]', [False, True]),
    ("array_object", '[{"n":0}]', [{"n": 0}]),
])
def test_user_input_declared_types(kind, value, expected):
    result = run(user_input, {"fields": [{"variable": "value", "type": kind, "required": True}]}, context(inputs={"value": value}))
    assert result["value"] == expected
    assert type(result["value"]) is type(expected)


@pytest.mark.parametrize(("kind", "value"), [("number", True), ("number", "NaN"), ("boolean", "yes"), ("object", "[]"), ("array_number", "[true]")])
def test_user_input_rejects_wrong_types(kind, value):
    with pytest.raises(ValueError, match="value"):
        run(user_input, {"fields": [{"variable": "value", "type": kind}]}, context(inputs={"value": value}))


def test_user_input_required_whitespace_optional_blank_and_false():
    with pytest.raises(ValueError, match="必填"):
        run(user_input, {"fields": [{"variable": "text", "required": True}]}, context(inputs={"text": "  "}))
    fields = [{"variable": "n", "type": "number", "default": ""}, {"variable": "flag", "type": "boolean", "default": True}]
    assert run(user_input, {"fields": fields}, context(inputs={"flag": False})) == {"n": None, "flag": False}


def test_user_input_source_fallback_and_duplicate_fields():
    fields = [{"variable": "question", "source_mode": "ref", "source_ref": ["input", "input"]}]
    assert run(user_input, {"fields": fields}, context(inputs={"input": "问题"}))["question"] == "问题"
    with pytest.raises(ValueError, match="重复"):
        run(user_input, {"fields": fields * 2}, context(inputs={"input": "问题"}))


@pytest.mark.parametrize(("ref", "value"), [("上游.zero", 0), ("上游.flag", False), ("上游.flag", "false")])
def test_selector_matches_false_and_zero(ref, value):
    cfg = {"cases": [{"id": "chosen", "conditions": [{"ref": ref, "op": "eq", "value": value}]}]}
    assert run(selector, cfg, key="selector_config") == {"branch_handle": "chosen", "matched": True}


def test_selector_first_match_and_all_conditions_and_else():
    cond = {"ref": "上游.zero", "op": "eq", "value": "0"}
    cfg = {"cases": [{"id": "first", "conditions": [cond]}, {"id": "second", "conditions": [cond]}]}
    assert run(selector, cfg, key="selector_config")["branch_handle"] == "first"
    cfg["cases"][0]["conditions"].append({"ref": "上游.flag", "op": "eq", "value": "true"})
    assert run(selector, cfg, key="selector_config")["branch_handle"] == "second"
    assert run(selector, {"cases": []}, key="selector_config") == {"branch_handle": "else", "matched": False}


def test_selector_invalid_reference_or_operator_does_not_route_silently():
    with pytest.raises(ValueError):
        selector._eval_condition(context(), "不存在.x", "ne", "value")
    with pytest.raises(ValueError, match="运算符"):
        selector._eval_condition(context(), "上游.zero", "unknown", "0")
    ctx = context(context={"up": {"items": []}})
    assert selector._eval_condition(ctx, "上游.items", "empty", "")


def test_output_formats_false_zero_and_typed_metadata():
    cfg = {"content_fields": [
        {"source_ref": "上游.zero"}, {"source_ref": "上游.flag"},
        {"source_ref": "上游.obj", "output_format": "json"},
    ], "metadata_fields": [
        {"name": "flag", "type": "BOOLEAN", "source_mode": "const", "const_value": "false"},
        {"name": "items", "type": "ARRAY", "source_ref": "上游.items"},
    ]}
    ctx = context()
    result = run(output, cfg, ctx, "output_config")
    assert result == {"content": '0\n\nfalse\n\n{"ok": true}', "metadata": {"flag": False, "items": [1, 2]}}
    assert ctx.final_output is None  # Engine owns final output commits across parallel nodes.


def test_output_invalid_json_and_reference_are_actionable():
    with pytest.raises(ValueError, match="有效 JSON"):
        run(output, {"content_fields": [{"source_mode": "const", "const_value": "bad", "output_format": "json"}]}, key="output_config")
    with pytest.raises(ValueError, match="未找到"):
        run(output, {"content_fields": [{"source_ref": "不存在.text"}]}, key="output_config")


def test_output_json_constant_and_legacy_template():
    assert run(output, {"content_fields": [{"source_mode": "const", "const_value": '{"n":0}', "output_format": "json"}]}, key="output_config")["content"] == '{"n": 0}'
    assert run(output, {"content_template": "答案 {{上游.zero}}"}, key="output_config")["content"] == "答案 0"


def llm_config(**kwargs):
    return {"provider_id": 1, "model_name": "fake", "system_prompt": "系统指令", "input_params": [{"variable": "input", "source_mode": "const", "default": "问题"}], **kwargs}


@pytest.mark.parametrize("template", ["{{ input }}", "{{上游.text}}", "${input}"])
def test_llm_templates_resolve_once_without_appending_input(template):
    chat = AsyncMock(return_value=SimpleNamespace(content="answer"))
    with patch.object(llm.ChatService, "send_chat", chat):
        assert run(llm, llm_config(use_user_prompt_template=True, user_prompt=template), key="llm_config") == {"text": "answer"}
    req = chat.call_args.args[1]
    assert req.message == (context().context["up"]["text"] if "上游" in template else "问题")
    assert req.system == "系统指令"


def test_llm_blank_named_binding_does_not_erase_explicit_input():
    chat = AsyncMock(return_value=SimpleNamespace(content="answer"))
    with patch.object(llm.ChatService, "send_chat", chat):
        run(llm, llm_config(param_bindings={"input": {"source_mode": "ref", "ref": ""}}), key="llm_config")
    assert chat.call_args.args[1].message == "问题"


@pytest.mark.parametrize('error', [
    HTTPException(status_code=503, detail='busy'),
    HTTPException(status_code=429, detail='rate limited'),
    HTTPException(status_code=504, detail='timeout'),
    HTTPException(status_code=401, detail='unauthorized'),
    httpx.ReadTimeout('upstream timeout'),
])
def test_llm_never_retries_even_when_saved_canvas_requests_retries(error):
    chat = AsyncMock(side_effect=[error, SimpleNamespace(content='must not be called')])
    with patch.object(llm.ChatService, 'send_chat', chat), pytest.raises(type(error)) as caught:
        run(llm, llm_config(retry_count=2, retry_interval=1), key='llm_config')
    assert caught.value is error
    assert chat.await_count == 1


def test_llm_requires_provider_and_model():
    with pytest.raises(ValueError, match="未配置"):
        run(llm, {}, key="llm_config")


def run_agent(nested, cfg=None):
    with patch.object(agent, "get_version_for_app", return_value=SimpleNamespace(id=2)), patch(
        "app.services.agent_app.workflow_engine.run_nested_agent_workflow", AsyncMock(return_value=nested)
    ) as runner:
        result = run(agent, {"target_app_id": 2, "target_version_id": 2, **(cfg or {})}, key="agent_config")
    return result, runner


def test_agent_default_output_survives_child_trace_metadata():
    result, _ = run_agent({"output": "答案", "exports": {}, "child_trace_id": "trace-2"})
    assert result == {"_child_trace_id": "trace-2", "output": "答案", "content": "答案"}


def test_agent_input_mapping_and_false_empty_output_values():
    result, runner = run_agent({"output": "", "exports": {"节点.flag": False, "节点.nil": None}}, {
        "input_mapping": [{"target_field": "zero", "source_mode": "ref", "source_var": "上游.zero"}],
        "output_mapping": [{"source_field": "flag", "target_var": "flag"}, {"source_field": "output", "target_var": "answer"}, {"source_field": "节点.nil", "target_var": "nil"}]
    })
    assert runner.call_args.kwargs["inputs"] == {"zero": 0, "history_question": "当前是新问题",
                                               "features": {"history_question": "当前是新问题"}}
    assert result == {"flag": False, "answer": "", "nil": None}


def test_agent_ambiguous_output_and_recursion_are_rejected():
    with pytest.raises(ValueError, match="多个来源"):
        run_agent({"exports": {"a.text": "a", "b.text": "b"}}, {"output_mapping": [{"source_field": "text", "target_var": "x"}]})
    with patch.object(agent, "get_version_for_app", return_value=SimpleNamespace(id=2)), pytest.raises(ValueError, match="环"):
        run(agent, {"target_app_id": 2, "target_version_id": 2}, context(call_stack=[(2, 2)]), "agent_config")


@pytest.mark.parametrize("path, expected", [("$.data[0].answer", 0), ("$.data.1.answer", False), ("$.data[99]", None), ("$.data", [{"answer": 0}, {"answer": False}])])
def test_external_api_json_paths(path, expected):
    assert external_api._json_path_get({"data": [{"answer": 0}, {"answer": False}]}, path) == expected


def test_external_api_json_path_root_array_and_invalid_syntax():
    assert external_api._json_path_get([{"v": False}], "$[0].v") is False
    with pytest.raises(ValueError, match="JSON Path"):
        external_api._json_path_get({}, "$.data[*]")


def test_external_api_real_http_request_encoding_timeout_and_array_response():
    captured = {}
    def handle(request):
        captured["request"] = request
        return httpx.Response(200, json=[{"answer": False}])
    real_client = httpx.AsyncClient
    def client(**kwargs):
        captured["timeout"] = kwargs["timeout"]
        return real_client(transport=httpx.MockTransport(handle), **kwargs)
    cfg = {"base_url": "https://example.test", "path": "/run", "method": "POST", "timeout": 7,
           "headers": [{"key": "x-zero", "value": 0}], "query": [{"key": "flag", "value": False}],
           "body_template": '{"text":"{{上游.text}}","items":"{{上游.items}}","flag":"{{上游.flag}}"}',
           "output_vars": [{"name": "answer", "json_path": "$[0].answer"}]}
    with patch.object(external_api.httpx, "AsyncClient", side_effect=client):
        result = run(external_api, cfg, key="api_config")
    request = captured["request"]
    assert json.loads(request.content) == {"text": context().context["up"]["text"], "items": [1, 2], "flag": False}
    assert request.headers["x-zero"] == "0"
    assert request.url.params["flag"] == "false"
    assert captured["timeout"].read == 7
    assert result["answer"] is False


@pytest.mark.parametrize("body", ["null", "false", "0"])
def test_external_api_preserves_json_scalars_and_delete_body(body):
    seen = []
    def handle(request):
        seen.append(request.content)
        return httpx.Response(400, text="bad request")
    real_client = httpx.AsyncClient
    with patch.object(external_api.httpx, "AsyncClient", side_effect=lambda **kw: real_client(transport=httpx.MockTransport(handle), **kw)):
        result = run(external_api, {"base_url": "https://example.test", "method": "DELETE", "body_template": body}, key="api_config")
    assert seen == [body.encode()]
    assert result["status_code"] == 400  # HTTP status remains available for selector routing.


def test_external_api_invalid_url_timeout_body():
    for cfg in [{"base_url": ""}, {"base_url": "https://example.test", "timeout": 0},
                {"base_url": "https://example.test", "method": "POST", "body_template": '{"bad":'}]:
        with pytest.raises(ValueError):
            run(external_api, cfg, key="api_config")


ATOMIC_INPUTS = {
    "elasticsearch-value-retriever": {"query": "问题"}, "elasticsearch-knowledge-retriever": {"query": "问题"},
    "sql-template-retriever": {"query": "123"}, "table-meta-retriever": {"query": "问题"},
    "table-value-retriever": {"query": "问题"}, "global-value-meta-retriever": {"query": "问题"},
    "multi-global-value-meta-retriever": {"query": "问题", "table_name": ["t.a", "t.b"]},
    "ner-retriever": {"query": "问题", "entity": ["上海"]}, "execute-sql": {"sql": "SELECT 1"},
    "generate-sql": {"query": "问题", "provider_id": 1, "model_name": "model"},
}


@pytest.mark.parametrize("capability", ATOMIC_INPUTS)
def test_each_atomic_capability_builds_real_request_and_filters_result(capability):
    req_model, _ = atomic._CAPABILITY_MAP[capability]
    service = AsyncMock(return_value={"value": False, "unused": 1})
    rows = [{"key": key, "type": "ARRAY" if isinstance(value, list) else "NUMBER" if isinstance(value, int) else "STRING", "source_mode": "const", "const_value": value} for key, value in ATOMIC_INPUTS[capability].items()]
    rows.append({"key": "knowledge_base_id", "source_mode": "const", "const_value": "1"})
    cfg = {"capability": capability, "input_vars": rows, "output_vars": [{"key": "value"}]}
    with patch.dict(atomic._CAPABILITY_MAP, {capability: (req_model, service)}), patch.object(atomic, "get_knowledge_base_database_type_service", return_value="postgres"):
        result = run(atomic, cfg, key="atomic_config")
    assert result == {"value": False}
    req = service.call_args.args[-1]
    assert isinstance(req, req_model)
    if capability == "sql-template-retriever":
        assert req.query == "123"
    if capability == "generate-sql":
        assert req.context["database_type"] == "postgres"
    else:
        assert service.call_args.args[1] == 1


def test_atomic_missing_invalid_kb_and_optional_empty_parameter():
    for value in [True, "invalid", 0, 1.5]:
        with pytest.raises(ValueError, match="knowledge_base_id"):
            atomic._resolve_knowledge_base_id(context(), {"input_vars": [{"key": "knowledge_base_id", "const_value": value}]})
    body = atomic._build_request_body(context(), {"input_vars": [{"key": "score_threshold", "type": "NUMBER", "const_value": ""}, {"key": "query", "type": "STRING", "const_value": "false"}]})
    assert body == {"query": "false"}


def lab_config(**kwargs):
    return {"project_id": 1, "input_mapping": [{"target_field": "content", "source_mode": "const", "const_value": "问题"}], **kwargs}


def test_lab_preserves_feature_types_and_nonstream_filter():
    cfg = lab_config(input_mapping=[{"target_field": "content", "source_mode": "const", "const_value": "问题"}, {"target_field": "features", "source_mode": "const", "const_value": {"items": "{{上游.items}}", "flag": "{{上游.flag}}"}}], output_vars=["summary", "error"])
    with patch.object(lab, "build_lab_run_spec_from_project_id") as build, patch.object(lab, "collect_lab_run_json", AsyncMock(return_value={"trace_id": "trace", "summary": "答案", "error": None})):
        result = run(lab, cfg, key="lab_config")
    assert build.call_args.kwargs["features"] == {"items": [1, 2], "flag": False, "history_question": "当前是新问题"}
    assert result == {"summary": "答案", "error": None}


def test_lab_accepts_null_content_and_rejects_used_malformed_features():
    assert run(lab, lab_config(input_mapping=[{"target_field": "content", "source_var": "上游.nil"}]), key="lab_config") == {
        "trace_id": "", "summary": "", "sql": "", "error": None}
    with pytest.raises(ValueError, match="features"):
        run(lab, lab_config(input_mapping=[{"target_field": "content", "source_mode": "const", "const_value": "问题"},
            {"target_field": "features", "source_mode": "const", "const_value": "[1]"}]), key="lab_config")


def test_lab_stream_failure_is_returned_and_selected_fields_match_nonstream():
    async def events(*_, trace=None):
        assert trace is not None
        yield 'data:{"status_code":"SUCCESS","message":{"type":"text","content":"partial"}}\n\n'
        yield 'data: {"status_code":"FAILED","message":{"type":"text","content":"[error] upstream unavailable"}}\n\n'
    ctx = context(stream=True)
    with patch.object(lab, "build_lab_run_spec_from_project_id"), patch.object(lab, "stream_lab_bailian_sse", events):
        result = run(lab, lab_config(output_vars=["summary", "error"]), ctx, "lab_config")
    assert result == {"summary": "partial", "error": "[error] upstream unavailable"}
    assert len(ctx.thought_events) == 3
    assert ctx.thought_events[0]["payload"]["type"] == "lab_trace"


def test_shared_types_support_strict_validation_for_script_outputs():
    assert coerce_value('[false]', 'LIST<Bool>', 'flags') == [False]
    with pytest.raises(ValueError):
        coerce_value("1", "number", "result", coerce=False)


def test_llm_unresolved_reference_fails_before_provider_call():
    with pytest.raises(ValueError, match="不存在"):
        llm.build_llm_request(context(), llm_config(input_params=[{"variable": "input", "ref": "不存在.text"}]))


def test_llm_stop_words_are_part_of_actual_request():
    request = llm.build_llm_request(context(), llm_config(stop_words=["END"]))
    assert request.stop_words == ["END"]


def test_atomic_generate_sql_invalid_configured_kb_is_not_ignored():
    rows = [{"key": key, "const_value": value} for key, value in ATOMIC_INPUTS["generate-sql"].items()]
    rows.append({"key": "knowledge_base_id", "const_value": "wrong"})
    with pytest.raises(ValueError, match="knowledge_base_id"):
        run(atomic, {"capability": "generate-sql", "input_vars": rows}, key="atomic_config")


@pytest.mark.parametrize("capability", ATOMIC_INPUTS)
def test_atomic_response_schema_is_exported_without_type_loss(capability):
    request_model, real_service = atomic._CAPABILITY_MAP[capability]
    response_model = real_service.__annotations__["return"]
    response = response_model()
    fake_service = AsyncMock(return_value=response)
    rows = [{"key": key, "const_value": value} for key, value in ATOMIC_INPUTS[capability].items()]
    rows.append({"key": "knowledge_base_id", "const_value": 1})
    # Explicit STRING avoids interpreting a numeric-looking natural-language query as a number.
    for row in rows:
        if row["key"] in ("query", "model_name", "sql"):
            row["type"] = "STRING"
    with patch.dict(atomic._CAPABILITY_MAP, {capability: (request_model, fake_service)}), patch.object(atomic, "get_knowledge_base_database_type_service", return_value="postgres"):
        result = run(atomic, {"capability": capability, "input_vars": rows}, key="atomic_config")
    assert result == response.model_dump()
    if "total" in result:
        assert type(result["total"]) is int and result["total"] == 0
        assert result["results"] == []
    if capability == "execute-sql":
        assert result == {"sql": "", "columns": [], "rows": [], "row_count": 0}


def test_external_api_whole_body_reference_accepts_legacy_serialized_json():
    ctx = context(context={"up": {"body": json.dumps({"query": '带"引号\n医院', "user_id": "U1"})}})
    request = external_api.build_api_request(ctx, {"base_url": "https://example.test", "method": "POST", "body_template": "{{上游.body}}"})
    assert request["body"] == {"query": '带"引号\n医院', "user_id": "U1"}
    assert request["body_kind"] == "json"


def test_output_metadata_does_not_suppress_legacy_content_template():
    cfg = {"content_template": "答案 {{上游.zero}}", "metadata_fields": [{"name": "flag", "source_ref": "上游.flag", "type": "BOOLEAN"}]}
    assert run(output, cfg, key="output_config") == {"content": "答案 0", "metadata": {"flag": False}}


@pytest.mark.parametrize("cfg", [{}, {"content_template": "模板"}])
def test_output_always_exports_declared_metadata_object(cfg):
    assert run(output, cfg, key="output_config")["metadata"] == {}


@pytest.mark.parametrize("relation, expected", [("AND", False), ("OR", True), ("or", True), (None, False)])
def test_selector_condition_relation_applies_to_false_and_zero(relation, expected):
    case = {"id": "chosen", "relation": relation, "conditions": [
        {"ref": "上游.flag", "op": "eq", "value": True},
        {"ref": "上游.zero", "op": "eq", "value": 0},
    ]}
    result = run(selector, {"cases": [case]}, key="selector_config")
    assert result == {"branch_handle": "chosen" if expected else "else", "matched": expected}


def test_selector_or_first_match_and_false_boolean_value():
    cfg = {"cases": [
        {"id": "first", "relation": "OR", "conditions": [
            {"ref": "上游.zero", "op": "eq", "value": 1},
            {"ref": "上游.flag", "op": "eq", "value": False},
        ]},
        {"id": "second", "relation": "OR", "conditions": [{"ref": "上游.zero", "op": "eq", "value": 0}]},
    ]}
    assert run(selector, cfg, key="selector_config") == {"branch_handle": "first", "matched": True}
    cfg["cases"][0]["conditions"][1]["value"] = True
    assert run(selector, cfg, key="selector_config")["branch_handle"] == "second"
    cfg["cases"][1]["conditions"][0]["value"] = 1
    assert run(selector, cfg, key="selector_config") == {"branch_handle": "else", "matched": False}


@pytest.mark.parametrize("relation", ["XOR", "", False])
def test_selector_invalid_condition_relation_is_rejected(relation):
    with pytest.raises(ValueError, match="条件关系"):
        run(selector, {"cases": [{"id": "invalid", "relation": relation, "conditions": []}]}, key="selector_config")


@pytest.mark.parametrize("relation", ["AND", "OR"])
def test_selector_empty_conditions_never_match(relation):
    assert run(selector, {"cases": [{"id": "empty", "relation": relation, "conditions": []}]}, key="selector_config")["matched"] is False


def test_selector_or_does_not_hide_invalid_later_condition():
    case = {"id": "invalid", "relation": "OR", "conditions": [
        {"ref": "上游.flag", "op": "eq", "value": False},
        {"ref": "不存在.value", "op": "eq", "value": 0},
    ]}
    with pytest.raises(ValueError, match="不存在"):
        run(selector, {"cases": [case]}, key="selector_config")
