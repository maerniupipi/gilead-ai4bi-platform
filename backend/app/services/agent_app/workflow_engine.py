"""智能体工作流执行：拓扑排序 + 节点分发 + Redis trace。"""
from __future__ import annotations
from app.core.execution import read_database, bounded_execution, TRACE_WORK
from app.core.trace_writer import write_trace

import asyncio
import contextlib
import json
import logging
import re
import time
import uuid
from typing import Any, Dict, List, Optional, Set, Tuple, AsyncGenerator

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ...core.redis_client import agent_run_trace_get, agent_run_trace_set
from ...repositories.agent_app.repository import get_version_for_app
from .trace_service import save_workflow_trace
from .executors.agent import execute as ex_agent
from .executors.atomic import (
    execute as ex_atomic,
    _build_request_body as build_atomic_request_body,
    _build_context_vars as build_atomic_context_vars,
    _resolve_knowledge_base_id as resolve_atomic_knowledge_base_id,
)
from .executors.external_api import execute as ex_external_api, build_api_request
from .executors.lab import execute as ex_lab, resolve_lab_inputs
from .executors.llm import execute as ex_llm, build_llm_request
from .executors.output import execute as ex_output, _build_output_from_config
from .executors.script import execute as ex_script
from .executors.script import resolve_script_inputs
from .executors.selector import execute as ex_selector
from .executors.start import execute as ex_start
from .executors.user_input import execute as ex_user_input
from .workflow_run_ctx import (
    WorkflowRunContext,
    build_var_name_maps,
    flatten_exports,
    reachable_from,
    resolve_dotted,
    substitute_llm_prompt,
    substitute_template,
    template_text,
    topological_order,
)

_KIND_HANDLERS = {
    "start": ex_start,
    "userInput": ex_user_input,
    "llm": ex_llm,
    "script": ex_script,
    "agent": ex_agent,
    "atomic": ex_atomic,
    "lab": ex_lab,
    "externalApi": ex_external_api,
    "selector": ex_selector,
    "output": ex_output,
}

logger = logging.getLogger(__name__)

_TEMPLATE_RE = re.compile(r"\{\{\s*([^}]+?)\s*\}\}")


def _coerce_atomic_const_value(raw: Any) -> Any:
    if raw is None:
        return None
    if not isinstance(raw, str):
        return raw
    text = raw.strip()
    if text == "":
        return ""
    try:
        return json.loads(text)
    except Exception:
        return raw


def _resolve_atomic_template_value(ctx: WorkflowRunContext, raw: Any) -> Any:
    if isinstance(raw, dict):
        return {k: _resolve_atomic_template_value(ctx, v) for k, v in raw.items()}
    if isinstance(raw, list):
        return [_resolve_atomic_template_value(ctx, v) for v in raw]
    if not isinstance(raw, str):
        return raw

    stripped = raw.strip()
    full = _TEMPLATE_RE.fullmatch(stripped)
    if full:
        return resolve_dotted(ctx, full.group(1).strip())

    def repl(m: re.Match) -> str:
        val = resolve_dotted(ctx, m.group(1).strip())
        return "" if val is None else str(val)

    return _TEMPLATE_RE.sub(repl, raw)


def _build_atomic_request_snapshot(ctx: WorkflowRunContext, cfg: Dict[str, Any]) -> Dict[str, Any]:
    request_body = build_atomic_request_body(ctx, cfg)
    knowledge_base_id = None
    if cfg.get("capability") == "generate-sql":
        request_body["context"] = build_atomic_context_vars(ctx, cfg)
        request_body["system_prompt"] = cfg.get("system_prompt") or request_body.get("system_prompt") or ""
        kb_row = next((row for row in cfg.get("input_vars") or [] if row.get("key") == "knowledge_base_id"), None)
        if kb_row and (kb_row.get("source_mode") == "ref" or kb_row.get("const_value") not in (None, "")):
            knowledge_base_id = resolve_atomic_knowledge_base_id(ctx, cfg)
    else:
        knowledge_base_id = resolve_atomic_knowledge_base_id(ctx, cfg)
    return {
        "capability": cfg.get("capability"),
        "knowledge_base_id": knowledge_base_id,
        "request_body": request_body,
    }


def _build_llm_bindings_snapshot(ctx: WorkflowRunContext, cfg: Dict[str, Any]) -> Dict[str, Any]:
    bindings: Dict[str, Any] = {}
    for p in cfg.get("input_params") or []:
        name = (p.get("variable") or "").strip()
        if not name:
            continue
        if (p.get("source_mode") or "ref").strip().lower() == "const":
            bindings[name] = {"source_mode": "const", "const_value": p.get("default", "")}
        else:
            bindings[name] = {"source_mode": "ref", "ref": (p.get("ref") or "").strip()}
    for name, spec in (cfg.get("param_bindings") or {}).items():
        if name and (name not in bindings or (isinstance(spec, dict) and (
            spec.get("source_mode") == "const" or (spec.get("ref") or "").strip()
        ))):
            bindings[name] = spec
    return bindings


def _build_script_input_snapshot(ctx: WorkflowRunContext, cfg: Dict[str, Any]) -> Dict[str, Any]:
    kwargs = resolve_script_inputs(ctx, cfg)
    return {"kwargs": kwargs, "code_line_count": len((cfg.get("code") or "").splitlines())}


def _build_agent_input_snapshot(ctx: WorkflowRunContext, cfg: Dict[str, Any]) -> Dict[str, Any]:
    sub_inputs: Dict[str, Any] = {}
    for m in cfg.get("input_mapping") or []:
        tfield = (m.get("target_field") or "").strip()
        if not tfield:
            continue
        if (m.get("source_mode") or "ref").strip() == "const":
            sub_inputs[tfield] = m.get("const_value")
        else:
            ref = (m.get("source_var") or m.get("source_ref") or "").strip()
            if ref:
                sub_inputs[tfield] = resolve_dotted(ctx, ref)
    return {
        "target_app_id": cfg.get("target_app_id"),
        "target_version_id": cfg.get("target_version_id"),
        "inputs": sub_inputs,
    }


def _coerce_json_object(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            val = json.loads(raw)
            return val if isinstance(val, dict) else {}
        except Exception:
            return {}
    return {}


def _build_lab_input_snapshot(ctx: WorkflowRunContext, cfg: Dict[str, Any]) -> Dict[str, Any]:
    return resolve_lab_inputs(ctx, cfg)


def _build_external_api_input_snapshot(ctx: WorkflowRunContext, cfg: Dict[str, Any]) -> Dict[str, Any]:
    request = build_api_request(ctx, cfg)
    request["headers"] = {
        key: "[REDACTED]" if key.lower() in {"authorization", "proxy-authorization", "cookie", "x-api-key", "api-key"} else value
        for key, value in request["headers"].items()
    }
    return request


def _build_selector_input_snapshot(ctx: WorkflowRunContext, cfg: Dict[str, Any]) -> Dict[str, Any]:
    cases: List[Dict[str, Any]] = []
    for case in cfg.get("cases") or []:
        conditions = []
        for cond in case.get("conditions") or []:
            ref = (cond.get("ref") or "").strip()
            try:
                actual = resolve_dotted(ctx, ref) if ref else None
            except Exception:
                actual = None
            conditions.append({
                "ref": ref,
                "actual": actual,
                "op": cond.get("op") or "eq",
                "value": cond.get("value") if cond.get("op") not in ("empty", "not_empty") else "",
            })
        cases.append({"id": case.get("id"), "relation": case.get("relation") or "AND", "conditions": conditions})
    return {"cases": cases}


def _build_output_input_snapshot(ctx: WorkflowRunContext, cfg: Dict[str, Any]) -> Dict[str, Any]:
    tpl = cfg.get("content_template") or ""
    if cfg.get("content_fields") or cfg.get("metadata_fields"):
        result = _build_output_from_config(ctx, cfg)
        return {"rendered_content": result["content"], "metadata": result["metadata"]}
    return {"content_template": tpl, "rendered_content": substitute_template(ctx, tpl) if tpl else ctx.final_output or "", "metadata": {}}


def _parse_workflow(version_row) -> Tuple[List[dict], List[dict]]:
    raw = getattr(version_row, "workflow_json", None) or {}
    if not isinstance(raw, dict):
        raw = {}
    nodes = raw.get("nodes") or []
    edges = raw.get("edges") or []
    if not isinstance(nodes, list):
        nodes = []
    if not isinstance(edges, list):
        edges = []
    return nodes, edges


def _validate_graph(nodes: List[dict], edges: Optional[List[dict]] = None) -> Tuple[str, str]:
    ids = set()
    for node in nodes:
        if not isinstance(node, dict) or not isinstance(node.get("id"), str) or not node["id"].strip():
            raise ValueError("节点必须包含非空字符串 ID")
        if node["id"] in ids:
            raise ValueError(f"节点 ID 重复: {node['id']}")
        ids.add(node["id"])
        data = node.get("data")
        if not isinstance(data, dict) or not isinstance(data.get("kind"), str) or data["kind"] not in _KIND_HANDLERS:
            raise ValueError(f"未知节点类型: {node['id']}")
    start_ids = [n["id"] for n in nodes if (n.get("data") or {}).get("kind") == "start"]
    if len(start_ids) != 1:
        raise ValueError("工作流必须有且仅有一个「开始」节点")
    start_id = start_ids[0]
    outs = [n for n in nodes if (n.get("data") or {}).get("kind") == "output"]
    if len(outs) < 1:
        raise ValueError("工作流至少需要一个「输出」节点")
    out_nid = outs[0]["id"]
    build_var_name_maps(nodes)
    if edges is not None:
        for edge in edges:
            if (not isinstance(edge, dict) or not isinstance(edge.get("source"), str)
                    or not isinstance(edge.get("target"), str)
                    or edge["source"] not in ids or edge["target"] not in ids):
                raise ValueError("工作流连线引用了不存在的节点，请删除失效连线")
        reachable = reachable_from(start_id, edges)
        if not any(node["id"] in reachable for node in outs):
            raise ValueError("输出节点必须从「开始」可达")
        topological_order(ids, edges)
    return start_id, out_nid


def assert_runnable_workflow(version_row) -> None:
    """启动异步执行前同步校验，避免无效任务入队（与 run_agent_workflow 前置条件一致）。"""
    nodes, edges = _parse_workflow(version_row)
    if not nodes:
        raise ValueError("工作流为空，请先设计画布")
    _validate_graph(nodes, edges)


def _step_input_snapshot(ctx: WorkflowRunContext, node: dict, kind: str) -> Any:
    """调试 trace 入参摘要（写入 Redis，避免整段 Prompt 过大时可再截断）。"""
    data = node.get("data") or {}
    nid = node.get("id")
    if kind == "start":
        return {"kind": "start"}
    if kind == "userInput":
        return {"inputs": dict(ctx.inputs)}
    if kind == "llm":
        cfg = data.get("llm_config") or {}
        bindings = _build_llm_bindings_snapshot(ctx, cfg)
        request = build_llm_request(ctx, cfg)
        return {
            "provider_id": cfg.get("provider_id"),
            "model_name": cfg.get("model_name"),
            "input_values": {
                name: (
                    spec.get("const_value")
                    if isinstance(spec, dict) and spec.get("source_mode") == "const"
                    else (
                        resolve_dotted(ctx, spec.get("ref"))
                        if isinstance(spec, dict) and spec.get("ref")
                        else None
                    )
                )
                for name, spec in bindings.items()
            },
            "use_user_prompt_template": bool(cfg.get("use_user_prompt_template")),
            "system_prompt": request.system or "",
            "user_prompt": request.message,
            "model_params": {
                "temperature": cfg.get("temperature", 0.7),
                "max_tokens": cfg.get("max_tokens", 2000),
                "top_p": cfg.get("top_p", 0.9),
                "stop_words": request.stop_words,
            },
        }
    if kind == "script":
        cfg = data.get("script_config") or {}
        return _build_script_input_snapshot(ctx, cfg)
    if kind == "agent":
        cfg = data.get("agent_config") or {}
        return _build_agent_input_snapshot(ctx, cfg)
    if kind == "lab":
        cfg = data.get("lab_config") or {}
        return _build_lab_input_snapshot(ctx, cfg)
    if kind == "atomic":
        cfg = data.get("atomic_config") or {}
        try:
            return _build_atomic_request_snapshot(ctx, cfg)
        except Exception as e:
            return {
                "capability": cfg.get("capability"),
                "error": f"解析原子能力入参失败: {e}",
            }
    if kind == "externalApi":
        cfg = data.get("api_config") or {}
        return _build_external_api_input_snapshot(ctx, cfg)
    if kind == "output":
        cfg = data.get("output_config") or {}
        return _build_output_input_snapshot(ctx, cfg)
    if kind == "selector":
        cfg = data.get("selector_config") or {}
        return _build_selector_input_snapshot(ctx, cfg)
    return {"kind": kind, "node_id": nid}


def _safe_step_input_snapshot(ctx: WorkflowRunContext, node: dict, kind: str) -> Any:
    try:
        return _step_input_snapshot(ctx, node, kind)
    except Exception as e:
        return {"error": f"解析入参快照失败: {e}"}


def _prune_selector_out_edges(edges: List[dict], selector_nid: str, chosen_handle: str) -> List[dict]:
    """移除选择器节点上非选中分支的出边（sourceHandle 与 branch_handle 对齐）。"""
    ch = str(chosen_handle or "else")
    out: List[dict] = []
    for e in edges:
        if e.get("source") != selector_nid:
            out.append(e)
            continue
        sh = e.get("sourceHandle") or e.get("source_handle")
        if sh is None:
            out.append(e)
        elif str(sh) == ch:
            out.append(e)
    return out


def _ready_nodes(reachable_ids: Set[str], active_edges: List[dict], context: Dict[str, Any]) -> List[str]:
    preds: Dict[str, List[str]] = {nid: [] for nid in reachable_ids}
    for e in active_edges:
        s, t = e.get("source"), e.get("target")
        if s in reachable_ids and t in reachable_ids:
            preds.setdefault(t, []).append(s)
    ready: List[str] = []
    for nid in reachable_ids:
        if nid in context:
            continue
        ps = preds.get(nid) or []
        if all(p in context for p in ps):
            ready.append(nid)
    return ready


def _update_final_output(ctx: WorkflowRunContext, completed_ids: List[str]) -> None:
    """Commit fallback text deterministically; explicit output nodes always win."""
    output_results = []
    for nid in sorted(completed_ids):
        result = ctx.context[nid]
        if (ctx.nodes_by_id[nid].get("data") or {}).get("kind") == "output":
            output_results.append(result)
        else:
            value = result.get("text") if result.get("text") is not None else result.get("content")
            if value is not None:
                ctx.final_output = template_text(value)
    if output_results:
        result = output_results[0]
        value = result.get("content") if "content" in result else result.get("text")
        ctx.final_output = template_text(value)


async def _run_workflow_dynamic(
    ctx: WorkflowRunContext,
    *,
    start_id: str,
    out_nid: Optional[str],
    out_nids: Optional[Set[str]] = None,
    trace_payload: Optional[Dict[str, Any]] = None,
    trace_run_id: Optional[str] = None,
    mysql_trace_id: Optional[str] = None,
) -> Optional[str]:
    """
    按拓扑就绪集执行；选择器节点执行后剪枝出边。
    成功返回 None，失败返回错误文案。
    """
    nodes_by_id = ctx.nodes_by_id
    edge_state: Dict[str, Any] = {"edges": [dict(e) for e in (ctx.edges or [])]}
    output_ids = set(out_nids or ({out_nid} if out_nid else set()))
    original_reachable = reachable_from(start_id, ctx.edges)

    async def _run_one_node(
        nid: str, step_rec: Optional[Dict[str, Any]]
    ) -> Tuple[str, Dict[str, Any], Optional[str]]:
        node = nodes_by_id.get(nid) or {}
        kind = (node.get("data") or {}).get("kind") or ""
        handler = _KIND_HANDLERS.get(kind)
        if not handler:
            err = f"未知节点类型: {kind}"
            if step_rec:
                step_rec["status"] = "error"
                step_rec["error"] = err
            return nid, {}, err
        step_t0 = time.perf_counter()
        try:
            result = await handler(ctx, node)
            if not isinstance(result, dict):
                result = {}
            if step_rec:
                step_rec["status"] = "done"
                child_tid = result.pop("_child_trace_id", None) if isinstance(result, dict) else None
                step_rec["output_snapshot"] = result
                step_rec["elapsed_ms"] = int((time.perf_counter() - step_t0) * 1000)
                if child_tid:
                    step_rec.setdefault("child_trace_ids", []).append(child_tid)
            if kind == "selector":
                chosen = result.get("branch_handle") or "else"
                edge_state["edges"] = _prune_selector_out_edges(edge_state["edges"], nid, chosen)
            return nid, result, None
        except Exception as e:
            msg = str(e.detail) if isinstance(e, HTTPException) else str(e)
            if step_rec:
                step_rec["status"] = "error"
                step_rec["error"] = msg
                step_rec["elapsed_ms"] = int((time.perf_counter() - step_t0) * 1000)
            return nid, {}, msg

    while True:
        rch = reachable_from(start_id, edge_state["edges"])
        ctx.skipped_node_ids = original_reachable - rch
        if ctx.result_collector is not None:
            ctx.result_collector.update_execution(ctx, edge_state["edges"])
        if output_ids and any(nid in ctx.context for nid in output_ids):
            break
        ready = _ready_nodes(rch, edge_state["edges"], ctx.context)
        ready.sort()
        if ctx.result_collector is not None:
            ctx.result_collector.update_execution(ctx, edge_state["edges"], ready)
        if not ready:
            if output_ids and not any(nid in rch for nid in output_ids):
                return "输出节点在当前分支下不可达，请检查连线与条件"
            return "工作流无法继续执行（可能存在环或未满足依赖）"

        step_recs: Dict[str, Dict[str, Any]] = {}
        if trace_payload is not None:
            for nid in ready:
                node = nodes_by_id.get(nid) or {}
                kind = (node.get("data") or {}).get("kind") if node else ""
                rec: Dict[str, Any] = {
                    "node_id": nid,
                    "kind": kind,
                    "var_name": ctx.id_to_var.get(nid),
                    "label": (node.get("data") or {}).get("label") if node else None,
                    "status": "running",
                    "started_at": int(time.time() * 1000),
                    "elapsed_ms": 0,
                    "input_snapshot": _safe_step_input_snapshot(ctx, node, kind or ""),
                    "output_snapshot": None,
                    "error": None,
                }
                trace_payload["steps"].append(rec)
                step_recs[nid] = rec
            if trace_run_id:
                await write_trace(agent_run_trace_set, trace_run_id, trace_payload)
            if mysql_trace_id and trace_payload is not None:
                try:
                    await write_trace(save_workflow_trace, mysql_trace_id, trace_payload)
                except Exception:
                    logger.warning("MySQL trace write failed (non-fatal) trace_id=%s", mysql_trace_id)

        results = await asyncio.gather(*[_run_one_node(nid, step_recs.get(nid)) for nid in ready])
        first_err: Optional[str] = None
        for nid, result, err in results:
            if err and first_err is None:
                first_err = err
            if not err:
                ctx.context[nid] = result
        _update_final_output(ctx, [nid for nid, _, err in results if not err])
        if trace_payload is not None and trace_run_id:
            await write_trace(agent_run_trace_set, trace_run_id, trace_payload)
        if mysql_trace_id and trace_payload is not None:
            try:
                await write_trace(save_workflow_trace, mysql_trace_id, trace_payload)
            except Exception:
                logger.warning("MySQL trace write failed (non-fatal) trace_id=%s", mysql_trace_id)
        if first_err:
            return first_err
    return None


async def run_nested_agent_workflow(
    db: Session,
    *,
    agent_app_id: int,
    version_id: int,
    inputs: Dict[str, Any],
    call_stack: List[Tuple[int, int]],
    stream: bool = False,
    thought_events: Optional[List[dict]] = None,
    parent_trace_id: Optional[str] = None,
    result_collector: Any = None,
) -> Dict[str, Any]:
    """供智能体节点递归调用；生成独立 trace_id 并写 Redis + MySQL。返回 exports + output + child_trace_id。"""
    t0 = time.perf_counter()
    v = await read_database(db, get_version_for_app, agent_app_id, version_id)
    if v is None:
        raise ValueError("目标版本不存在")
    nodes, edges = _parse_workflow(v)
    if not nodes:
        raise ValueError("目标工作流为空")
    start_id, _ = _validate_graph(nodes, edges)
    var_to_id, id_to_var = build_var_name_maps(nodes)
    reachable = reachable_from(start_id, edges)
    out_nid = None
    for n in nodes:
        if (n.get("data") or {}).get("kind") == "output":
            out_nid = n["id"]
            break
    out_nids = {n["id"] for n in nodes if (n.get("data") or {}).get("kind") == "output"}
    order = topological_order(reachable, edges)
    nodes_by_id = {n["id"]: n for n in nodes if n.get("id")}

    # resolve app name
    app_name = None
    try:
        from ...models.agent_app import AgentApp
        app_row = await read_database(db, lambda session: session.query(AgentApp).filter(AgentApp.id == agent_app_id).first())
        if app_row:
            app_name = app_row.name
    except Exception:
        pass

    child_trace_id = str(uuid.uuid4())
    from ..chatbi.diagnostics import capture_invocation, record_trace
    from .input_usage import workflow_input_usage
    capture_invocation('nested_agent', inputs, trace_id=child_trace_id, parent_trace_id=parent_trace_id,
                       app_id=agent_app_id, version_id=version_id,
                       input_usage=workflow_input_usage(nodes, inputs))
    record_trace(child_trace_id, {'parent_trace_id':parent_trace_id,'app_id':agent_app_id,'version_id':version_id,'status':'running'})
    child_run_id = "stream" if stream else child_trace_id

    trace_payload: Dict[str, Any] = {
        "run_id": child_run_id,
        "trace_id": child_trace_id,
        "app_id": agent_app_id,
        "version_id": version_id,
        "app_name": app_name,
        "parent_trace_id": parent_trace_id,
        "status": "running",
        "steps": [],
        "nodes": nodes,
        "edges": edges,
        "output": None,
        "error": None,
        "elapsed_ms": 0,
        "created_at": int(time.time() * 1000),
    }
    if not stream:
        await write_trace(agent_run_trace_set, child_run_id, trace_payload)

    ctx = WorkflowRunContext(
        db=db,
        run_id=child_run_id,
        trace_id=child_trace_id,
        agent_app_id=agent_app_id,
        version_id=version_id,
        inputs=dict(inputs or {}),
        call_stack=list(call_stack),
        nodes_by_id=nodes_by_id,
        nodes=nodes,
        edges=edges,
        var_to_id=var_to_id,
        id_to_var=id_to_var,
        thought_events=thought_events if thought_events is not None else [],
        stream=stream,
        result_collector=result_collector,
    )

    try:
        err = await _run_workflow_dynamic(
            ctx,
            start_id=start_id,
            out_nid=out_nid,
            out_nids=out_nids,
            trace_payload=trace_payload,
            trace_run_id=child_run_id if not stream else None,
            mysql_trace_id=child_trace_id,
        )
    except asyncio.CancelledError:
        trace_payload.update(status="stopped", error="执行已停止",
                             elapsed_ms=int((time.perf_counter() - t0) * 1000))
        for step in trace_payload["steps"]:
            if step.get("status") == "running":
                step.update(status="stopped", error="执行已停止")
        if not stream:
            await write_trace(agent_run_trace_set, child_run_id, trace_payload)
        await write_trace(save_workflow_trace, child_trace_id, trace_payload)
        raise
    if err:
        elapsed = int((time.perf_counter() - t0) * 1000)
        trace_payload.update({"status": "error", "error": err, "elapsed_ms": elapsed})
        if not stream:
            await write_trace(agent_run_trace_set, child_run_id, trace_payload)
        try:
            await write_trace(save_workflow_trace, child_trace_id, trace_payload)
        except Exception:
            logger.warning("MySQL trace write failed (non-fatal) trace_id=%s", child_trace_id)
        raise ValueError(err)

    elapsed = int((time.perf_counter() - t0) * 1000)
    trace_payload.update(
        {
            "status": "done",
            "output": ctx.final_output,
            "error": None,
            "elapsed_ms": elapsed,
        }
    )
    if not stream:
        await write_trace(agent_run_trace_set, child_run_id, trace_payload)
    try:
        await write_trace(save_workflow_trace, child_trace_id, trace_payload)
    except Exception:
        logger.warning("MySQL trace write failed (non-fatal) trace_id=%s", child_trace_id)

    if result_collector is not None:
        result_collector.finish(ctx)
    exports = flatten_exports(ctx.context, id_to_var, ctx.final_output)
    exports["content"] = ctx.final_output if ctx.final_output is not None else ""
    executed_outputs = sorted(nid for nid in out_nids if nid in ctx.context)
    exports["metadata"] = ctx.context[executed_outputs[0]].get("metadata", {}) if executed_outputs else {}
    return {
        "output": ctx.final_output,
        "exports": exports,
        "child_trace_id": child_trace_id,
    }


@bounded_execution
async def run_agent_workflow(
    db: Session,
    *,
    agent_app_id: int,
    version_id: int,
    inputs: Dict[str, Any],
    run_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    执行工作流并写入 Redis trace（每步写入，供前端轮询）。
    返回 WorkflowRunOut 字典字段。
    run_id 由调用方传入时须已写入 Redis 初始壳（与 POST /run 一致）。
    """
    t0 = time.perf_counter()
    run_id = run_id or str(uuid.uuid4())
    trace_id = run_id

    v = await read_database(db, get_version_for_app, agent_app_id, version_id)
    if v is None:
        raise ValueError("版本不存在")

    # resolve app name
    app_name = None
    try:
        from ...models.agent_app import AgentApp
        app_row = await read_database(db, lambda session: session.query(AgentApp).filter(AgentApp.id == agent_app_id).first())
        if app_row:
            app_name = app_row.name
    except Exception:
        pass

    payload: Dict[str, Any] = {
        "run_id": run_id,
        "trace_id": trace_id,
        "app_id": agent_app_id,
        "version_id": version_id,
        "app_name": app_name,
        "status": "running",
        "steps": [],
        "nodes": None,
        "edges": None,
        "output": None,
        "error": None,
        "elapsed_ms": 0,
        "parent_trace_id": None,
        "created_at": int(time.time() * 1000),
    }
    await write_trace(agent_run_trace_set, run_id, payload)

    try:
        nodes, edges = _parse_workflow(v)
        if not nodes:
            raise ValueError("工作流为空，请先设计画布")
        start_id, _ = _validate_graph(nodes, edges)
        var_to_id, id_to_var = build_var_name_maps(nodes)
        reachable = reachable_from(start_id, edges)
        out_nid = None
        out_nids: Set[str] = set()
        for n in nodes:
            if (n.get("data") or {}).get("kind") == "output":
                out_nids.add(n["id"])
                if out_nid is None:
                    out_nid = n["id"]
        if out_nids and not any(nid in reachable for nid in out_nids):
            raise ValueError("输出节点必须从「开始」可达")
        topological_order(reachable, edges)
        nodes_by_id = {n["id"]: n for n in nodes if n.get("id")}

        payload["nodes"] = nodes
        payload["edges"] = edges

        ctx = WorkflowRunContext(
            db=db,
            run_id=run_id,
            trace_id=trace_id,
            agent_app_id=agent_app_id,
            version_id=version_id,
            inputs=dict(inputs or {}),
            call_stack=[(agent_app_id, version_id)],
            nodes_by_id=nodes_by_id,
            nodes=nodes,
            edges=edges,
            var_to_id=var_to_id,
            id_to_var=id_to_var,
        )

        dyn_err = await _run_workflow_dynamic(
            ctx,
            start_id=start_id,
            out_nid=out_nid,
            out_nids=out_nids,
            trace_payload=payload,
            trace_run_id=run_id,
            mysql_trace_id=trace_id,
        )
        if dyn_err:
            raise ValueError(dyn_err)

        elapsed = int((time.perf_counter() - t0) * 1000)
        payload.update(
            {
                "status": "done",
                "output": ctx.final_output,
                "error": None,
                "elapsed_ms": elapsed,
            }
        )
        await write_trace(agent_run_trace_set, run_id, payload)
        try:
            await write_trace(save_workflow_trace, trace_id, payload)
        except Exception:
            logger.warning("MySQL trace write failed (non-fatal) trace_id=%s", trace_id)
        return {
            "run_id": run_id,
            "trace_id": trace_id,
            "output": ctx.final_output,
            "status": "done",
            "error": None,
            "elapsed_ms": elapsed,
        }
    except asyncio.CancelledError:
        payload.update(status="stopped", error="执行已停止",
                       elapsed_ms=int((time.perf_counter() - t0) * 1000))
        for step in payload["steps"]:
            if step.get("status") == "running":
                step.update(status="stopped", error="执行已停止")
        await write_trace(agent_run_trace_set, run_id, payload)
        await write_trace(save_workflow_trace, trace_id, payload)
        raise
    except Exception as e:
        elapsed = int((time.perf_counter() - t0) * 1000)
        msg = str(e.detail) if isinstance(e, HTTPException) else str(e)
        payload.update(
            {
                "status": "error",
                "error": msg,
                "elapsed_ms": elapsed,
            }
        )
        await write_trace(agent_run_trace_set, run_id, payload)
        try:
            await write_trace(save_workflow_trace, trace_id, payload)
        except Exception:
            logger.warning("MySQL trace write failed (non-fatal) trace_id=%s", trace_id)
        return {
            "run_id": run_id,
            "trace_id": trace_id,
            "output": None,
            "status": "error",
            "error": msg,
            "elapsed_ms": elapsed,
        }


def get_agent_run_trace(run_id: str) -> Optional[dict]:
    return agent_run_trace_get(run_id)


@bounded_execution
async def run_agent_workflow_stream(
    db: Session,
    agent_app_id: int,
    version_id: int,
    inputs: Dict[str, Any],
    *,
    emit_trace: bool = False,
    result_collector: Any = None,
) -> AsyncGenerator[str, None]:
    """
    流式执行工作流，每次节点完成时 yield 出进度。
    """
    import json

    t0 = time.perf_counter()
    stream_trace_id = str(uuid.uuid4())
    from ..chatbi.diagnostics import capture_invocation, record_trace
    record_trace(stream_trace_id, {'app_id':agent_app_id,'version_id':version_id,'status':'running'})

    # resolve app name
    app_name = None
    try:
        from ...models.agent_app import AgentApp
        app_row = await read_database(db, lambda session: session.query(AgentApp).filter(AgentApp.id == agent_app_id).first())
        if app_row:
            app_name = app_row.name
    except Exception:
        pass

    v = await read_database(db, get_version_for_app, agent_app_id, version_id)
    if v is None:
        yield "data: " + json.dumps({"error": "版本不存在"}) + "\n\n"
        return

    try:
        nodes, edges = _parse_workflow(v)
        if not nodes:
            yield "data: " + json.dumps({"error": "工作流为空，请先设计画布"}) + "\n\n"
            return
        start_id, out_nid = _validate_graph(nodes, edges)
    except ValueError as e:
        yield "data: " + json.dumps({"error": str(e)}) + "\n\n"
        return

    from .input_usage import workflow_input_usage
    capture_invocation('workflow', inputs, trace_id=stream_trace_id, app_id=agent_app_id, version_id=version_id,
                       input_usage=workflow_input_usage(nodes, inputs))

    # Init MySQL trace
    try:
        await write_trace(save_workflow_trace, stream_trace_id, {
            "run_id": "stream",
            "trace_id": stream_trace_id,
            "app_id": agent_app_id,
            "version_id": version_id,
            "app_name": app_name,
            "status": "running",
            "steps": [],
            "nodes": nodes,
            "edges": edges,
            "output": None,
            "error": None,
            "elapsed_ms": 0,
            "parent_trace_id": None,
            "created_at": int(time.time() * 1000),
        })
    except Exception:
        logger.warning("MySQL trace init failed (non-fatal) trace_id=%s", stream_trace_id)

    if emit_trace:
        yield "data: " + json.dumps({"type": "trace_id", "trace_id": stream_trace_id}) + "\n\n"

    var_to_id, id_to_var = build_var_name_maps(nodes)
    reachable = reachable_from(start_id, edges)
    out_nids = {n["id"] for n in nodes if (n.get("data") or {}).get("kind") == "output" and n.get("id")}
    nodes_by_id = {n["id"]: n for n in nodes if n.get("id")}

    # Collect step summaries for final MySQL write
    stream_steps: List[Dict[str, Any]] = []

    ctx = WorkflowRunContext(
        db=db,
        run_id="stream",
        trace_id=stream_trace_id,
        agent_app_id=agent_app_id,
        version_id=version_id,
        inputs=dict(inputs or {}),
        call_stack=[(agent_app_id, version_id)],
        nodes_by_id=nodes_by_id,
        nodes=nodes,
        edges=edges,
        var_to_id=var_to_id,
        id_to_var=id_to_var,
        stream=True,
        result_collector=result_collector,
    )

    edge_state = {"edges": list(edges)}
    thought_index = 0

    async def run_node(nid: str):
        node = nodes_by_id.get(nid)
        if not node:
            return {}, "节点不存在"
        kind = (node.get("data") or {}).get("kind") or ""
        handler = _KIND_HANDLERS.get(kind)
        if not handler:
            return {}, f"未知节点类型: {kind}"
        try:
            result = await handler(ctx, node)
            if not isinstance(result, dict):
                result = {}
            return result, None
        except Exception as e:
            msg = str(e)
            return {}, msg

    def _serialize_thought_events(nid: str, start: int) -> List[str]:
        events: List[str] = []
        for event in ctx.thought_events[start:]:
            events.append("data: " + json.dumps({
                "type": "thought",
                "node_id": nid,
                "thought": event,
            }, ensure_ascii=False) + "\n\n")
        return events

    def _serialize_result_deltas():
        if result_collector is not None:
            for delta in result_collector.drain_text():
                yield "data: " + json.dumps({"type": "result_delta", "content": delta}, ensure_ascii=False) + "\n\n"

    completed = False
    try:
        while True:
            rch = reachable_from(start_id, edge_state["edges"])
            ctx.skipped_node_ids = reachable - rch
            if result_collector is not None:
                result_collector.update_execution(ctx, edge_state["edges"])
            if out_nids and any(nid in ctx.context for nid in out_nids):
                break
            ready = _ready_nodes(rch, edge_state["edges"], ctx.context)
            ready.sort()
            if result_collector is not None:
                result_collector.update_execution(ctx, edge_state["edges"], ready)
            if not ready:
                if out_nids and not any(nid in rch for nid in out_nids):
                    raise ValueError("输出节点在当前分支下不可达，请检查连线与条件")
                raise ValueError("工作流无法继续执行（可能存在环或未满足依赖）")

            for nid in ready:
                node = nodes_by_id.get(nid) or {}
                kind = (node.get("data") or {}).get("kind") or ""
                step_rec = {
                    "node_id": nid,
                    "kind": kind,
                    "var_name": id_to_var.get(nid),
                    "label": (node.get("data") or {}).get("label"),
                    "status": "running",
                    "started_at": int(time.time() * 1000),
                    "elapsed_ms": 0,
                    "input_snapshot": _safe_step_input_snapshot(ctx, node, kind),
                    "output_snapshot": None,
                    "error": None,
                }
                stream_steps.append(step_rec)
                step_t0 = time.perf_counter()
                yield "data: " + json.dumps(step_rec, ensure_ascii=False) + "\n\n"

                task = asyncio.create_task(run_node(nid))
                next_thought_index = thought_index
                try:
                    while not task.done():
                        thought_chunks = _serialize_thought_events(nid, next_thought_index)
                        next_thought_index = len(ctx.thought_events)
                        for chunk in thought_chunks:
                            yield chunk
                        for chunk in _serialize_result_deltas():
                            yield chunk
                        text_ready = None
                        pending = {task}
                        if result_collector is not None:
                            text_ready = asyncio.create_task(result_collector.text_available.wait())
                            pending.add(text_ready)
                        try:
                            done, _ = await asyncio.wait(pending, timeout=0.05)
                        finally:
                            if text_ready is not None:
                                text_ready.cancel()
                                with contextlib.suppress(asyncio.CancelledError):
                                    await text_ready
                        if task in done:
                            break
                    result, err = await task
                finally:
                    # Closing/cancelling an SSE consumer must cancel its in-flight node too.
                    if not task.done():
                        task.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await task
                thought_chunks = _serialize_thought_events(nid, next_thought_index)
                thought_index = len(ctx.thought_events)
                for chunk in thought_chunks:
                    yield chunk
                for chunk in _serialize_result_deltas():
                    yield chunk
                if err:
                    step_rec["status"] = "error"
                    step_rec["error"] = err
                    step_rec["elapsed_ms"] = int((time.perf_counter() - step_t0) * 1000)
                    elapsed_total = int((time.perf_counter() - t0) * 1000)
                    try:
                        await write_trace(save_workflow_trace, stream_trace_id, {
                            "run_id": "stream",
                            "trace_id": stream_trace_id,
                            "app_id": agent_app_id,
                            "version_id": version_id,
                            "app_name": app_name,
                            "status": "error",
                            "steps": stream_steps,
                            "nodes": nodes,
                            "edges": edges,
                            "output": None,
                            "error": err,
                            "elapsed_ms": elapsed_total,
                        })
                    except Exception:
                        logger.warning("MySQL trace write failed (non-fatal) trace_id=%s", stream_trace_id)
                    yield "data: " + json.dumps({**step_rec, "trace_id": stream_trace_id}, ensure_ascii=False) + "\n\n"
                    return
                child_tid = result.pop("_child_trace_id", None) if isinstance(result, dict) else None
                step_rec["status"] = "done"
                step_rec["output_snapshot"] = result
                step_rec["elapsed_ms"] = int((time.perf_counter() - step_t0) * 1000)
                if child_tid:
                    step_rec.setdefault("child_trace_ids", []).append(child_tid)
                ctx.context[nid] = result
                if result.get("branch_handle"):
                    edge_state["edges"] = _prune_selector_out_edges(
                        edge_state["edges"],
                        nid,
                        str(result.get("branch_handle") or "else"),
                    )
                yield "data: " + json.dumps({
                    **step_rec,
                    "output": result
                }) + "\n\n"
            _update_final_output(ctx, ready)

        if result_collector is not None:
            result_collector.finish(ctx, edge_state["edges"])
        for chunk in _serialize_result_deltas():
            yield chunk
        elapsed_total = int((time.perf_counter() - t0) * 1000)
        try:
            await write_trace(save_workflow_trace, stream_trace_id, {
                "run_id": "stream",
                "trace_id": stream_trace_id,
                "app_id": agent_app_id,
                "version_id": version_id,
                "app_name": app_name,
                "status": "done",
                "steps": stream_steps,
                "nodes": nodes,
                "edges": edges,
                "output": ctx.final_output or "",
                "error": None,
                "elapsed_ms": elapsed_total,
            })
        except Exception:
            logger.warning("MySQL trace write failed (non-fatal) trace_id=%s", stream_trace_id)
        completed = True
        yield "data: " + json.dumps({
            "status": "done",
            "output": ctx.final_output or "",
            "trace_id": stream_trace_id,
            "steps": stream_steps,
            "elapsed_ms": elapsed_total,
        }) + "\n\n"
    except (asyncio.CancelledError, GeneratorExit):
        if not completed:
            for step in stream_steps:
                if step.get("status") == "running":
                    step.update(status="stopped", error="执行已停止")
            try:
                await write_trace(save_workflow_trace, stream_trace_id, {
                    "run_id": "stream", "trace_id": stream_trace_id,
                    "app_id": agent_app_id, "version_id": version_id, "app_name": app_name,
                    "status": "stopped", "steps": stream_steps, "nodes": nodes, "edges": edges,
                    "output": ctx.final_output, "error": "执行已停止",
                    "elapsed_ms": int((time.perf_counter() - t0) * 1000),
                })
            except Exception:
                logger.exception("Stopped workflow trace write failed trace_id=%s", stream_trace_id)
        raise
    except Exception as e:
        elapsed_total = int((time.perf_counter() - t0) * 1000)
        msg = str(e)
        try:
            await write_trace(save_workflow_trace, stream_trace_id, {
                "run_id": "stream",
                "trace_id": stream_trace_id,
                "app_id": agent_app_id,
                "version_id": version_id,
                "app_name": app_name,
                "status": "error",
                "steps": stream_steps,
                "nodes": nodes,
                "edges": edges,
                "output": None,
                "error": msg,
                "elapsed_ms": elapsed_total,
            })
        except Exception:
            logger.warning("MySQL trace write failed (non-fatal) trace_id=%s", stream_trace_id)
        yield "data: " + json.dumps({"error": msg}) + "\n\n"


async def execute_agent_workflow_background(
    *,
    agent_app_id: int,
    version_id: int,
    inputs: Dict[str, Any],
    run_id: str,
) -> None:
    """独立 DB 会话中执行，供 HTTP 立即返回 run_id 后轮询 Redis。"""
    import logging

    from ...core.database import SessionLocal

    log = logging.getLogger(__name__)
    # 后台任务让出一个调度周期，避免同步型节点（如原子能力 SQL 执行）在
    # /run 响应发回前占住事件循环，导致前端只能在整条链路结束后才开始轮询。
    await asyncio.sleep(0.01)
    db = SessionLocal()
    try:
        await run_agent_workflow(
            db,
            agent_app_id=agent_app_id,
            version_id=version_id,
            inputs=inputs,
            run_id=run_id,
        )
    except (Exception, asyncio.CancelledError) as exc:
        log.exception("agent workflow background run_id=%s", run_id)
        payload = await TRACE_WORK.run(agent_run_trace_get, run_id) or {
            "run_id": run_id, "trace_id": run_id, "app_id": agent_app_id,
            "version_id": version_id, "steps": [], "output": None}
        message = "工作流执行超时" if isinstance(exc, TimeoutError) else str(getattr(exc, "detail", exc))
        payload.update(status="stopped" if isinstance(exc, asyncio.CancelledError) else "error",
                       error=message or "执行已停止")
        await write_trace(agent_run_trace_set, run_id, payload)
        await write_trace(save_workflow_trace, run_id, payload)
        if isinstance(exc, asyncio.CancelledError):
            raise
    finally:
        db.close()
