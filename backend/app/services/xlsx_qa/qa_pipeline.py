"""
XLSX Smart Q&A · Four-stage Q&A pipeline (SSE streaming)

Stage order:
  A. plan        — LLM intent understanding + sub-question decomposition → subquestions[]
  B. text_to_sql — ALL sub-questions generated in PARALLEL → one SELECT each
  C. run_sql     — execute each SQL once; preserve failures for diagnostics
  D. chart       — LLM picks best charts from successful results
  E. summarize   — LLM writes the final report + follow-up questions

Returns an async generator of SSE text chunks; the router wraps it in StreamingResponse.
"""
from __future__ import annotations

import asyncio
import datetime as _dt
import json
import logging
import time
from dataclasses import dataclass, asdict, field
from typing import Any, AsyncIterator, Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from . import llm_client
from . import prompts
from .sql_safety import SqlSafetyError, run_select
from . import table_understanding

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SSE helpers
# ---------------------------------------------------------------------------

def _sse(event: str, data: Dict[str, Any]) -> str:
    payload = json.dumps(data, ensure_ascii=False, default=_json_default)
    return f"event: {event}\ndata: {payload}\n\n"


def _json_default(v: Any) -> Any:
    if isinstance(v, (_dt.date, _dt.datetime)):
        return v.isoformat()
    return str(v)


# ---------------------------------------------------------------------------
# Pipeline context
# ---------------------------------------------------------------------------

@dataclass
class SheetInfo:
    """单个活跃 Sheet 的上下文信息。"""
    sheet_id: int
    file_name: str
    sheet_name: str
    data_table_name: str
    columns_json: List[dict]
    understanding_md: str
    total_rows: int = 0


@dataclass
class QaContext:
    db: Session
    engine: Engine
    conversation_id: int
    module_name: str
    active_sheets: List[SheetInfo]           # 当前可用的 Sheet 列表（至少 1 个）
    user_question: str
    history: List[Dict[str, str]]            # OpenAI messages, last ~2 rounds
    llm_provider_id: Optional[int]
    llm_model: Optional[str]
    prompts_override: Optional[Dict[str, Optional[str]]] = None
    sql_max_rows: int = 1000
    sql_timeout_ms: int = 10000
    max_subquestions: int = 5
    enable_chart: bool = True
    module_understanding_md: Optional[str] = None  # Stage 0 输入（跨 Sheet 汇总理解）
    language: Optional[str] = None

    # 旧字段保留为 None 以保证向后兼容（让仍用旧签名的调用方不会报错）
    file_name: Optional[str] = None
    sheet_name: Optional[str] = None
    data_table_name: Optional[str] = None
    total_rows: int = 0
    columns_json: List[dict] = field(default_factory=list)
    understanding_md: Optional[str] = None

    def __post_init__(self) -> None:
        """如果调用方传了旧字段但没传 active_sheets，则自动转换。"""
        if not self.active_sheets and self.data_table_name:
            self.active_sheets = [
                SheetInfo(
                    sheet_id=0,
                    file_name=self.file_name or "",
                    sheet_name=self.sheet_name or "Sheet1",
                    data_table_name=self.data_table_name,
                    columns_json=list(self.columns_json),
                    understanding_md=self.understanding_md or "",
                )
            ]


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------

async def run_pipeline(ctx: QaContext) -> AsyncIterator[str]:
    """Async generator of SSE text. Last event is always `done` or `error`."""
    final_state: Dict[str, Any] = {
        "plan_summary": "",
        "subquestions": [],
        "summary_markdown": "",
        "follow_up_questions": [],
        "stage_timings": {},
        "chart": None,
        "charts": [],
        "primary_chart_id": None,
        "think_content": None,
        "relevant_sheet_ids": None,
    }

    # 初始化知识挖掘结果
    knowledge_items: List[Dict[str, Any]] = []

    bundle = prompts.resolve_bundle(ctx.prompts_override, default_language=ctx.language)

    try:
        choice = llm_client.resolve_llm(
            ctx.db,
            provider_id=ctx.llm_provider_id,
            model=ctx.llm_model,
        )
    except HTTPException as e:
        yield _sse("error", {"stage": "resolve_llm", "message": e.detail})
        return

    # ── Stage 0: Module Planning (Think) ────────────────────────────────────
    # 只在多 Sheet + 有模块汇总理解时启用
    relevant_sheets: List[SheetInfo] = ctx.active_sheets
    if ctx.module_understanding_md and len(ctx.active_sheets) > 1:
        yield _sse("stage_start", {
            "stage": "module_plan",
            "message": "Analyzing cross-sheet data relationships…",
        })
        t_mp = time.time()
        try:
            mp_result = await _stage_module_planning(
                choice, ctx.module_understanding_md, ctx.user_question, ctx.active_sheets
            )
            final_state["think_content"] = mp_result.get("think_content") or ""
            final_state["relevant_sheet_ids"] = mp_result.get("relevant_sheet_ids") or []
            final_state["stage_timings"]["module_plan_ms"] = int((time.time() - t_mp) * 1000)

            # 筛选 relevant sheets
            relevant_ids = set(mp_result.get("relevant_sheet_ids") or [])
            if relevant_ids:
                relevant_sheets = [s for s in ctx.active_sheets if s.sheet_id in relevant_ids]
                if not relevant_sheets:
                    relevant_sheets = ctx.active_sheets  # fallback

            yield _sse("module_plan", {
                "think_content": final_state["think_content"],
                "relevant_sheet_ids": final_state["relevant_sheet_ids"],
            })
        except Exception as e:
            logger.warning("xlsx_qa.module_plan failed: %s", e)
            # 降级：跳过 Stage 0，使用全部 Sheet
            relevant_sheets = ctx.active_sheets
    else:
        # 单 Sheet：跳过 Stage 0
        relevant_sheets = ctx.active_sheets

    # 构建多 Sheet schema block
    multi_schema_block = prompts.build_schema_prompt(active_sheets=relevant_sheets)

    yield _sse("stage_start", {"stage": "plan", "message": "Analyzing your question and planning the approach…"})

    # ── Stage A: plan ──────────────────────────────────────────────────────
    t0 = time.time()
    try:
        plan = await _stage_plan(choice, bundle, multi_schema_block, ctx.user_question, ctx.history)
    except HTTPException as e:
        yield _sse("error", {"stage": "plan", "message": str(e.detail)})
        return
    final_state["stage_timings"]["plan_ms"] = int((time.time() - t0) * 1000)
    final_state["plan_summary"] = plan.get("plan_summary") or ""

    subqs_raw = plan.get("subquestions") or []
    if not isinstance(subqs_raw, list) or not subqs_raw:
        yield _sse("error", {"stage": "plan", "message": "Model returned no usable sub-questions."})
        return
    subqs_raw = subqs_raw[: ctx.max_subquestions]
    default_follow_ups = [str(x) for x in (plan.get("follow_up_questions") or []) if str(x).strip()][:4]

    subquestions: List[Dict[str, Any]] = []
    for idx, sq in enumerate(subqs_raw):
        sq_id = str(sq.get("id") or f"sq{idx + 1}")
        # 映射 target_sheet
        target = _map_target_sheet(sq, relevant_sheets)
        subquestions.append({
            "id": sq_id,
            "question": str(sq.get("question") or "").strip() or f"Sub-question {idx + 1}",
            "purpose": str(sq.get("purpose") or "").strip(),
            "sql": "",
            "sql_status": "pending",
            "columns": [],
            "rows": [],
            "total_rows": 0,
            "error": None,
            "explain": "",
            "target_sheet_id": target.sheet_id if target else None,
            "target_sheet_display_name": (
                f"{target.file_name} / {target.sheet_name}" if target else None
            ),
        })

    yield _sse("plan", {
        "plan_summary": final_state["plan_summary"],
        "subquestions": [
            {
                "id": s["id"], "question": s["question"], "purpose": s["purpose"],
                "target_sheet_id": s.get("target_sheet_id"),
                "target_sheet_display_name": s.get("target_sheet_display_name"),
            }
            for s in subquestions
        ],
    })

    # ── Stage B+C: parallel SQL generation + execution ─────────────────────
    for s in subquestions:
        yield _sse("stage_start", {
            "stage": "text_to_sql",
            "subquestion_id": s["id"],
            "message": f"Analyzing: {s['question']}…",
        })

    t_sql = time.time()

    # 构建 allowed_tables 白名单
    all_allowed = [s.data_table_name for s in relevant_sheets]

    # 知识挖掘（并行）
    knowledge_task = _stage_knowledge_mining(
        choice=choice,
        active_sheets=relevant_sheets,
        module_understanding_md=ctx.module_understanding_md,
        user_question=ctx.user_question,
    )
    subq_tasks = [
        _process_subq(
            choice=choice,
            bundle=bundle,
            s=s,
            relevant_sheets=relevant_sheets,
            engine=ctx.engine,
            all_allowed_tables=all_allowed,
            sql_max_rows=ctx.sql_max_rows,
            sql_timeout_ms=ctx.sql_timeout_ms,
        )
        for s in subquestions
    ]

    results = await asyncio.gather(*subq_tasks, knowledge_task, return_exceptions=True)
    km_result = results[-1]
    if isinstance(km_result, dict):
        knowledge_items = km_result.get("knowledge_items") or []
    else:
        knowledge_items = []
    final_state["stage_timings"]["sql_ms"] = int((time.time() - t_sql) * 1000)

    # Emit results in original order
    for s in subquestions:
        yield _sse("sql", {
            "subquestion_id": s["id"],
            "sql": s.get("sql") or "",
            "explain": s.get("explain") or "",
        })
        yield _sse("sql_result", _subq_result_dto(s))

    final_state["subquestions"] = subquestions

    # ── Stage D: chart ──────────────────────────────────────────────────────
    if ctx.enable_chart and any(s["sql_status"] == "ok" and s.get("rows") for s in subquestions):
        yield _sse("stage_start", {"stage": "chart", "message": "Selecting the best chart combination…"})
        t_chart = time.time()
        try:
            chart_result = await _stage_chart(
                choice, bundle,
                user_question=ctx.user_question,
                subquestions=subquestions,
            )
        except HTTPException as e:
            chart_result = None
            yield _sse("stage_error", {"stage": "chart", "message": str(e.detail)})
        if chart_result and chart_result.get("charts"):
            charts = chart_result["charts"]
            primary_id = chart_result.get("primary_id")
            primary = next((c for c in charts if c["subquestion_id"] == primary_id), charts[0])
            final_state["charts"] = charts
            final_state["primary_chart_id"] = primary["subquestion_id"]
            final_state["chart"] = primary
            final_state["stage_timings"]["chart_ms"] = int((time.time() - t_chart) * 1000)
            yield _sse("chart", {
                "primary_id": primary["subquestion_id"],
                "charts": charts,
                "chart": primary,
            })

    # ── Stage E: summarize ──────────────────────────────────────────────────
    yield _sse("stage_start", {"stage": "summarize", "message": "Summarizing conclusions and insights…"})

    t1 = time.time()
    try:
        summary = await _stage_summarize(
            choice, bundle,
            user_question=ctx.user_question,
            subquestions=subquestions,
            default_follow_ups=default_follow_ups,
        )
        final_state["summary_markdown"] = summary.get("summary_markdown") or ""
        follow_ups = [str(x) for x in (summary.get("follow_up_questions") or []) if str(x).strip()][:4]
        final_state["follow_up_questions"] = follow_ups or default_follow_ups
        final_state["stage_timings"]["summarize_ms"] = int((time.time() - t1) * 1000)
    except HTTPException as e:
        final_state["summary_markdown"] = (
            "Sorry, the summary stage failed: " + str(e.detail) +
            "\n\nThe sub-question results below were retrieved successfully — please refer to them."
        )
        final_state["follow_up_questions"] = default_follow_ups

    yield _sse("summary", {
        "summary_markdown": final_state["summary_markdown"],
        "follow_up_questions": final_state["follow_up_questions"],
    })

    # ── Stage F: knowledge_card (parallel result, emitted after summarize) ───
    if knowledge_items:
        yield _sse("knowledge_card", {
            "has_knowledge": True,
            "items": knowledge_items,
        })

    yield _sse("done", {"state": _strip_for_done(final_state)})


# ---------------------------------------------------------------------------
# Parallel sub-question processor (modifies `s` dict in-place)
# ---------------------------------------------------------------------------

async def _process_subq(
    *,
    choice: llm_client.LlmChoice,
    bundle: prompts.PromptBundle,
    s: Dict[str, Any],
    relevant_sheets: List[SheetInfo],
    engine: Engine,
    all_allowed_tables: List[str],
    sql_max_rows: int,
    sql_timeout_ms: int,
) -> None:
    """Generate and execute one SQL for the mapped sheet. Mutates `s` in-place."""

    # ── Resolve target sheet ─────────────────────────────────────────────────
    target = _resolve_target_sheet(s, relevant_sheets)

    # Build single-sheet schema for the target
    schema_block = prompts.build_schema_prompt(
        file_name=target.file_name,
        sheet_name=target.sheet_name,
        data_table_name=target.data_table_name,
        total_rows=getattr(target, "total_rows", 0),
        columns=target.columns_json,
        understanding_md=target.understanding_md,
    )

    data_table_name = target.data_table_name

    # ── Step 1: generate SQL ────────────────────────────────────────────────
    try:
        sql_obj = await _stage_text_to_sql(
            choice, bundle,
            schema_block=schema_block,
            subquestion=s["question"],
            table_name=data_table_name,
        )
    except HTTPException as e:
        s["sql_status"] = "error"
        s["error"] = f"SQL generation failed: {e.detail}"
        return

    s["sql"]     = (sql_obj.get("sql") or "").strip()
    s["explain"] = sql_obj.get("explain") or ""

    if not s["sql"]:
        s["sql_status"] = "error"
        s["error"] = "Model did not return SQL."
        return

    # ── Step 2: execute SQL ─────────────────────────────────────────────────
    await _run_sql(s, engine=engine, allowed_tables=all_allowed_tables,
                                 sql_max_rows=sql_max_rows, sql_timeout_ms=sql_timeout_ms)


async def _run_sql(
    s: Dict[str, Any],
    *,
    engine: Engine,
    allowed_tables: List[str],
    sql_max_rows: int,
    sql_timeout_ms: int,
) -> Optional[str]:
    """Execute s["sql"]. On success fills s with results and returns None.
    On failure sets s["sql_status"]="error" and returns the error string."""
    try:
        cols, rows, total, truncated = await asyncio.to_thread(
            run_select,
            engine,
            s["sql"],
            allowed_tables=allowed_tables,
            max_rows=sql_max_rows,
            timeout_ms=sql_timeout_ms,
        )
        s["sql_status"] = "ok"
        s["columns"]    = list(cols)
        s["rows"]       = [list(_jsonable_row(r)) for r in rows]
        s["total_rows"] = int(total)
        s["truncated"]  = bool(truncated)
        return None
    except SqlSafetyError as e:
        err = f"SQL safety check failed: {e}"
    except Exception as e:  # noqa: BLE001
        err = f"SQL execution failed: {e}"
    s["sql_status"] = "error"
    s["error"]      = err
    return err


# ---------------------------------------------------------------------------
# Individual stage functions
# ---------------------------------------------------------------------------

def _map_target_sheet(sq: dict, sheets: List[SheetInfo]) -> Optional[SheetInfo]:
    """Map LLM's target_sheet_name / target_file_name to a concrete SheetInfo."""
    if not sheets:
        return None
    target_file = (sq.get("target_file_name") or "").strip()
    target_sheet = (sq.get("target_sheet_name") or "").strip()

    # If LLM didn't provide sheet targeting (single-sheet schema) → use first
    if not target_file and not target_sheet:
        return sheets[0]

    # Exact match
    for s in sheets:
        if target_file and target_sheet:
            if s.file_name == target_file and s.sheet_name == target_sheet:
                return s
        elif target_sheet:
            if s.sheet_name == target_sheet:
                return s
        elif target_file:
            if s.file_name == target_file:
                return s

    # Case-insensitive fallback
    for s in sheets:
        if target_file and target_sheet:
            if s.file_name.lower() == target_file.lower() and s.sheet_name.lower() == target_sheet.lower():
                return s
        elif target_sheet:
            if s.sheet_name.lower() == target_sheet.lower():
                return s
        elif target_file:
            if s.file_name.lower() == target_file.lower():
                return s

    # Fallback to first sheet
    return sheets[0]


def _resolve_target_sheet(s: Dict[str, Any], sheets: List[SheetInfo]) -> SheetInfo:
    """Resolve the target sheet for a sub-question (already mapped in run_pipeline).
    Falls back to the first sheet."""
    target_id = s.get("target_sheet_id")
    if target_id is not None:
        for sh in sheets:
            if sh.sheet_id == target_id:
                return sh
    return sheets[0]


async def _stage_module_planning(
    choice: llm_client.LlmChoice,
    module_understanding_md: str,
    user_question: str,
    active_sheets: List[SheetInfo],
) -> Dict[str, Any]:
    """Stage 0: Think about cross-sheet relevance before plan decomposition."""
    # Build sheet index for the prompt
    sheet_index_lines = []
    for s in active_sheets:
        sheet_index_lines.append(
            f"- Sheet ID {s.sheet_id}: {s.file_name} / {s.sheet_name} "
            f"(table: {s.data_table_name})"
        )
    sheet_index = "\n".join(sheet_index_lines)

    user = (
        "=== MODULE UNDERSTANDING (cross-sheet relationships) ===\n"
        f"{module_understanding_md}\n\n"
        "=== AVAILABLE SHEETS ===\n"
        f"{sheet_index}\n\n"
        "=== USER QUESTION ===\n"
        f"{user_question}\n\n"
        "Think step by step about which sheets are relevant to this question, "
        "then output the JSON."
    )

    return await llm_client.chat_json(
        choice,
        system=prompts.MODULE_PLANNING_SYSTEM,
        user=user,
        temperature=0.3,
        max_tokens=1200,
    )

async def _stage_plan(
    choice: llm_client.LlmChoice,
    bundle: prompts.PromptBundle,
    schema_block: str,
    user_question: str,
    history: List[Dict[str, str]],
) -> Dict[str, Any]:
    user = (
        f"{schema_block}\n\n"
        "=== USER QUESTION (detect output language from THIS text only) ===\n"
        f"{user_question}"
    )
    return await llm_client.chat_json(
        choice,
        system=bundle.plan_system,
        user=user,
        history=history,
        temperature=0.2,
        max_tokens=1200,
    )


async def _stage_text_to_sql(
    choice: llm_client.LlmChoice,
    bundle: prompts.PromptBundle,
    *,
    schema_block: str,
    subquestion: str,
    table_name: str,
) -> Dict[str, Any]:
    system = bundle.text_to_sql_system.replace("{table_name}", table_name)
    user = (
        f"{schema_block}\n\n"
        "=== SUB-QUESTION TO ANSWER ===\n"
        f"{subquestion}"
    )
    obj = await llm_client.chat_json(
        choice,
        system=system,
        user=user,
        temperature=0.1,
        max_tokens=800,
    )
    if "sql" not in obj:
        raise HTTPException(status_code=502, detail="Model did not return sql field")
    return obj


async def _stage_chart(
    choice: llm_client.LlmChoice,
    bundle: prompts.PromptBundle,
    *,
    user_question: str,
    subquestions: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    candidates = [s for s in subquestions if s["sql_status"] == "ok" and s.get("rows")]
    if not candidates:
        return None

    payload = {
        "_lang_note": "Detect output language from user_question field only; ignore schema/system text language.",
        "user_question": user_question,
        "subquestions": [
            {
                "id": s["id"],
                "question": s["question"],
                "status": s["sql_status"],
                "columns": s.get("columns") or [],
                "rows": (s.get("rows") or [])[:15],
                "total_rows": s.get("total_rows") or 0,
            }
            for s in candidates
        ],
    }
    user = json.dumps(payload, ensure_ascii=False, default=_json_default)
    obj = await llm_client.chat_json(
        choice,
        system=bundle.chart_system,
        user=user,
        temperature=0.3,
        max_tokens=2000,
    )

    raw_charts = obj.get("charts")
    if not isinstance(raw_charts, list) or not raw_charts:
        legacy_single = {
            "subquestion_id": obj.get("source_subquestion_id") or obj.get("subquestion_id"),
            "chart_type": obj.get("chart_type"),
            "title": obj.get("title"),
            "explain": obj.get("explain"),
            "dimension_field": obj.get("dimension_field"),
            "metric_fields": obj.get("metric_fields"),
        }
        if legacy_single["subquestion_id"] and legacy_single["chart_type"]:
            raw_charts = [legacy_single]
        else:
            raw_charts = []

    built: List[Dict[str, Any]] = []
    seen_ids: set[str] = set()
    llm_picked_ids = {str(c.get("subquestion_id") or "").strip() for c in raw_charts if isinstance(c, dict)}

    def _match_col(name: Any, sq_cols: List[str]) -> Optional[str]:
        if name is None:
            return None
        key = str(name).strip().lower()
        if not key:
            return None
        for c in sq_cols:
            if c.lower() == key:
                return c
        norm = key.replace(" ", "").replace("_", "")
        for c in sq_cols:
            if c.lower().replace(" ", "").replace("_", "") == norm:
                return c
        return None

    def _auto_fields(sq: Dict[str, Any]) -> tuple[Optional[str], List[str]]:
        cols = list(sq.get("columns") or [])
        rows = sq.get("rows") or []
        if len(cols) < 2 or not rows:
            return None, []
        dim = cols[0]
        numeric_cols: List[str] = []
        for i, c in enumerate(cols[1:], start=1):
            sample = [r[i] for r in rows[:20] if i < len(r) and r[i] is not None]
            if not sample:
                continue
            def _isnum(v):
                if isinstance(v, (int, float)):
                    return True
                s = str(v).strip().replace(",", "").replace(" ", "").replace("%", "")
                try:
                    float(s)
                    return True
                except (TypeError, ValueError):
                    return False
            if sum(1 for v in sample if _isnum(v)) >= max(1, int(len(sample) * 0.7)):
                numeric_cols.append(c)
        return dim, numeric_cols[:2] or [cols[1]]

    def _pick_chart_type(preferred: str, sq: Dict[str, Any], metrics: List[str]) -> str:
        rows = sq.get("rows") or []
        if not metrics:
            return "table"
        n = len(rows)
        if preferred == "pie" and 2 <= n <= 6:
            return "pie"
        if preferred == "line" and n >= 3:
            return "line"
        if preferred in {"bar", "line", "pie"}:
            return "bar" if n >= 2 else "table"
        return "table"

    for c in raw_charts:
        if not isinstance(c, dict):
            continue
        sq_id = str(c.get("subquestion_id") or "").strip()
        if not sq_id or sq_id in seen_ids:
            continue
        source_sq = next((s for s in candidates if s["id"] == sq_id), None)
        if source_sq is None:
            continue
        preferred = str(c.get("chart_type") or "").strip().lower()
        if preferred not in {"bar", "line", "pie", "table"}:
            preferred = "bar"
        sq_cols = list(source_sq.get("columns") or [])

        dim = _match_col(c.get("dimension_field"), sq_cols)
        metrics_raw = c.get("metric_fields") or []
        metrics = [m for m in (_match_col(x, sq_cols) for x in metrics_raw) if m]

        ctype = preferred
        if ctype in {"bar", "line", "pie"} and (not dim or not metrics):
            auto_dim, auto_metrics = _auto_fields(source_sq)
            if auto_dim and auto_metrics:
                dim, metrics = auto_dim, auto_metrics
                ctype = _pick_chart_type(preferred, source_sq, metrics)
            else:
                ctype = "table"

        built.append({
            "subquestion_id": source_sq["id"],
            "chart_type": ctype,
            "title": str(c.get("title") or "").strip() or source_sq["question"],
            "explain": str(c.get("explain") or "").strip(),
            "dimension_field": dim if ctype != "table" else None,
            "metric_fields": metrics if ctype != "table" else [],
            "columns": list(source_sq.get("columns") or []),
            "rows": list(source_sq.get("rows") or [])[:100],
            "role": "secondary",
        })
        seen_ids.add(sq_id)

    # Fill in any sub-questions the LLM missed (up to 4 total)
    for sq in candidates:
        if len(built) >= 4:
            break
        if sq["id"] in seen_ids:
            continue
        auto_dim, auto_metrics = _auto_fields(sq)
        if not (auto_dim and auto_metrics):
            continue
        built.append({
            "subquestion_id": sq["id"],
            "chart_type": "bar" if len(sq.get("rows") or []) >= 2 else "table",
            "title": sq["question"],
            "explain": "",
            "dimension_field": auto_dim,
            "metric_fields": auto_metrics,
            "columns": list(sq.get("columns") or []),
            "rows": list(sq.get("rows") or [])[:100],
            "role": "secondary",
        })
        seen_ids.add(sq["id"])

    if not built:
        return None

    primary_id = str(obj.get("primary_id") or "").strip()
    if not any(b["subquestion_id"] == primary_id for b in built):
        primary_id = built[0]["subquestion_id"]
    for b in built:
        b["role"] = "primary" if b["subquestion_id"] == primary_id else "secondary"

    logger.info(
        "xlsx_qa.chart built=%s primary=%s types=%s (llm_picked=%s, candidates=%s)",
        len(built), primary_id, [b["chart_type"] for b in built],
        sorted(llm_picked_ids), [s["id"] for s in candidates],
    )
    return {"primary_id": primary_id, "charts": built}


async def _stage_knowledge_mining(
    choice: llm_client.LlmChoice,
    active_sheets: List[SheetInfo],
    module_understanding_md: Optional[str],
    user_question: str,
) -> Dict[str, Any]:
    """判断用户问题是否揭示了新的业务知识，返回结构化追加片段（失败返回空）。"""
    if not active_sheets and not user_question:
        return {"has_new_knowledge": False, "knowledge_items": []}

    # Build per-sheet understanding block
    understanding_blocks: List[str] = []
    if module_understanding_md and module_understanding_md.strip():
        understanding_blocks.append(
            "=== MODULE SUMMARY (cross-sheet relationships) ===\n"
            f"{module_understanding_md.strip()}\n"
        )
    for s in active_sheets:
        understanding_blocks.append(
            f"=== SHEET ID {s.sheet_id}: {s.file_name} / {s.sheet_name} ===\n"
            f"{s.understanding_md or '(no understanding generated yet)'}\n"
        )
    understanding_text = "\n".join(understanding_blocks) if understanding_blocks else "(no understanding generated yet)"

    user = (
        "=== TABLE UNDERSTANDING REPORTS ===\n"
        f"{understanding_text}\n\n"
        "=== USER QUESTION ===\n"
        f"{user_question}\n\n"
        "Based on the table understanding reports and the user's question above, "
        "extract any new business knowledge, aliases, or mappings not already covered. "
        "Output JSON as instructed."
    )
    try:
        result = await llm_client.chat_json(
            choice,
            system=prompts.KNOWLEDGE_MINING_SYSTEM,
            user=user,
            temperature=0.2,
            max_tokens=800,
            timeout=60.0,
        )
        if not isinstance(result, dict):
            return {"has_new_knowledge": False, "knowledge_items": []}
        return {
            "has_new_knowledge": bool(result.get("has_new_knowledge", False)),
            "knowledge_items": result.get("knowledge_items") or [],
        }
    except Exception:  # noqa: BLE001
        return {"has_new_knowledge": False, "knowledge_items": []}


async def _stage_summarize(
    choice: llm_client.LlmChoice,
    bundle: prompts.PromptBundle,
    *,
    user_question: str,
    subquestions: List[Dict[str, Any]],
    default_follow_ups: List[str],
) -> Dict[str, Any]:
    payload = {
        "_lang_note": "Detect output language from user_question field only; ignore schema/system text language.",
        "user_question": user_question,
        "subquestions": [
            {
                "question": s["question"],
                "purpose": s["purpose"],
                "sql": s["sql"],
                "status": s["sql_status"],
                "error": s.get("error"),
                "columns": s.get("columns") or [],
                "rows": (s.get("rows") or [])[:20],
                "total_rows": s.get("total_rows") or 0,
            }
            for s in subquestions
        ],
        "default_follow_ups": default_follow_ups,
    }
    user = json.dumps(payload, ensure_ascii=False, default=_json_default)
    return await llm_client.chat_json(
        choice,
        system=bundle.summary_system,
        user=user,
        temperature=0.4,
        max_tokens=2000,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _subq_result_dto(s: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "subquestion_id": s["id"],
        "sql_status": s["sql_status"],
        "columns": s.get("columns") or [],
        "rows": s.get("rows") or [],
        "total_rows": s.get("total_rows") or 0,
        "truncated": bool(s.get("truncated")),
        "error": s.get("error"),
    }


def _strip_for_done(state: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "plan_summary": state.get("plan_summary") or "",
        "subquestions": state.get("subquestions") or [],
        "summary_markdown": state.get("summary_markdown") or "",
        "follow_up_questions": state.get("follow_up_questions") or [],
        "stage_timings": state.get("stage_timings") or {},
        "chart": state.get("chart") or None,
        "charts": state.get("charts") or [],
        "primary_chart_id": state.get("primary_chart_id"),
    }


def _jsonable_row(row) -> list:
    out = []
    for v in row:
        if isinstance(v, (_dt.date, _dt.datetime)):
            out.append(v.isoformat())
        elif isinstance(v, (bytes, bytearray)):
            try:
                out.append(v.decode("utf-8"))
            except UnicodeDecodeError:
                out.append(str(v))
        else:
            out.append(v)
    return out


__all__ = ["SheetInfo", "QaContext", "run_pipeline"]
