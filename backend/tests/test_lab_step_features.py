import json

from app.services.autobi.lab_features import replace_features_in_template
from app.services.autobi.lab_prompt_agg import (
    build_step_feature_values,
    build_step_response_nlp,
)


def test_build_step_feature_values_exposes_named_and_step_scoped_keys():
    response = {
        "total": 1,
        "results": [
            {
                "score": 1,
                "content": "杭州和黄医药科技有限公司",
                "metadata": {
                    "field_code": "ads_sales_fact&&distributor_name",
                    "field_table": "ads_sales_fact",
                },
            }
        ],
    }

    values = build_step_feature_values(
        step_id=1,
        api_key="elasticsearch-value-retriever",
        title="ES表值召回",
        response=response,
    )

    raw_key = "elasticsearch-value-retriever_result"
    nlp_key = "elasticsearch-value-retriever_nlp"
    assert json.loads(values[raw_key]) == response
    assert "杭州和黄医药科技有限公司" in values[nlp_key]
    assert "ads_sales_fact.distributor_name" in values[nlp_key]
    assert values["step_1_elasticsearch-value-retriever_result"] == values[raw_key]
    assert values["step_1_elasticsearch-value-retriever_nlp"] == values[nlp_key]


def test_step_feature_values_can_replace_hyphenated_placeholders():
    values = build_step_feature_values(
        step_id=1,
        api_key="elasticsearch-value-retriever",
        title="ES表值召回",
        response={"total": 0, "results": []},
    )

    rendered = replace_features_in_template(
        "原始：{{elasticsearch-value-retriever_result}}\n"
        "自然语言：{{elasticsearch-value-retriever_nlp}}",
        values,
    )

    assert "{{" not in rendered
    assert '"total": 0' in rendered
    assert "共召回 0 条结果" in rendered


def test_skipped_step_nlp_contains_reason():
    text = build_step_response_nlp(
        {"skipped": True, "reason": "多列同值未开启"},
        "多列同值召回",
    )

    assert text == "多列同值召回：已跳过，原因：多列同值未开启"


def test_duplicate_api_key_keeps_step_aliases_while_latest_named_value_wins():
    runtime_features = {}
    first = build_step_feature_values(
        step_id=1,
        api_key="elasticsearch-value-retriever",
        title="ES表值召回",
        response={"total": 1, "results": [{"content": "第一次"}]},
    )
    second = build_step_feature_values(
        step_id=9,
        api_key="elasticsearch-value-retriever",
        title="ES表值召回（双次检索合并）",
        response={"total": 1, "results": [{"content": "第二次"}]},
    )

    runtime_features.update(first)
    runtime_features.update(second)

    assert "第二次" in runtime_features["elasticsearch-value-retriever_nlp"]
    assert "第一次" in runtime_features["step_1_elasticsearch-value-retriever_nlp"]
    assert "第二次" in runtime_features["step_9_elasticsearch-value-retriever_nlp"]
