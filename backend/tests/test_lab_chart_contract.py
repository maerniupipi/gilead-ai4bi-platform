import asyncio
import pytest
from app.services.autobi.lab_prompt_agg import parse_chart_spec_from_llm
from app.services.autobi import lab_pipeline_runner as pipeline


def test_chart_parser_skips_explanatory_code_blocks_and_uses_final_json():
    output = '解释\n```jinja\n{% for k in fields %}\n```\n```sql\nSELECT city\n```\n最终：\n```json\n{"type":"A","xaxis":["city"],"yaxis":["total_sales"]}\n```'
    assert parse_chart_spec_from_llm(output)["yaxis"] == ["total_sales"]
    assert parse_chart_spec_from_llm('说明后输出 {"type":"B","xaxis":["date"],"yaxis":["sales"]}')["type"] == "B"
    assert parse_chart_spec_from_llm("没有 JSON") is None


@pytest.mark.parametrize("output,valid", [
    ('{"type":"A","xaxis":["city"],"yaxis":["total_sales"]}', True),
    ('{"type":"A","xaxis":["city"],"yaxis":["raw_sales"]}', False),
    ("no JSON", False),
])
def test_chart_prompt_renders_legacy_fields_and_validates_result_columns(monkeypatch, output, valid):
    seen = []
    async def llm(db, config, binding, prompt, extra):
        seen.append(prompt)
        return output
    monkeypatch.setattr(pipeline, "_call_llm", llm)
    cfg = {"request": {"advanced_config": {"chart_drawing_config": {"enable": True, "prompt":
        '字段：{% for key, value in rich_sql_data.column_names.items() %}{{ key }}:{{ value }}; {% endfor %}\n'
        'SQL：{% if execute_sql is not none %}{{execute_sql}}{% else %}无{% endif %}'}}}}
    _, result = asyncio.run(pipeline._dispatch_step(None, 18, "销售", cfg, 1,
        {"generated_sql": "SELECT city, SUM(raw_sales) AS total_sales FROM sales GROUP BY city"},
        {16: {"response": {"columns": ["city", "total_sales"], "rows": [{"city": "上海", "total_sales": 100}]}}}))
    assert "{%" not in seen[0] and "{{" not in seen[0]
    assert "total_sales:total_sales" in seen[0]
    assert (result.get("error") is None) == valid
    assert bool(result["chart_spec"]) == valid


def test_single_aggregate_uses_table_without_asking_model_for_axes(monkeypatch):
    async def unexpected_model(*args, **kwargs):
        pytest.fail("A scalar result does not need chart axes")
    monkeypatch.setattr(pipeline, "_call_llm", unexpected_model)
    cfg = {"request": {"advanced_config": {"chart_drawing_config": {"prompt": "Draw a chart"}}}}
    acc = {}
    _, result = asyncio.run(pipeline._dispatch_step(None, 18, "城市销售额占比", cfg, 1, acc,
        {16: {"response": {"columns": ["percentage_of_total"],
                          "rows": [{"percentage_of_total": "8.477443"}], "row_count": 1}}}))
    assert result["chart_spec"] == acc["chart_spec"]
    assert result["chart_spec"]["type"] == "D"
    assert not result["chart_spec"]["xaxis"] and not result["chart_spec"]["yaxis"]
    assert not result.get("error")
