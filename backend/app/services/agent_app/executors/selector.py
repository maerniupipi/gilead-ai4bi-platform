"""选择器节点：按条件匹配首个分支，供引擎剪枝下游边。"""
from __future__ import annotations

from typing import Any

from ..workflow_run_ctx import WorkflowRunContext, resolve_dotted
from ._values import as_text


_as_text = as_text

def _eval_condition(ctx: WorkflowRunContext, ref: str, op: str, value: Any) -> bool:
    ref = (ref or "").strip()
    if not ref:
        raise ValueError("选择器条件未配置引用变量")
    actual = resolve_dotted(ctx, ref)
    s = _as_text(actual)
    v = _as_text(value)
    op = (op or "eq").strip()
    if op == "contains":
        return v in s
    if op == "not_contains":
        return v not in s
    if op == "starts_with":
        return s.startswith(v)
    if op == "ends_with":
        return s.endswith(v)
    if op == "eq":
        return s == v
    if op == "ne":
        return s != v
    if op == "empty":
        return actual is None or actual == [] or actual == {} or s.strip() == ""
    if op == "not_empty":
        return not (actual is None or actual == [] or actual == {} or s.strip() == "")
    raise ValueError(f"选择器不支持的运算符: {op}")


def _case_matches(ctx: WorkflowRunContext, case: dict) -> bool:
    raw_relation = case.get("relation")
    relation = "AND" if raw_relation is None else str(raw_relation).strip().upper()
    if relation not in ("AND", "OR"):
        raise ValueError(f"选择器不支持的条件关系: {raw_relation}（仅支持 AND 或 OR）")
    conds = case.get("conditions") or []
    if not conds:
        return False
    # Resolve every configured condition, so an invalid reference is not hidden by
    # an earlier true OR condition or false AND condition.
    results = [
        _eval_condition(ctx, str(c.get("ref") or ""), str(c.get("op") or "eq"), c.get("value", ""))
        for c in conds
    ]
    return any(results) if relation == "OR" else all(results)


async def execute(ctx: WorkflowRunContext, node: dict) -> dict:
    data = node.get("data") or {}
    cfg = data.get("selector_config") or {}
    cases = cfg.get("cases") or []
    for i, case in enumerate(cases):
        bid = (case.get("id") or "").strip() or f"case-{i}"
        if _case_matches(ctx, case):
            return {"branch_handle": bid, "matched": True}
    return {"branch_handle": "else", "matched": False}

