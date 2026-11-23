"""实验室网关（百炼风格包装）：将现有 SSE 事件包装为百炼流式格式。"""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from ...core.redis_client import trace_get
from ...core.execution import TRACE_WORK
from .lab_runtime import LabRunSpec, LabTraceContext, new_lab_trace_context
from .lab_pipeline_runner import run_autobi_lab_gateway_sse

logger = logging.getLogger(__name__)


def _dump_sse(obj: Dict[str, Any]) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


def _chart_type_letter(chart_spec: Dict[str, Any]) -> str:
    raw = str(chart_spec.get("type") or "D").upper()
    m = re.search(r"[ABCD]", raw)
    return m.group(0) if m else "D"


def _markdown_fence_for_chart_type(typ: str) -> str:
    """
    与 Java ChartEnum 对应：A=柱状 BAR、B=折线 LINE、C=饼图 PIE。
    markdown 围栏标签：bar / line / pie
    """
    if typ == "A":
        return "bar"
    if typ == "B":
        return "line"
    if typ == "C":
        return "pie"
    return "bar"


def _axis_keys(val: Any) -> List[str]:
    if val is None:
        return []
    if isinstance(val, str):
        return [val] if val.strip() else []
    if isinstance(val, list):
        return [str(x) for x in val if x is not None and str(x).strip()]
    return []


def _lower_map(cols: List[str]) -> Dict[str, str]:
    return {str(c).lower(): str(c) for c in cols if c is not None}


def _resolve_keys(requested: List[str], sql_columns: List[str]) -> List[str]:
    """与前端 autobiLabChartSpec.resolveSqlColumnKeys 一致：大小写不敏感落到实际列名。"""
    cols = [str(c) for c in sql_columns if c is not None]
    lm = _lower_map(cols)
    out: List[str] = []
    for k in requested:
        if k is None or str(k).strip() == "":
            continue
        ks = str(k)
        if ks in cols:
            out.append(ks)
        else:
            real = lm.get(ks.lower())
            if real:
                out.append(real)
    return out


def _is_shell_out_query(user_message: str) -> bool:
    text = str(user_message or "").lower()
    return any(key in text for key in ("shell-out", "shell out", "sell-out", "sell out"))


def _is_sell_out_agg_key(key: Any) -> bool:
    compact = re.sub(r"[^a-z0-9]+", "", str(key or "").lower())
    return compact == "sumselloutvalue"


def _normalize_shell_out_sql(sql_text: str, user_message: str) -> str:
    if not _is_shell_out_query(user_message):
        return sql_text
    if re.search(r"\bshell_out\b", sql_text, flags=re.IGNORECASE):
        return sql_text
    return re.sub(
        r"SUM\s*\(\s*sell_out_value\s*\)(\s+FROM\b)",
        r"SUM(sell_out_value) AS shell_out\1",
        sql_text,
        count=1,
        flags=re.IGNORECASE,
    )


def _normalize_shell_out_columns(columns: List[Any], user_message: str) -> List[str]:
    cols = [str(c) for c in (columns or []) if c is not None]
    if not _is_shell_out_query(user_message):
        return cols
    return ["shell_out" if _is_sell_out_agg_key(c) else c for c in cols]


def _normalize_shell_out_rows(rows: List[Any], user_message: str) -> List[Any]:
    if not _is_shell_out_query(user_message):
        return rows
    normalized: List[Any] = []
    for row in rows or []:
        if not isinstance(row, dict):
            normalized.append(row)
            continue
        next_row: Dict[str, Any] = {}
        shell_out_value = None
        for key, value in row.items():
            if _is_sell_out_agg_key(key):
                shell_out_value = value
            else:
                next_row[str(key)] = value
        if shell_out_value is not None:
            next_row["shell_out"] = shell_out_value
        normalized.append(next_row)
    return normalized


def _normalize_shell_out_chart_spec(chart_spec: Dict[str, Any], user_message: str) -> Dict[str, Any]:
    if not _is_shell_out_query(user_message) or not isinstance(chart_spec, dict):
        return chart_spec
    result = dict(chart_spec)
    for axis in ("xaxis", "yaxis"):
        keys = _axis_keys(result.get(axis))
        mapped = ["shell_out" if _is_sell_out_agg_key(k) else k for k in keys]
        if isinstance(result.get(axis), str):
            result[axis] = mapped[0] if mapped else ""
        else:
            result[axis] = mapped
    return result


def _bailian_markdown_from_lab_chart(
    chart_spec: Dict[str, Any],
    sql_columns: List[str],
    rows: List[Any],
) -> Tuple[str, Dict[str, Any], Dict[str, Any]]:
    """
    百炼 markdown + Bootcamp 图表载荷。

    - 围栏与 ChartEnum 一致：A→```bar、B→```line、C→```pie（见 bootcamp ChartEnum）。
    - 内部 JSON：`{ type, columns[{key,name,target}], data }`，与 Bootcamp 对话里 ```line / ```bar 块一致，
      且可直接交给 `bootcamp0415_user_frontend/src/utils/echarts-utils.ts` 的 `getEchartsOption`
      （A/B 走同一分支仅 chartType 为 bar/line；C 走饼图分支）。

    chart_intent（message.features.markdown）：
    - C：xaxis 字符串、yaxis 数组（百炼 pie 样例）
    - A/B：xaxis、yaxis 均为数组，可选 title（与 Bootcamp bar 流式样例一致；折线 B 同结构）
    """
    typ = _chart_type_letter(chart_spec)
    cols = [str(c) for c in (sql_columns or []) if c is not None]
    xkeys = _resolve_keys(_axis_keys(chart_spec.get("xaxis")), cols)
    ykeys = _resolve_keys(_axis_keys(chart_spec.get("yaxis")), cols)
    columns_out: List[Dict[str, str]] = []
    col_display: Dict[str, str] = {}
    for c in cols:
        target = ""
        if c in xkeys:
            target = "xaxis"
        elif c in ykeys:
            target = "yaxis"
        columns_out.append({"key": c, "name": c, "target": target})
        col_display[c] = c
    bootcamp_chart = {"type": typ, "columns": columns_out, "data": rows}
    fence = _markdown_fence_for_chart_type(typ)
    md = f"```{fence}\n" + json.dumps(bootcamp_chart, ensure_ascii=False, indent=4) + "\n```"

    # A=柱状、B=折线：与 Bootcamp bar 的 chart_intent 形态一致（折线样例亦为 xaxis/yaxis 数组 + title）
    if typ == "C":
        chart_intent: Dict[str, Any] = {
            "type": typ,
            "xaxis": xkeys[0] if xkeys else (cols[0] if cols else ""),
            "yaxis": list(ykeys),
        }
    elif typ in ("A", "B"):
        chart_intent = {"type": typ, "xaxis": list(xkeys), "yaxis": list(ykeys)}
        tit = chart_spec.get("title")
        if tit is not None and str(tit).strip():
            chart_intent["title"] = str(tit).strip()
    else:
        chart_intent = {"type": typ, "xaxis": list(xkeys), "yaxis": list(ykeys)}

    features = {
        "markdown": {
            "chart_intent": chart_intent,
            "columns": col_display,
        }
    }
    return md, features, bootcamp_chart


async def run_autobi_lab_gateway_bailian_sse(
    db: Session,
    *,
    user_message: str,
    lab_config: Dict[str, Any],
    kb_id: int,
    project_id: int,
    project_name: Optional[str],
    features: Optional[Dict[str, Any]] = None,
    trace: Optional[LabTraceContext] = None,
) -> AsyncGenerator[str, None]:
    """
    将内部实验室流水线 SSE（trace_id/summary/done/error）转为百炼风格返回。

    说明：
    - 不改动原有流水线，仅做外层包装。
    - token 统计为近似值，用于兼容百炼事件结构展示。
    """

    stream_id = uuid.uuid4().hex
    action_id = uuid.uuid4().hex
    trace = trace or new_lab_trace_context()
    trace_id = trace.trace_id
    inner_trace_id: Optional[str] = None
    trace_started_at = trace.started_at
    app_id = str(project_id)
    index = 0
    completion_tokens = 0
    prompt_tokens = max(1, len(user_message))
    status_code = "SUCCESS"
    first_token_rt_ms: Optional[int] = None
    sent_sql_citations = False
    sent_data_citations = False
    sent_lab_render = False

    def _wrap_message(
        *,
        msg_type: str,
        content: str = "",
        features: Optional[Dict[str, Any]] = None,
        finish: bool = False,
    ) -> str:
        nonlocal index, completion_tokens, first_token_rt_ms
        index += 1
        now_ms = int(time.time() * 1000)
        if msg_type == "text" and content:
            completion_tokens += len(content)
            if first_token_rt_ms is None:
                first_token_rt_ms = max(1, now_ms - trace_started_at)
        payload = {
            "id": stream_id,
            "trace_id": inner_trace_id or trace_id,
            "app_id": app_id,
            "created_time": now_ms,
            "model": "",
            "version": "default",
            "message": {
                "role": "assistant",
                "content": content,
                "type": msg_type,
                "features": features or {},
                "action_id": action_id,
            },
            "index": index,
            "prompt_tokens": prompt_tokens,
            "finish": finish,
            "status_code": status_code,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        }
        return _dump_sse(payload)

    def _chart_messages(chart_spec: Any, sql_data_payload: Any) -> List[str]:
        if not isinstance(chart_spec, dict) or not chart_spec:
            return []
        if not isinstance(sql_data_payload, dict):
            return []
        chart_spec = _normalize_shell_out_chart_spec(chart_spec, user_message)
        rows = _normalize_shell_out_rows(sql_data_payload.get("rows") or [], user_message)
        if not rows or sql_data_payload.get("skipped"):
            return []
        sql_columns = _normalize_shell_out_columns(sql_data_payload.get("columns") or [], user_message)
        typ_letter = _chart_type_letter(chart_spec)
        lab_features: Dict[str, Any] = {
            "chart_spec": chart_spec,
            "sql_data": sql_data_payload,
        }
        md: Optional[str] = None
        md_features: Optional[Dict[str, Any]] = None
        if typ_letter in ("A", "B", "C"):
            md, md_features, bootcamp_chart = _bailian_markdown_from_lab_chart(
                chart_spec, sql_columns, rows
            )
            lab_features["bootcamp_chart"] = bootcamp_chart
        chunks = [_wrap_message(msg_type="lab_render", features=lab_features)]
        if md is not None and md_features is not None:
            chunks.append(_wrap_message(msg_type="markdown", content=md, features=md_features))
        return chunks

    async for raw in run_autobi_lab_gateway_sse(
        db,
        user_message=user_message,
        lab_config=lab_config,
        kb_id=kb_id,
        project_id=project_id,
        project_name=project_name,
        trace_id=trace_id,
        trace_started_at=trace_started_at,
        bailian_compat=True,
        features=features,
    ):
        for block in raw.split("\n\n"):
            if not block.strip():
                continue
            for line in block.split("\n"):
                line = line.strip()
                if not line.startswith("data: "):
                    continue
                try:
                    obj = json.loads(line[6:].strip())
                except json.JSONDecodeError:
                    continue

                evt_type = obj.get("type")
                if evt_type == "trace_id":
                    inner_trace_id = str(obj.get("trace_id") or trace_id)
                elif evt_type == "bailian_progress":
                    prog = str(obj.get("progress") or "")
                    if prog:
                        yield _wrap_message(msg_type="progress", features={"progress": prog})
                elif evt_type == "bailian_sql":
                    raw_sql = str(obj.get("sql") or "").strip()
                    sql_text = _normalize_shell_out_sql(raw_sql, user_message)
                    q = str(obj.get("query") or user_message)
                    if sql_text and sql_text.lower() != "none":
                        sent_sql_citations = True
                        yield _wrap_message(
                            msg_type="sql_citations",
                            features={"sql_citations": [{"query": q, "sql": sql_text}], "sql": raw_sql},
                        )
                elif evt_type == "bailian_data":
                    q = str(obj.get("query") or user_message)
                    rows = _normalize_shell_out_rows(obj.get("data") or [], user_message)
                    if rows:
                        sent_data_citations = True
                        yield _wrap_message(
                            msg_type="data_citations",
                            features={"data_citations": [{"query": q, "data": rows}]},
                        )
                elif evt_type == "bailian_chart":
                    if not sent_lab_render:
                        for chunk in _chart_messages(obj.get("chart_spec"), obj.get("sql_data")):
                            yield chunk
                            sent_lab_render = True
                elif evt_type == "summary":
                    delta = str(obj.get("delta") or "")
                    if delta:
                        yield _wrap_message(msg_type="text", content=delta)
                elif evt_type == "error":
                    status_code = "FAILED"
                    msg = str(obj.get("message") or "未知错误")
                    yield _wrap_message(msg_type="text", content=f"\n[error] {msg}")
                elif evt_type == "done":
                    # done 前补齐百炼常见结构：sql_citations / data_citations / markdown(chart)
                    need_trace_fallback = (
                        not sent_sql_citations
                        or not sent_data_citations
                        or not sent_lab_render
                    )
                    trace: Dict[str, Any] = {}
                    if need_trace_fallback:
                        final_trace_id = inner_trace_id or trace_id
                        try:
                            trace = await TRACE_WORK.run(trace_get, final_trace_id) or {}
                        except Exception:
                            logger.exception("读取实验室 trace 兜底数据失败 trace_id=%s", final_trace_id)
                    steps = trace.get("steps") or []
                    step_by_id: Dict[int, Dict[str, Any]] = {}
                    for s in steps:
                        sid_raw = s.get("step_id")
                        try:
                            sid = int(sid_raw)
                        except (TypeError, ValueError):
                            continue
                        step_by_id[sid] = s

                    raw_sql = (
                        ((step_by_id.get(15) or {}).get("response") or {}).get("sql")
                        or ((step_by_id.get(14) or {}).get("response") or {}).get("sql")
                        or ""
                    )
                    raw_sql = str(raw_sql).strip()
                    sql_text = _normalize_shell_out_sql(raw_sql, user_message)
                    if (
                        not sent_sql_citations
                        and sql_text
                        and sql_text.lower() != "none"
                    ):
                        yield _wrap_message(
                            msg_type="sql_citations",
                            features={
                                "sql": raw_sql,
                                "sql_citations": [
                                    {
                                        "query": user_message,
                                        "sql": sql_text,
                                    }
                                ]
                            },
                        )

                    step16_resp = ((step_by_id.get(16) or {}).get("response") or {})
                    rows = _normalize_shell_out_rows(step16_resp.get("rows") or [], user_message)
                    sql_columns = _normalize_shell_out_columns(step16_resp.get("columns") or [], user_message)
                    if not sent_data_citations and rows:
                        yield _wrap_message(
                            msg_type="data_citations",
                            features={
                                "data_citations": [
                                    {
                                        "query": user_message,
                                        "data": rows,
                                    }
                                ]
                            },
                        )

                    chart_spec = _normalize_shell_out_chart_spec(
                        ((step_by_id.get(18) or {}).get("response") or {}).get("chart_spec"),
                        user_message,
                    )
                    # 与 new-chat 实验室 AutobiLabChartPanel 一致；并附带 Bootcamp 前端 getEchartsOption 所需结构
                    if (
                        not sent_lab_render
                        and isinstance(chart_spec, dict)
                        and chart_spec
                        and rows
                        and not step16_resp.get("skipped")
                    ):
                        sql_data_payload = {
                            "columns": sql_columns,
                            "rows": rows,
                            "row_count": step16_resp.get("row_count"),
                            "skipped": step16_resp.get("skipped"),
                        }
                        for chunk in _chart_messages(chart_spec, sql_data_payload):
                            yield chunk
                            sent_lab_render = True

                    elapsed = max(1, int(time.time() * 1000) - trace_started_at)
                    tps = round(completion_tokens / max(elapsed / 1000.0, 0.001), 2)
                    stats = {
                        "first_token_rt": first_token_rt_ms or elapsed,
                        "tokens_per_sec": tps,
                        "total_tokens": prompt_tokens + completion_tokens,
                        "response_time": elapsed,
                    }
                    yield _wrap_message(msg_type="statistics", features=stats, finish=True)


async def stream_lab_bailian_sse(
    db: Session,
    spec: LabRunSpec,
    *,
    trace: Optional[LabTraceContext] = None,
) -> AsyncGenerator[str, None]:
    """平台适配器入口：将平台无关实验室运行规格输出为百炼 SSE。"""
    async for chunk in run_autobi_lab_gateway_bailian_sse(
        db,
        user_message=spec.content,
        lab_config=spec.lab_config,
        kb_id=spec.knowledge_base_id,
        project_id=spec.project_id,
        project_name=spec.project_name,
        features=spec.features,
        trace=trace,
    ):
        yield chunk
