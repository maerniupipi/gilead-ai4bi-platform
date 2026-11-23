"""lab_features：占位符与请求体 features 的替换逻辑。"""

from __future__ import annotations

from app.services.autobi.lab_features import replace_features_in_template
import pytest


def test_flat_max_year():
    t = "year={{max_year}}"
    assert replace_features_in_template(t, {"max_year": 2026}) == "year=2026"


def test_nested_features_max_year():
    t = "y={{features.max_year}}"
    body = {"features": {"max_year": 2026}}
    assert replace_features_in_template(t, body) == "y=2026"


def test_features_prefix_flat_body_compat():
    """模板 {{ features.max_year }} + 扁平 { max_year: 2026 }（与前端默认一致）。"""
    t = "{{features.max_year}}年Q1"
    assert replace_features_in_template(t, {"max_year": 2026, "max_month": "03"}) == "2026年Q1"


def test_legacy_scalar_features_key():
    t = "{{features.max_year}} 与 {{features.foo}}"
    assert replace_features_in_template(t, {"features": 2025}) == "2025 与 2025"


def test_unknown_placeholder_unchanged():
    t = "{{not_in_body}}"
    assert replace_features_in_template(t, {"max_year": 1}) == "{{not_in_body}}"


def test_jinja_filter_still_after_pipe():
    """仅取 | 前路径段用于 features（管道留给其它引擎的语义保留为路径前缀）。"""
    t = "{{max_year|default(0)}}"
    # 当前实现：path 为 max_year|default(0)，split("|")[0] 得到 max_year — 与旧行为一致
    assert replace_features_in_template(t, {"max_year": 2026}) == "2026"


@pytest.mark.parametrize('identity', [
    {'role': 'administrator', 'permission': 'all'},
    {'role': 'analyst', 'permission': 'region'},
    {'department': 'finance', 'scope_values': ['A', 'B']},
    {'scope_values': ['上海']},
])
def test_runtime_prompt_only_substitutes_explicit_variables(identity):
    from app.services.autobi.lab_pipeline_runner import _runtime_prompt
    prompt = '原样保留的配置\n问题：{{question}}\n范围：{{scope_values}}\n'
    values = {**identity, 'question': '原始问题'}
    assert _runtime_prompt(prompt, values) == replace_features_in_template(prompt, values)
