from unittest.mock import AsyncMock
import asyncio
import copy
import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app import models
from app.schemas.autobi_atomic import GlobalValueMetaRetrieverResponse, TableValueRetrieverResponse
from app.services.autobi import lab_pipeline_runner as pipeline
from app.services.autobi import lab_prompt_agg as agg
from app.services.autobi.lab_features import apply_features_to_lab_config_prompts
from app.repositories.knowledge.knowledge_base import repository


TABLE = "tw_target_cvh"
TABLE_ALIAS = "全渠道月指标(CVH架构)主题表"
FIELD = "indication_name"
FIELD_ALIAS = "适应症名称"


def hit(value, field=FIELD, *, table=TABLE, score=0.8, code=None):
    return {
        "content": value,
        "score": score,
        "metadata": {
            "field_table": table,
            "field_code": code if code is not None else f"{table}&&{field}",
            "field_value": value,
        },
    }


def step(*hits, **extra):
    return {"response": {"results": list(hits), **extra}}


def descriptions():
    return [
        {"table_name": TABLE, "table_alias": TABLE_ALIAS,
         "field_name": field, "field_alias": FIELD_ALIAS}
        for field in (FIELD, f"{FIELD}12")
    ]


@pytest.mark.parametrize("value_step", [11, 12])
def test_qs_recall_merges_sources_into_the_requested_format(value_step):
    by_step = {
        1: step(hit("GC", score=1)),
        6: step(hit("旧表说明&&旧字段说明")),
        7: step(hit("BC"), hit("GC", score=0.6)),
        9: step(hit("GC", score=0.95), hit("GYN"), hit("GC", score=0.7)),
        value_step: step(hit("LC"), *[hit(value, f"{FIELD}12") for value in ("GC", "BC", "GYN", "LC")]),
        23 - value_step: step(hit("跳过步骤的值"), skipped=True),
        8: step(hit("SQL样例不是候选值")),
    }

    original = copy.deepcopy(by_step)
    result = agg.build_qs_recall(by_step, descriptions())
    expected = ["LC"] if value_step == 12 else ["GC", "BC", "GYN", "LC"]

    assert result == (
        f'表名："{TABLE}"{{{TABLE_ALIAS}}}\n字段：\n'
        f'候选值：字段"{TABLE}.{FIELD}"{{{FIELD_ALIAS}}}在数据表中有如下值 {expected!r}\n'
        f'候选值：字段"{TABLE}.{FIELD}12"{{{FIELD_ALIAS}}}在数据表中有如下值 [\'GC\', \'BC\', \'GYN\', \'LC\']'
    )
    assert by_step == original


def test_qs_recall_normalizes_field_codes_and_keeps_other_tables_and_columns():
    by_step = {9: step(
        hit("GC"), hit("GC", code=f"{TABLE}.{FIELD}"), hit("GC", code=FIELD),
        hit("BC", code=f"{TABLE}.{FIELD}"),
        hit("GC", "indication_name12"), hit("GC", table="another_table"),
        hit("GC", table="public.tw_target_cvh", code="public.tw_target_cvh.indication_name"),
    )}

    assert agg.collect_qs_recall_values(by_step) == {
        TABLE: {FIELD: ["GC", "BC"], "indication_name12": ["GC"]},
        "another_table": {FIELD: ["GC"]},
        "public.tw_target_cvh": {FIELD: ["GC"]},
    }


def test_qs_recall_filters_empty_values_and_invalid_fields_without_losing_zero_or_text():
    by_step = {7: step(
        hit(None), hit(""), hit("  "), hit(0), hit(" GC "), hit("GC"), hit("gc"),
        hit("胃癌"), hit("O'Reilly"), hit("C:\\tmp"),
        hit("无字段", code=""), hit("无表", table="", code=FIELD),
        {"content": "格式错误", "metadata": []},
    )}

    assert agg.collect_qs_recall_values(by_step) == {
        TABLE: {FIELD: ["0", "GC", "gc", "胃癌", "O'Reilly", "C:\\tmp"]},
    }
    text = agg.build_qs_recall(by_step)
    assert "None" not in text
    assert "O'Reilly" in text
    assert "胃癌" in text


def test_qs_recall_can_get_table_and_field_from_code_and_value_from_metadata():
    assert agg.collect_qs_recall_values({1: step({
        "metadata": {"field_code": f"{TABLE}&&{FIELD}", "field_value": "GC"},
    })}) == {TABLE: {FIELD: ["GC"]}}


def test_qs_recall_uses_step_six_as_description_fallback_only():
    text = agg.build_qs_recall({
        6: step(hit(f"{TABLE_ALIAS}&&{FIELD_ALIAS}")),
        7: step(hit("GC")),
    })
    assert f'表名："{TABLE}"{{{TABLE_ALIAS}}}' in text
    assert f'字段"{TABLE}.{FIELD}"{{{FIELD_ALIAS}}}' in text
    assert text.count("['GC']") == 1
    assert "&&" not in text


def test_qs_recall_empty_result_is_explicit():
    assert agg.build_qs_recall({6: step(hit("表说明&&字段说明"))}) == "（暂无候选值召回结果）"






@pytest.mark.parametrize('key', ['qs_recall'])
def test_qs_recall_is_not_filled_from_request_features_before_recall(key):
    config = {"request": {"advanced_config": {
        "nl2sql_config": {"prompt": '{{' + key + '}} / {{max_year}}'},
    }}}
    rendered = apply_features_to_lab_config_prompts(config, {key: "外部传入", "max_year": 2026})
    assert rendered["request"]["advanced_config"]["nl2sql_config"]["prompt"] == '{{' + key + '}} / 2026'
    assert config["request"]["advanced_config"]["nl2sql_config"]["prompt"].endswith("{{max_year}}")


def test_nested_request_features_preserve_runtime_recall_placeholders():
    template = '{{features.qs_recall}} / {{features.max_year}}'
    config = {'request': {'advanced_config': {'nl2sql_config': {'prompt': template}}}}
    rendered = apply_features_to_lab_config_prompts(config, {'features': {
        'qs_recall': 'forged full', 'max_year': 2026,
    }})
    assert rendered['request']['advanced_config']['nl2sql_config']['prompt'] == template.replace('{{features.max_year}}', '2026')


def test_qs_recall_descriptions_are_scoped_to_the_active_knowledge_base():
    engine = create_engine("sqlite://")
    for model in (models.KnowledgeBase, models.KbTableStructure, models.KbTableField):
        model.__table__.create(engine)
    try:
        with Session(engine) as db:
            for kb_id in (1, 2, 3):
                db.add(models.KnowledgeBase(id=kb_id, name=f"kb{kb_id}", knowledge_access_id=1, is_deleted=kb_id == 3))
                db.add(models.KbTableStructure(id=kb_id, knowledge_base_id=kb_id,
                                              table_structure_id=1, table_name=TABLE, table_alias=f"表说明{kb_id}"))
                db.add(models.KbTableField(kb_table_structure_id=kb_id, table_field_id=1,
                                          field_name=FIELD, field_alias=f"字段说明{kb_id}", field_type="varchar"))
            db.add(models.KbTableField(kb_table_structure_id=1, table_field_id=2,
                                      field_name="disabled", field_alias="未启用", field_type="varchar", is_enabled=False))
            db.commit()

            assert repository.list_kb_recall_field_descriptions(db, 1, [TABLE]) == [{
                "table_name": TABLE, "table_alias": "表说明1", "field_name": FIELD, "field_alias": "字段说明1",
            }]
            assert repository.list_kb_recall_field_descriptions(db, 1, ["other_table"]) == []
            assert repository.list_kb_recall_field_descriptions(db, 3, [TABLE]) == []
            assert repository.list_kb_recall_field_descriptions(db, 1, []) == []
    finally:
        engine.dispose()


@pytest.mark.parametrize("multi_column", [False, True])
def test_qs_recall_is_available_to_ner_sql_and_summary_after_all_value_retrieval(monkeypatch, multi_column):
    original_dispatch = pipeline._dispatch_step
    prompts = {}
    metadata_calls = []
    retrieval_calls = []
    traces = []
    responses = {
        1: step(hit("GC")), 6: step(hit("旧表说明&&旧字段说明")),
        7: step(hit("BC")), 9: step(hit("GC", score=0.6), hit("GYN")),
        16: {"response": {"columns": ["city", "sales"], "rows": [["上海", 10], ["北京", 20]], "row_count": 2}},
    }

    def load_descriptions(db, kb_id, table_names):
        metadata_calls.append((kb_id, table_names))
        return descriptions()

    async def dispatch(db, sid, *args, **kwargs):
        features = kwargs.get("features") or {}
        if sid <= 12:
            assert "qs_recall" not in features
        if sid in (11, 12, 13, 14, 18):
            return await original_dispatch(db, sid, *args, **kwargs)
        return {}, responses.get(sid, step(skipped=True))["response"]

    async def model(db, config, binding, prompt, extra):
        prompts[binding] = prompt
        if binding == "ner_retrieval":
            return '{"ner": []}'
        if binding == "chart_drawing":
            return '{"type": "A", "xaxis": ["city"], "yaxis": ["sales"]}'
        return "SELECT 1"

    async def table_values(db, kb_id, request):
        retrieval_calls.append("table")
        assert kb_id == 42 and request.table_name == TABLE
        return TableValueRetrieverResponse(results=[hit("LC")], total=1)

    async def multi_values(db, kb_id, request):
        retrieval_calls.append("multi")
        assert kb_id == 42 and request.table_name == [f"{TABLE}&&{FIELD}"]
        return GlobalValueMetaRetrieverResponse(results=[hit("LC")], total=1)

    async def summary(db, request):
        prompts["summary"] = request.message
        yield "summary"

    monkeypatch.setattr(pipeline, "list_kb_recall_field_descriptions", load_descriptions)
    monkeypatch.setattr(pipeline.AutoBIAtomicService, "table_value_retrieve", table_values)
    monkeypatch.setattr(pipeline.AutoBIAtomicService, "multi_global_value_meta_retrieve", multi_values)
    monkeypatch.setattr(pipeline, "_dispatch_step", dispatch)
    monkeypatch.setattr(pipeline, "_call_llm", model)
    monkeypatch.setattr(pipeline, "_knowledge_base_database_type", lambda *_: "PostgreSQL")
    monkeypatch.setattr(pipeline, "_persist_trace", AsyncMock(side_effect=lambda *args: traces.append(copy.deepcopy(args[-1]))))
    monkeypatch.setattr(pipeline.ChatService, "stream_chat_text_deltas", summary)
    config = {"request": {"advanced_config": {
        "ner_retrieval_config": {"enable": True, "prompt": "NER {{qs_recall}}"},
        "nl2sql_config": {"prompt": "SQL {{qs_recall}}"},
        "bi_summary_config": {"prompt": "总结 {{qs_recall}}"},
        "chart_drawing_config": {"enable": True, "prompt": "图表 {{qs_recall}}"},
        "value_multi_column_embedding_config": {"enable": multi_column},
    }}, "model_bindings": {"bi_summary": {"provider_id": 1, "model_name": "test"}}}

    async def run():
        return [json.loads(chunk[6:]) async for chunk in pipeline.run_autobi_lab_gateway_sse(
            None, user_message="销售", lab_config=config, kb_id=42, project_id=1,
            project_name="test", trace_id="qs-recall-test", trace_started_at=1000,
        )]

    events = asyncio.run(run())
    assert not any(event["type"] == "error" for event in events), events
    assert events[-1] == {"type": "done"}
    assert metadata_calls == [(42, [TABLE])]
    assert retrieval_calls == (["multi"] if multi_column else ["table"])
    for key in ("ner_retrieval", "nl2sql", "summary", "chart_drawing"):
        assert "{{qs_recall}}" not in prompts[key]
        assert "外部传入" not in prompts[key]
        assert '外部过滤结果' not in prompts[key]
        assert TABLE_ALIAS in prompts[key]
        assert repr(["LC"] if multi_column else ["GC", "BC", "GYN", "LC"]) in prompts[key]
    assert repr(["LC"] if multi_column else ["GC", "BC", "GYN", "LC"]) in traces[-1][13]["request"]["full_prompt"]


@pytest.mark.parametrize("response", [{"results": []}, {"skipped": True}, {"error": "offline"}])
def test_enabled_multi_column_never_fills_qs_recall_from_other_steps(response):
    by_step = {1: step(hit("old ES")), 7: step(hit("old global")), 12: {"response": response}}
    assert agg.collect_qs_recall_values(by_step, multi_column_enabled=True) == {}
    assert agg.build_qs_recall(by_step, multi_column_enabled=True) == "（暂无候选值召回结果）"


def test_qs_recall_takes_all_twelve_multi_values_and_does_not_mix_other_columns():
    values = [f"V{i}" for i in range(6)] + [f"E{i}" for i in range(6)]
    by_step = {
        1: step(hit("outside", field="other")),
        7: step(*[hit(f"G{i}") for i in range(90)]),
        9: step(hit("old ES")),
        12: step(*[hit(v) for v in values]),
    }
    assert agg.collect_qs_recall_values(by_step, multi_column_enabled=True) == {TABLE: {FIELD: values}}
    assert repr(values) in agg.build_qs_recall(by_step, descriptions(), multi_column_enabled=True)


def test_disabled_multi_column_ignores_any_stale_multi_result():
    by_step = {1: step(hit("ES")), 11: step(hit("ordinary")), 12: step(hit("stale multi"))}
    assert agg.collect_qs_recall_values(by_step, multi_column_enabled=False) == {TABLE: {FIELD: ["ES", "ordinary"]}}


def test_qs_recall_empty_pipeline_has_a_resolved_variable_without_a_metadata_query(monkeypatch):
    seen = []

    async def dispatch(db, sid, *args, **kwargs):
        if sid == 13:
            seen.append(pipeline._runtime_prompt("候选值：{{qs_recall}}", kwargs["features"]))
        return {}, {"skipped": True}

    def unexpected(*args):
        pytest.fail("Empty recalls must not query table descriptions")

    monkeypatch.setattr(pipeline, "_dispatch_step", dispatch)
    monkeypatch.setattr(pipeline, "list_kb_recall_field_descriptions", unexpected)
    monkeypatch.setattr(pipeline, "_persist_trace", AsyncMock(side_effect=lambda *args: None))

    async def run():
        return [json.loads(chunk[6:]) async for chunk in pipeline.run_autobi_lab_gateway_sse(
            None, user_message="销售", lab_config={"request": {"advanced_config": {"bi_summary_config": {"enable": False}}}},
            kb_id=42, project_id=1, project_name="test", trace_id="empty-recall", trace_started_at=1000,
        )]

    events = asyncio.run(run())
    assert not any(event["type"] == "error" for event in events), events
    assert seen == ["候选值：（暂无候选值召回结果）"]


