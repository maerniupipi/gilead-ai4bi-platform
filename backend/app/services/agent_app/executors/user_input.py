from typing import Any

from ..workflow_run_ctx import WorkflowRunContext
from ._values import coerce_value


def _fallback_from_source(ctx: WorkflowRunContext, f: dict) -> Any:
    """字段未在 inputs 中显式传入时，根据「来源」解析默认值（常量或引用）。"""
    mode = (f.get("source_mode") or "const").strip()
    if mode == "const":
        return f.get("default")
    if mode == "ref":
        ref = f.get("source_ref") or []
        if len(ref) >= 2:
            cat, key = ref[0], ref[1]
            if cat == "input":
                if key == "input":
                    return ctx.inputs.get("input")
                if key == "attachments":
                    return ctx.inputs.get("attachments")
                if key == "metadata":
                    return ctx.inputs.get("metadata")
            if cat == "session":
                return ctx.inputs.get(key)
    return f.get("default")


async def execute(ctx: WorkflowRunContext, node: dict) -> dict:
    data = node.get("data") or {}
    fields = data.get("fields")
    if not fields:
        fields = [
            {
                "variable": "input",
                "display": "input",
                "type": "string",
                "required": True,
                "hidden": False,
            }
        ]
    out: dict = {}
    for f in fields:
        key = (f.get("variable") or "").strip()
        if not key:
            continue
        if key in out:
            raise ValueError(f"输入字段名称重复: {key}")
        fallback = _fallback_from_source(ctx, f)
        val = ctx.inputs.get(key, fallback)
        empty = val is None or (isinstance(val, str) and not val.strip())
        if f.get("required") and empty:
            raise ValueError(f"缺少必填输入字段: {key}")
        # Optional blank form fields are absent values, not malformed JSON/numbers.
        if empty and (f.get("type") or "string").lower() != "string":
            val = None
        out[key] = coerce_value(val, f.get("type"), key)
    return out
