import asyncio
import json

import pytest

from app.services.autobi import lab_pipeline_runner as runner
from app.services.autobi.lab_config_merge import expand_legacy_config, merge_lab_config
from app.services.autobi.lab_tool_outputs import output_stage, sql_output


def test_compact_projects_keep_customizations_in_the_editable_configuration():
    raw = {"lab_mode": "sql", "knowledge_base_id": 42, "atomic_sql_rules": "旧项目口径",
           "model_bindings": {"nl2sql": {"provider_id": 8, "model_name": "selected"}},
           "request": {"advanced_config": {"nl2sql_config": {"prompt": "自选提示词"}}}}
    expanded = expand_legacy_config(raw)
    advanced = expanded["request"]["advanced_config"]
    assert advanced["nl2sql_config"]["prompt"] == "自选提示词\n旧项目口径"
    assert advanced["output_stage"] == "sql"
    assert expanded["knowledge_base_id"] == 42
    assert expanded["model_bindings"]["nl2sql"] == raw["model_bindings"]["nl2sql"]
    assert not advanced["bi_summary_config"]["enable"]
    assert expand_legacy_config(expanded) == expanded
    assert "output_stage" not in merge_lab_config({})["request"]["advanced_config"]
    with pytest.raises(ValueError):
        output_stage(advanced, {"lab_output": "recall"})


@pytest.mark.parametrize("stage,expected", [
    ("recall", [i for i in range(1, 14) if i != 8]),
    ("sql", list(range(1, 16))),
    (None, list(range(1, 19))),
])
def test_tools_run_saved_pipeline_settings_and_stop_after_the_requested_output(monkeypatch, stage, expected):
    cfg = merge_lab_config({})
    adv = cfg["request"]["advanced_config"]
    adv["nl2sql_config"]["prompt"] = "custom question: {{query}}"
    adv["bi_summary_config"]["enable"] = False
    cfg["model_bindings"] = {"nl2sql": {"provider_id": 12, "model_name": "chosen-model"}}
    visited = []
    dispatch = runner._dispatch_step

    async def mock_dispatch(db, sid, question, config, kb_id, acc, by_step, features):
        visited.append(sid)
        if sid in (14, 15):
            return await dispatch(db, sid, question, config, kb_id, acc, by_step, features)
        if sid == 3:
            return {}, {"results": [{"content": "销售", "metadata": {"quote_extend": "实际销售金额"}}]}
        return {}, {}

    async def mock_llm(db, config, role, prompt, options):
        assert prompt == "custom question: my question"
        assert config["model_bindings"][role]["model_name"] == "chosen-model"
        return "SELECT 51 AS actual"

    async def no_persist(*args):
        pass

    monkeypatch.setattr(runner, "_persist_trace", no_persist)
    monkeypatch.setattr(runner, "_dispatch_step", mock_dispatch)
    monkeypatch.setattr(runner, "_call_llm", mock_llm)
    monkeypatch.setattr(runner, "_knowledge_base_database_type", lambda *_: "PostgreSQL")

    async def run():
        return [json.loads(chunk.removeprefix("data:").strip()) async for chunk in
                runner.run_autobi_lab_gateway_sse(None, user_message="my question", lab_config=cfg,
                    kb_id=3, project_id=8, project_name="Any project", trace_id="test", trace_started_at=1,
                    features={"lab_output": stage} if stage else {})]
    events = asyncio.run(run())
    assert not [e for e in events if e["type"] == "error"], events
    assert visited == expected
    results = [e for e in events if e["type"] == "lab_result"]
    if stage == "recall":
        assert [(x["text"], x["content"]) for x in results[0]["items"]] == [("销售", "实际销售金额")]
    elif stage == "sql":
        assert results[0]["sql"] == "SELECT 51 AS actual"
    else:
        assert not results


def test_verified_sql_scope_and_read_only_output():
    for invalid in ("None", "SELECT 1; SELECT 2", "WITH removed AS (DELETE FROM t RETURNING *) SELECT * FROM removed"):
        assert sql_output(invalid, None, None, "PostgreSQL")["kind"] == "clarification"
    with pytest.raises(ValueError):
        sql_output("SELECT * FROM t", {"mode": "restricted"}, None)
