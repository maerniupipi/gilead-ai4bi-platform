import json

from ..workflow_run_ctx import WorkflowRunContext, substitute_template, resolve_dotted
from ._values import as_text, coerce_value


def _field_value(ctx: WorkflowRunContext, field: dict):
    if field.get("source_mode", "ref") == "const":
        return field.get("const_value", "")
    ref = (field.get("source_ref") or "").strip()
    return resolve_dotted(ctx, ref) if ref else ""


def _build_output_from_config(ctx: WorkflowRunContext, config: dict) -> dict:
    """Render declared content formats and preserve typed metadata values."""
    content_parts = []
    for index, field in enumerate(config.get("content_fields") or []):
        value = _field_value(ctx, field)
        fmt = field.get("output_format", "text")
        if fmt == "json":
            if isinstance(value, str):
                try:
                    value = json.loads(value)
                except ValueError as exc:
                    raise ValueError(f"输出内容第 {index + 1} 项不是有效 JSON") from exc
            content_parts.append(json.dumps(value, ensure_ascii=False, allow_nan=False))
        elif fmt in ("text", "markdown"):
            content_parts.append(as_text(value))
        else:
            raise ValueError(f"不支持的输出格式: {fmt}")

    metadata = {}
    for field in config.get("metadata_fields") or []:
        name = (field.get("name") or "").strip()
        if not name:
            continue
        if name in metadata:
            raise ValueError(f"输出元数据名称重复: {name}")
        metadata[name] = coerce_value(_field_value(ctx, field), field.get("type"), name)

    content = "\n\n".join(content_parts)
    if not content_parts and config.get("content_template"):
        content = substitute_template(ctx, config["content_template"])
    return {"content": content, "metadata": metadata}


async def execute(ctx: WorkflowRunContext, node: dict) -> dict:
    data = node.get("data") or {}
    cfg = data.get("output_config") or {}
    if cfg.get("content_fields") or cfg.get("metadata_fields"):
        result = _build_output_from_config(ctx, cfg)
    elif cfg.get("content_template"):
        result = {"content": substitute_template(ctx, cfg["content_template"]), "metadata": {}}
    else:
        result = {"content": as_text(ctx.final_output), "metadata": {}}
    return result
