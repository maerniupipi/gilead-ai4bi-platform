from app.core.execution import read_database
from ..workflow_run_ctx import WorkflowRunContext, resolve_dotted
from ....repositories.agent_app.repository import get_output_version_for_app, get_version_for_app
from ...conversation_history import history_context_values


async def execute(ctx: WorkflowRunContext, node: dict) -> dict:
    from ..workflow_engine import run_nested_agent_workflow

    data = node.get("data") or {}
    cfg = data.get("agent_config") or {}
    target_app = cfg.get("target_app_id")
    if target_app is None:
        raise ValueError("智能体节点未选择目标应用")
    target_app = int(target_app)

    vid = cfg.get("target_version_id")
    if vid is not None:
        target_version = int(vid)
        vrow = await read_database(ctx.db, get_version_for_app, target_app, target_version)
        if vrow is None:
            raise ValueError("目标版本不存在")
    else:
        vrow = await read_database(ctx.db, get_output_version_for_app, target_app)
        if vrow is None:
            raise ValueError("目标应用未配置输出版本，请指定版本")
        target_version = int(vrow.id)

    sub_inputs: dict = {}
    for m in cfg.get("input_mapping") or []:
        tfield = (m.get("target_field") or "").strip()
        if not tfield:
            continue
        mode = (m.get("source_mode") or "ref").strip()
        if mode == "const":
            sub_inputs[tfield] = m.get("const_value")
            continue
        ref = (m.get("source_var") or m.get("source_ref") or "").strip()
        if not ref:
            continue
        sub_inputs[tfield] = resolve_dotted(ctx, ref)

    history_context = history_context_values(ctx.inputs)
    sub_inputs.update(history_context)
    features = sub_inputs.get("features")
    if isinstance(features, dict):
        sub_inputs["features"] = {**features, **history_context}
    elif features is None:
        sub_inputs["features"] = dict(history_context)

    stack = list(ctx.call_stack)
    pair = (target_app, target_version)
    if pair in stack:
        raise ValueError("智能体调用出现环，已中止")
    stack.append(pair)

    sse_output_thoughts = cfg.get("sse_output_thoughts", True) is not False
    stream_nested = bool(ctx.stream and sse_output_thoughts)
    nested_thoughts = ctx.thought_events if stream_nested else []
    child_collector = None
    if ctx.result_collector is not None:
        from ..workflow_output import WorkflowOutput
        child_collector = WorkflowOutput(
            on_text=lambda delta: ctx.result_collector.append_text(node.get("id"), delta))
    try:
        nested = await run_nested_agent_workflow(
            ctx.db,
            agent_app_id=target_app,
            version_id=target_version,
            inputs=sub_inputs,
            call_stack=stack,
            stream=stream_nested,
            thought_events=nested_thoughts,
            parent_trace_id=ctx.trace_id or ctx.run_id,
            **({"result_collector": child_collector} if child_collector is not None else {}),
        )
    finally:
        if not stream_nested:
            # Even a failed/hidden nested workflow must retain all lab execution IDs.
            ctx.thought_events.extend(event for event in nested_thoughts
                if isinstance(event.get("payload"), dict) and event["payload"].get("type") == "lab_trace")

    if child_collector is not None:
        ctx.result_collector.record_agent(node.get("id"), child_collector,
            output_enabled=cfg.get("sse_output_results", True) is not False)
    exports = nested.get("exports") or {}
    output = nested.get("output")
    child_trace_id = nested.get("child_trace_id")

    out: dict = {}
    if child_trace_id:
        out["_child_trace_id"] = child_trace_id
    # Note: _child_trace_id will be stripped from output_snapshot by the engine
    # (captured into step_rec["child_trace_ids"] before saving)
    output_mapping = cfg.get("output_mapping") or []

    for m in output_mapping:
        src = (m.get("source_field") or "").strip()
        tgt = (m.get("target_var") or "").strip()
        if not src or not tgt:
            continue
        if tgt in out:
            raise ValueError(f"智能体输出变量名称重复: {tgt}")
        if src in exports:
            val = exports[src]
        elif src in ("output", "content"):
            val = output
        else:
            candidates = [value for key, value in exports.items() if key.endswith(f".{src}")]
            if len(candidates) > 1:
                raise ValueError(f"智能体输出字段 {src} 存在多个来源，请使用完整的节点名.字段")
            if not candidates:
                raise ValueError(f"智能体未返回输出字段: {src}")
            val = candidates[0]
        out[tgt] = val

    if not output_mapping:
        # Trace metadata must not suppress the public default output.
        out["output"] = output if output is not None else ""
        out["content"] = out["output"]  # Compatibility with older workflows.

    return out
