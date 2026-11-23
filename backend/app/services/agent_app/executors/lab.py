from app.core.execution import read_database
import json
import re

from fastapi import HTTPException

from ..workflow_run_ctx import WorkflowRunContext, resolve_dotted
from ._values import as_text
from ....services.autobi.lab_bailian_gateway import stream_lab_bailian_sse
from ....services.autobi.lab_runtime import build_lab_run_spec_from_project_id, collect_lab_run_json, new_lab_trace_context
from ...conversation_history import history_context_values


_PLACEHOLDER = re.compile(r"\{\{\s*([^}]+?)\s*\}\}")


def _resolve_features(ctx: WorkflowRunContext, value):
    if isinstance(value, str):
        full = _PLACEHOLDER.fullmatch(value.strip())
        if full:
            return resolve_dotted(ctx, full.group(1))
        return _PLACEHOLDER.sub(lambda match: as_text(resolve_dotted(ctx, match.group(1))), value)
    if isinstance(value, dict):
        return {key: _resolve_features(ctx, item) for key, item in value.items()}
    if isinstance(value, list):
        return [_resolve_features(ctx, item) for item in value]
    return value


def resolve_lab_inputs(ctx: WorkflowRunContext, cfg: dict) -> dict:
    """Build the validated runtime inputs, also used by trace snapshots."""
    def mapping_value(mapping):
        if mapping.get("source_mode", "ref") == "const":
            return mapping.get("const_value")
        ref = (mapping.get("source_var") or mapping.get("source_ref") or "").strip()
        return resolve_dotted(ctx, ref) if ref else None

    mappings = cfg.get("input_mapping") or []
    content_mappings = [mapping for mapping in mappings if
        (mapping.get("target_field") or mapping.get("target") or "content").strip() in ("content", "query")]
    user_message = ""
    for mapping in content_mappings:
        user_message = as_text(mapping_value(mapping))
    if not content_mappings and cfg.get("content_ref"):
        user_message = as_text(resolve_dotted(ctx, cfg["content_ref"]))

    pid = cfg.get("project_id")
    # Empty split branches are successful no-ops. Resolve features only if used.
    if not user_message.strip():
        return {"project_id": pid, "content": "", "features": {}}
    if pid is None:
        raise ValueError("实验室节点未选择项目")

    features = {}
    for mapping in mappings:
        if (mapping.get("target_field") or mapping.get("target") or "").strip() == "features":
            value = mapping_value(mapping)
            if value is None or value == "":
                features = {}
            else:
                try:
                    features = json.loads(value) if isinstance(value, str) else value
                except ValueError as exc:
                    raise ValueError("实验室 features 必须是有效 JSON 对象") from exc
                if not isinstance(features, dict):
                    raise ValueError("实验室 features 必须是 JSON 对象")

    features = _resolve_features(ctx, features)
    features.update(history_context_values(ctx.inputs))
    return {"project_id": int(pid), "content": user_message, "features": features}


def _select_outputs(cfg: dict, out: dict) -> dict:
    out_vars = cfg.get("output_vars") or []
    if isinstance(out_vars, list) and out_vars:
        keys = [item.get("key") if isinstance(item, dict) else item for item in out_vars]
        return {key: out[key] for key in keys if key in out}
    return out


async def execute(ctx: WorkflowRunContext, node: dict) -> dict:
    cfg = (node.get("data") or {}).get("lab_config") or {}
    inputs = resolve_lab_inputs(ctx, cfg)
    if not inputs["content"]:
        return _select_outputs(cfg, {"trace_id": "", "summary": "", "sql": "", "error": None})
    try:
        spec = await read_database(ctx.db, build_lab_run_spec_from_project_id, inputs["project_id"], content=inputs["content"], features=inputs["features"])
    except HTTPException as exc:
        raise ValueError(str(exc.detail)) from exc

    trace = new_lab_trace_context()
    from ...chatbi.diagnostics import capture_invocation, record_trace
    capture_invocation('lab', inputs, trace_id=trace.trace_id, parent_trace_id=getattr(ctx,'trace_id',None),
                       project_id=inputs['project_id'], node_id=node.get('id'))
    record_trace(trace.trace_id, {'status':'running','project_id':inputs['project_id'],
                                'parent_trace_id':ctx.trace_id}, kind='lab')
    # Trace metadata survives hidden thoughts, filtered output variables and errors.
    ctx.thought_events.append({"tag": "实验室追踪", "payload": {
        "type": "lab_trace", "trace_id": trace.trace_id,
        "node_id": node.get("id"), "project_id": inputs["project_id"],
    }})
    sse_output_thoughts = cfg.get("sse_output_thoughts", True) is not False
    is_stream = ctx.result_collector is not None or (
        (bool(ctx.stream) or str(ctx.run_id) == "stream") and sse_output_thoughts)
    result_events = []
    if is_stream:
        summary_parts = []
        sql = ""
        error = None
        async for raw in stream_lab_bailian_sse(ctx.db, spec, trace=trace):
            for block in raw.split("\n\n"):
                for line in block.split("\n"):
                    line = line.strip()
                    if not line.startswith("data:"):
                        continue
                    try:
                        obj = json.loads(line[5:].strip())
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(obj, dict):
                        continue
                    msg = obj.get("message") or {}
                    if not isinstance(msg, dict):
                        continue
                    if obj.get("status_code") in ("FAILED", "ERROR"):
                        error = error or as_text(msg.get("content")).strip() or "实验室执行失败"
                    elif msg.get("type") == "text" and msg.get("content"):
                        summary_parts.append(as_text(msg["content"]))
                        if ctx.result_collector is not None:
                            ctx.result_collector.append_text(node.get("id"), as_text(msg["content"]))
                    elif msg.get("type") == "sql_citations":
                        features = msg.get("features") or {}
                        if "sql" in features:
                            sql = as_text(features["sql"]).strip()
                        else:
                            for citation in features.get("sql_citations") or []:
                                if isinstance(citation, dict):
                                    sql = as_text(citation.get("sql")).strip()
                    payload = {key: obj.get(key) for key in ("id", "index", "finish", "status_code")}
                    payload["message"] = msg
                    result_events.append(payload)
                    if sse_output_thoughts:
                        ctx.thought_events.append({"tag": "实验室", "raw": "", "payload": payload})
        out = {"trace_id": trace.trace_id, "summary": "".join(summary_parts), "sql": sql, "error": error}
    else:
        res = await collect_lab_run_json(ctx.db, spec, trace=trace)
        for event in res.get("events") or []:
            if isinstance(event, dict):
                result_events.append(event)
            if sse_output_thoughts and isinstance(event, dict):
                ctx.thought_events.append({"tag": "实验室", "raw": "", "payload": event})
        out = {"trace_id": res.get("trace_id"), "summary": res.get("summary") or "", "sql": res.get("sql") or "", "error": res.get("error")}

    if ctx.result_collector is not None:
        ctx.result_collector.record_lab(node.get("id"), result_events, trace_id=trace.trace_id,
            query=inputs["content"], summary=out["summary"], sql=out["sql"], error=out["error"],
            output_enabled=cfg.get("sse_output_results", True) is not False)
    return _select_outputs(cfg, out)
