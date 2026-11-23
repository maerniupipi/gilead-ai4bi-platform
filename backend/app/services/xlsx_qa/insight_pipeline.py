"""
XLSX 表格 · 数据深度洞察报告（SSE streaming）

流水线：数据画像 → 四角色并行假设 → 维度规划 → 证据 SQL → 并行维度解读 → 最终总结。
"""
from __future__ import annotations

import asyncio
import datetime as _dt
import json
import logging
import re
from decimal import Decimal
import time
from dataclasses import dataclass
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from ...repositories.xlsx_qa import XlsxQaRepository
from . import llm_client
from . import prompts
from .qa_pipeline import SheetInfo
from .sql_safety import SqlSafetyError, run_select

logger = logging.getLogger(__name__)


def _sse(event: str, data: Dict[str, Any]) -> str:
    payload = json.dumps(data, ensure_ascii=False, default=_json_default)
    return f"event: {event}\ndata: {payload}\n\n"


def _json_default(v: Any) -> Any:
    if isinstance(v, (_dt.date, _dt.datetime)):
        return v.isoformat()
    if isinstance(v, float):
        return round(v, 1)
    if isinstance(v, Decimal):
        try:
            i = int(v)
            if Decimal(i) == v:
                return i
        except (ValueError, OverflowError, ArithmeticError):
            pass
        return round(float(v), 1)
    return str(v)


def _dumps(obj: Any) -> str:
    """JSON 序列化（供 LLM 上下文）：Decimal / 日期等转为可编码标量。"""
    return json.dumps(obj, ensure_ascii=False, default=_json_default)


def _jsonable_sql_row(row: Any) -> list:
    out = []
    for v in row:
        if isinstance(v, (_dt.date, _dt.datetime)):
            out.append(v.isoformat())
        elif isinstance(v, float):
            out.append(round(v, 1))
        elif isinstance(v, Decimal):
            try:
                i = int(v)
                if Decimal(i) == v:
                    out.append(i)
                    continue
            except (ValueError, OverflowError, ArithmeticError):
                pass
            out.append(round(float(v), 1))
        elif isinstance(v, (bytes, bytearray)):
            try:
                out.append(v.decode("utf-8"))
            except UnicodeDecodeError:
                out.append(str(v))
        else:
            out.append(v)
    return out


def _qi(name: str) -> str:
    return "`" + str(name).replace("`", "``") + "`"


def _col_names(columns_json: List[dict]) -> List[str]:
    out = []
    for c in columns_json or []:
        n = (c.get("column_name") or "").strip()
        if n and not n.startswith("_"):
            out.append(n)
    return out


def _is_numeric_type(ct: str) -> bool:
    u = (ct or "").upper()
    return any(x in u for x in ("INT", "DECIMAL", "FLOAT", "DOUBLE", "REAL", "NUMERIC", "BIGINT"))


_TIME_HINT = re.compile(
    r"(date|time|month|year|week|季度|年月|日期|月份)",
    re.I,
)
_METRIC_HINT = re.compile(
    r"(amount|sales|revenue|qty|quantity|price|cost|total|sum|金额|销售|销量|数量|库存|进货|回款)",
    re.I,
)
_DIM_HINT = re.compile(
    r"(region|province|city|area|country|hospital|doctor|hcp|customer|client|channel|product|sku|brand|代表|大区|省份|医院|客户|渠道|产品)",
    re.I,
)


def _hint_metric_dimension_time(raw_header: str, column_name: str, ctype: str) -> Tuple[bool, bool, bool]:
    blob = f"{raw_header} {column_name}"
    is_time = bool(_TIME_HINT.search(blob))
    is_metric = bool(_METRIC_HINT.search(blob)) or _is_numeric_type(ctype)
    is_dim = bool(_DIM_HINT.search(blob)) or (not _is_numeric_type(ctype) and not is_time)
    return is_metric, is_dim, is_time


def profile_sheet(engine: Engine, sh: SheetInfo) -> Dict[str, Any]:
    """轻量画像：行数、列统计、缺失率、数值摘要、类别 Top、启发式字段归类。"""
    table = sh.data_table_name
    cols_meta = list(sh.columns_json or [])
    names = _col_names(cols_meta)
    out: Dict[str, Any] = {
        "sheet_id": sh.sheet_id,
        "file_name": sh.file_name,
        "sheet_name": sh.sheet_name,
        "data_table_name": table,
        "total_rows": int(sh.total_rows or 0),
        "columns": [],
        "metric_candidates": [],
        "dimension_candidates": [],
        "time_candidates": [],
        "quality_flags": [],
        "numeric_summaries": {},
        "top_value_samples": {},
    }

    if not table or not names:
        out["quality_flags"].append("no_columns")
        return out

    try:
        with engine.connect() as conn:
            cnt_row = conn.execute(text(f"SELECT COUNT(*) FROM {_qi(table)}")).fetchone()
            total = int(cnt_row[0]) if cnt_row else 0
            out["total_rows"] = total
    except Exception as e:  # noqa: BLE001
        logger.warning("insight.profile count failed table=%s: %s", table, e)
        out["quality_flags"].append(f"count_failed:{e}")
        return out

    metric_candidates: List[str] = []
    dimension_candidates: List[str] = []
    time_candidates: List[str] = []

    for c in cols_meta:
        cn = (c.get("column_name") or "").strip()
        if not cn or cn.startswith("_"):
            continue
        rh = str(c.get("raw_header") or "")
        ctype = str(c.get("column_type") or "")
        is_metric, is_dim, is_time = _hint_metric_dimension_time(rh, cn, ctype)

        col_profile: Dict[str, Any] = {"column_name": cn, "column_type": ctype, "raw_header": rh}

        try:
            with engine.connect() as conn:
                r1 = conn.execute(
                    text(
                        f"SELECT COUNT(DISTINCT {_qi(cn)}), SUM({_qi(cn)} IS NULL) "
                        f"FROM {_qi(table)}"
                    )
                ).fetchone()
                distinct_n = int(r1[0] or 0) if r1 else 0
                null_n = int(r1[1] or 0) if r1 else 0
                null_pct = (null_n / total * 100.0) if total else 0.0
                col_profile["distinct_count"] = distinct_n
                col_profile["null_pct"] = round(null_pct, 1)

                if null_pct > 30:
                    out["quality_flags"].append(f"{cn}: missing≈{null_pct:.1f}%")
                if total and distinct_n <= 1:
                    out["quality_flags"].append(f"{cn}: almost_constant")

                if _is_numeric_type(ctype):
                    r2 = conn.execute(
                        text(
                            f"SELECT MIN({_qi(cn)}), MAX({_qi(cn)}), AVG({_qi(cn)}) "
                            f"FROM {_qi(table)} WHERE {_qi(cn)} IS NOT NULL"
                        )
                    ).fetchone()
                    if r2:
                        sm = {
                            "min": _json_default(r2[0]) if r2[0] is not None else None,
                            "max": _json_default(r2[1]) if r2[1] is not None else None,
                            "avg": round(float(r2[2]), 1) if r2[2] is not None else None,
                        }
                        col_profile["numeric_summary"] = sm
                        out["numeric_summaries"][cn] = sm
                        mn, mx = sm.get("min"), sm.get("max")
                        try:
                            if mn is not None and mx is not None and float(mx) != float(mn):
                                ratio = abs(float(mx) / float(mn)) if float(mn) not in (0, 0.0) else None
                                if ratio and ratio > 1000:
                                    out["quality_flags"].append(f"{cn}: wide_numeric_range")
                        except (TypeError, ValueError):
                            pass

                if distinct_n <= 50 and distinct_n > 0 and not _is_numeric_type(ctype):
                    tops = conn.execute(
                        text(
                            f"SELECT {_qi(cn)}, COUNT(*) AS cnt FROM {_qi(table)} "
                            f"WHERE {_qi(cn)} IS NOT NULL GROUP BY {_qi(cn)} "
                            f"ORDER BY cnt DESC LIMIT 5"
                        )
                    ).fetchall()
                    out["top_value_samples"][cn] = [(row[0], int(row[1])) for row in tops]
        except Exception as e:  # noqa: BLE001
            logger.warning("insight.profile col=%s table=%s: %s", cn, table, e)
            col_profile["profile_error"] = str(e)

        if is_time:
            time_candidates.append(cn)
        if is_metric:
            metric_candidates.append(cn)
        if is_dim:
            dimension_candidates.append(cn)

        out["columns"].append(col_profile)

    def _uniq(xs: List[str]) -> List[str]:
        seen = set()
        r = []
        for x in xs:
            if x not in seen:
                seen.add(x)
                r.append(x)
        return r

    out["metric_candidates"] = _uniq(metric_candidates)[:12]
    out["dimension_candidates"] = _uniq(dimension_candidates)[:12]
    out["time_candidates"] = _uniq(time_candidates)[:8]

    return out


def _multi_schema_block(ctx_sheets: List[SheetInfo]) -> str:
    return prompts.build_schema_prompt(active_sheets=ctx_sheets)


def _resolve_sheet_by_id(sheets: List[SheetInfo], sid: Any) -> SheetInfo:
    try:
        want = int(sid)
    except (TypeError, ValueError):
        return sheets[0]
    for s in sheets:
        if int(s.sheet_id) == want:
            return s
    return sheets[0]


def _normalize_sheet_id(sheets: List[SheetInfo], sid: Any) -> int:
    """Return a valid sheet id so planner output cannot drift from available sheets."""
    resolved = _resolve_sheet_by_id(sheets, sid)
    return int(resolved.sheet_id)


def _match_col(name: Optional[str], sq_cols: List[str]) -> Optional[str]:
    if not name:
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


def _auto_chart_fields(cols: List[str], rows: List[list]) -> Tuple[Optional[str], List[str]]:
    if len(cols) < 2 or not rows:
        return None, []

    def _isnum(v: Any) -> bool:
        if isinstance(v, (int, float)):
            return True
        s = str(v).strip().replace(",", "").replace(" ", "").replace("%", "")
        try:
            float(s)
            return True
        except (TypeError, ValueError):
            return False

    dim = cols[0]
    numeric_cols: List[str] = []
    for i, c in enumerate(cols[1:], start=1):
        sample = [r[i] for r in rows[:25] if i < len(r) and r[i] is not None]
        if not sample:
            continue
        ok = sum(1 for v in sample if _isnum(v))
        if ok >= max(1, int(len(sample) * 0.65)):
            numeric_cols.append(c)
    return dim, numeric_cols[:2] or ([cols[1]] if len(cols) > 1 else [])


def _chart_payload(
    *,
    cols: List[str],
    rows: List[list],
    chart_type: str,
    dimension_field: Optional[str],
    metric_fields: Optional[List[str]],
    title: str,
) -> Dict[str, Any]:
    ctype = (chart_type or "table").strip().lower()
    if ctype not in {"bar", "line", "pie", "table"}:
        ctype = "bar"

    dim = _match_col(dimension_field, cols)
    metrics = [_match_col(m, cols) for m in (metric_fields or [])]
    metrics = [m for m in metrics if m]

    if ctype != "table" and (not dim or not metrics):
        auto_dim, auto_metrics = _auto_chart_fields(cols, rows)
        if auto_dim and auto_metrics:
            dim, metrics = auto_dim, auto_metrics
        else:
            ctype = "table"

    return {
        "subquestion_id": "insight",
        "chart_type": ctype,
        "title": title or "",
        "explain": "",
        "dimension_field": dim if ctype != "table" else None,
        "metric_fields": metrics if ctype != "table" else [],
        "columns": cols,
        "rows": rows[:100],
        "role": "secondary",
    }


async def _evidence_sql(
    choice: llm_client.LlmChoice,
    *,
    schema_block: str,
    evidence_question: str,
    evidence_type: str,
    table_name: str,
    language: Optional[str],
) -> Dict[str, Any]:
    sys = prompts._with_language_policy(prompts.INSIGHT_EVIDENCE_SQL_SYSTEM, language).replace(
        "{table_name}", table_name
    )
    user = (
        f"{schema_block}\n\n"
        f"=== EVIDENCE TYPE ===\n{evidence_type}\n\n"
        f"=== BUSINESS QUESTION ===\n{evidence_question}\n"
    )
    return await llm_client.chat_json(
        choice,
        system=sys,
        user=user,
        temperature=0.1,
        max_tokens=1800,
    )


ROLE_DEFINITIONS: List[Tuple[str, str, str]] = [
    (
        "sales",
        "市场增长动因与机会结构深度研判",
        "销量与达成、区域/医院/零售终端表现、产品与竞品动态、机会客户与增长点。",
    ),
    (
        "management",
        "组织效能与资源配置协同优化研判",
        "团队效率与资源配置、KPI 拆解与达成路径、流程瓶颈、投入产出与管理抓手。",
    ),
    (
        "boss",
        "经营质量与战略回报及综合风险研判",
        "整体营收结构、增长质量、盈利能力线索（若缺成本字段需谨慎）、战略重心与重大风险。",
    ),
    (
        "operations",
        "全链路履约与成本效率优化深度研判",
        "供应链与库存周转、渠道履约与覆盖、运营效率与成本结构（字段允许时）。",
    ),
]


def _dim_public(d: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": d.get("id"),
        "title": d.get("title"),
        "display_title": d.get("display_title") or _compact_dimension_title(d.get("title")),
        "why_selected": d.get("why_selected"),
        "score": d.get("score"),
        "scores": d.get("scores"),
        "data_support_notes": d.get("data_support_notes"),
        "target_sheet_id": d.get("target_sheet_id"),
        "questions": d.get("questions") or [],
    }


def _compact_dimension_title(title: Any, *, max_chars: int = 10) -> str:
    """Short title for cards; full title remains available for analysis."""
    s = str(title or "").strip()
    if not s:
        return ""
    s = re.sub(r"[（(].*?[）)]", "", s).strip()
    s = re.sub(r"\s+", "", s)
    return s[:max_chars]


def _fallback_dimensions(sheets: List[SheetInfo]) -> List[Dict[str, Any]]:
    """Planner 失败时的兜底五维度假设。"""
    sh = sheets[0]
    sid = sh.sheet_id

    def _dim(i: int, title: str, qs: List[Tuple[str, str, str]]) -> Dict[str, Any]:
        return {
            "id": f"dim_fallback_{i}",
            "target_sheet_id": sid,
            "title": title,
            "display_title": _compact_dimension_title(title),
            "why_selected": "自动兜底维度（规划模型不可用或输出不完整）。",
            "score": 40,
            "scores": {},
            "data_support_notes": "",
            "questions": [{"id": f"q{i}_{j}", "type": t, "text": tx} for j, (t, tx) in enumerate(qs)],
        }

    return [
        _dim(
            1,
            "总体规模与结构",
            [
                ("overview", "当前数据集的行数规模如何？有哪些关键字段？"),
                ("drilldown", "按最主要的分类字段拆分，占比结构如何？"),
                ("anomaly", "是否存在极端值或缺失严重的字段？"),
                ("priority", "哪些关键分组最需要管理层优先关注？"),
            ],
        ),
        _dim(
            2,
            "核心业务分布",
            [
                ("overview", "核心业务指标（若存在数值字段）的总体水平？"),
                ("drilldown", "若存在区域/渠道/产品字段，拆分对比表现？"),
                ("anomaly", "是否存在集中度异常（头部过高或长尾过重）？"),
                ("priority", "Top 分组与尾部分组之间的差距有多大？"),
            ],
        ),
        _dim(
            3,
            "时间与趋势线索",
            [
                ("overview", "若存在时间字段，覆盖的时间范围是什么？"),
                ("drilldown", "按时间粒度聚合后的走势如何？"),
                ("anomaly", "是否存在明显的异常时间段？"),
                ("priority", "哪些时间段最值得优先复盘？"),
            ],
        ),
        _dim(
            4,
            "增长与运营关注点",
            [
                ("overview", "从字段命名推断，可能与销量/库存/渠道相关的信号？"),
                ("drilldown", "交叉维度下的差异主要体现在哪里？"),
                ("anomaly", "有哪些潜在的数据质量问题会影响结论？"),
                ("priority", "哪些业务切片最适合作为下一步重点分析对象？"),
            ],
        ),
        _dim(
            5,
            "数据质量与完整性评估",
            [
                ("overview", "各字段的填充率、缺失率或异常值情况如何？"),
                ("drilldown", "不同维度组合下的数据完整性差异？"),
                ("anomaly", "是否存在系统性数据采集偏差或口径不一致？"),
                ("priority", "哪些数据问题最可能影响业务判断的可靠性？"),
            ],
        ),
    ]


def _normalize_dimensions(raw: List[Dict[str, Any]], sheets: List[SheetInfo]) -> List[Dict[str, Any]]:
    base_sid = sheets[0].sheet_id
    cleaned: List[Dict[str, Any]] = []
    for i, d in enumerate(raw or []):
        if not isinstance(d, dict):
            continue
        dim_id = str(d.get("id") or "").strip() or f"dim{i + 1}"
        title = str(d.get("title") or "").strip() or f"分析维度 {i + 1}"
        display_title = str(d.get("display_title") or "").strip() or _compact_dimension_title(title)
        display_title = _compact_dimension_title(display_title)
        qs_in = d.get("questions") if isinstance(d.get("questions"), list) else []
        questions = []
        for j, q in enumerate(qs_in):
            if not isinstance(q, dict):
                continue
            qt = str(q.get("type") or "overview").strip()
            qtext = str(q.get("text") or "").strip()
            qid = str(q.get("id") or "").strip() or f"{dim_id}_q{j + 1}"
            if qtext:
                questions.append({"id": qid, "type": qt, "text": qtext})
        tsid = _normalize_sheet_id(sheets, d.get("target_sheet_id") or base_sid)
        cleaned.append(
            {
                "id": dim_id,
                "title": title,
                "display_title": display_title,
                "why_selected": str(d.get("why_selected") or "").strip(),
                "score": d.get("score"),
                "scores": d.get("scores") if isinstance(d.get("scores"), dict) else {},
                "data_support_notes": str(d.get("data_support_notes") or "").strip(),
                "target_sheet_id": tsid,
                "questions": questions[:6],
            }
        )

    cleaned = [d for d in cleaned if (d.get("questions") or [])]
    if len(cleaned) >= 5:
        return cleaned[:5]

    fb = _fallback_dimensions(sheets)
    merged = cleaned + [x for x in fb if x["id"] not in {c["id"] for c in cleaned}]
    return merged[:5]


@dataclass
class InsightContext:
    db: Session
    engine: Engine
    module_id: int
    module_name: str
    active_sheets: List[SheetInfo]
    module_understanding_md: Optional[str]
    llm_provider_id: Optional[int]
    llm_model: Optional[str]
    language: Optional[str] = None
    sql_max_rows: int = 1000
    sql_timeout_ms: int = 10000
    max_queries_per_dimension: int = 5
    dimension_stream_timeout: int = 150
    final_stream_timeout: int = 180


async def run_insight_pipeline(ctx: InsightContext) -> AsyncIterator[str]:
    t0 = time.time()
    sheets = ctx.active_sheets
    role_cards_state: List[Dict[str, Any]] = []
    dimensions_state: List[Dict[str, Any]] = []
    evidence_by_dim: Dict[str, List[Dict[str, Any]]] = {}
    dim_markdown: Dict[str, str] = {}
    final_buf: List[str] = []

    def _persist_report(**kwargs: Any) -> None:
        try:
            XlsxQaRepository.update_insight_report(ctx.db, ctx.module_id, **kwargs)
            ctx.db.commit()
        except Exception as e:  # noqa: BLE001
            logger.warning("insight.persist failed module=%s: %s", ctx.module_id, e)
            try:
                ctx.db.rollback()
            except Exception:  # noqa: BLE001
                pass

    try:
        XlsxQaRepository.create_or_reset_insight_report(ctx.db, ctx.module_id)
        ctx.db.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning("insight.persist reset failed module=%s: %s", ctx.module_id, e)
        try:
            ctx.db.rollback()
        except Exception:  # noqa: BLE001
            pass

    yield _sse(
        "insight_start",
        {"message": "开始生成数据深度洞察报告…", "module_id": ctx.module_id},
    )

    try:
        choice = llm_client.resolve_llm(
            ctx.db,
            provider_id=ctx.llm_provider_id,
            model=ctx.llm_model,
        )
    except HTTPException as e:
        _persist_report(status="failed", phase="resolve_llm", error_message=str(e.detail))
        yield _sse("insight_error", {"stage": "resolve_llm", "message": str(e.detail)})
        return

    profile_bundle: Dict[str, Any] = {"sheets": [], "generated_at": _dt.datetime.utcnow().isoformat()}

    yield _sse("profile_start", {"message": "正在扫描数据结构…"})
    try:
        tasks = [asyncio.to_thread(profile_sheet, ctx.engine, sh) for sh in sheets]
        profile_results = await asyncio.gather(*tasks)
        profile_bundle["sheets"] = list(profile_results)
        _persist_report(phase="roles")
        yield _sse("profile_result", {"profile": profile_bundle})
    except Exception as e:  # noqa: BLE001
        logger.warning("insight.profile fatal: %s", e)
        _persist_report(phase="roles")
        yield _sse("profile_result", {"profile": profile_bundle, "warning": str(e)})

    schema_all = _multi_schema_block(sheets)
    profile_json = _dumps(profile_bundle)

    async def _role_task(role_key: str, role_name: str, role_desc: str) -> Dict[str, Any]:
        sys_tmpl = prompts.INSIGHT_ROLE_SYSTEM.format(role_name=role_name, role_desc=role_desc)
        system = prompts._with_language_policy(sys_tmpl, ctx.language)
        user = (
            f"{schema_all}\n\n"
            f"=== MODULE UNDERSTANDING ===\n{ctx.module_understanding_md or '(none)'}\n\n"
            f"=== DATA PROFILE JSON ===\n{profile_json}\n\n"
            "Return JSON only."
        )
        return await llm_client.chat_json(
            choice,
            system=system,
            user=user,
            temperature=0.35,
            max_tokens=4400,
        )

    for rk, rn, _rd in ROLE_DEFINITIONS:
        yield _sse("role_start", {"role": rk, "name": rn, "message": f"{rn}研判中…"})

    role_results: List[Dict[str, Any]] = []
    tasks = [_role_task(rk, rn, rd) for rk, rn, rd in ROLE_DEFINITIONS]
    raw_roles = await asyncio.gather(*tasks, return_exceptions=True)

    for (rk, rn, rd), res in zip(ROLE_DEFINITIONS, raw_roles):
        if isinstance(res, Exception):
            logger.warning("insight.role failed role=%s: %s", rk, res)
            payload = {
                "role": rk,
                "name": rn,
                "error": str(res),
                "hypotheses": [],
                "role_summary": "",
                "thinking_feedback": "",
            }
            role_results.append(payload)
            role_cards_state.append({**payload, "done": True})
            _persist_report(phase="roles", role_cards_json=role_cards_state)
            yield _sse("role_result", payload)
            continue
        res = res if isinstance(res, dict) else {}
        res.setdefault("role", rk)
        res.setdefault("role_name", rn)
        role_summary = str(res.get("role_summary") or "").strip()
        thinking_feedback = str(res.get("thinking_feedback") or "").strip()
        role_results.append(res)
        role_payload = {
            "role": rk,
            "name": rn,
            "done": True,
            "hypotheses": res.get("hypotheses") or [],
            "role_summary": role_summary,
            "thinking_feedback": thinking_feedback,
            "error": "",
        }
        role_cards_state.append(role_payload)
        _persist_report(phase="roles", role_cards_json=role_cards_state)
        yield _sse(
            "role_result",
            {
                "role": rk,
                "name": rn,
                "hypotheses": res.get("hypotheses") or [],
                "role_summary": role_summary,
                "thinking_feedback": thinking_feedback,
            },
        )

    sheet_index = "\n".join(
        f"- sheet_id={s.sheet_id}: {s.file_name} / {s.sheet_name} → `{s.data_table_name}`"
        for s in sheets
    )

    planner_payload = {"message": "正在提炼分析维度…"}
    yield _sse("merge_start", planner_payload)
    yield _sse("planner_start", planner_payload)
    planner_user = (
        f"{schema_all}\n\n"
        f"=== MODULE UNDERSTANDING ===\n{ctx.module_understanding_md or '(none)'}\n\n"
        f"=== DATA PROFILE JSON ===\n{profile_json}\n\n"
        f"=== AVAILABLE SHEETS ===\n{sheet_index}\n\n"
        "=== ROLE HYPOTHESES (JSON) ===\n"
        f"{_dumps(role_results)}\n"
    )

    dims_raw: List[Dict[str, Any]] = []
    try:
        plan_obj = await llm_client.chat_json(
            choice,
            system=prompts._with_language_policy(prompts.INSIGHT_PLANNER_SYSTEM, ctx.language),
            user=planner_user,
            temperature=0.25,
            max_tokens=4400,
        )
        dims_raw = plan_obj.get("dimensions") if isinstance(plan_obj, dict) else []
        if not isinstance(dims_raw, list):
            dims_raw = []
    except Exception as e:  # noqa: BLE001
        logger.warning("insight.planner failed: %s", e)
        dims_raw = []

    dimensions = _normalize_dimensions(dims_raw, sheets)
    dimensions_state = [_dim_public(d) for d in dimensions]
    evidence_by_dim = {d["id"]: [] for d in dimensions}

    _persist_report(phase="evidence", dimensions_json=dimensions_state, evidence_json=evidence_by_dim)
    yield _sse("dimensions_result", {"dimensions": dimensions_state})

    yield _sse(
        "query_plan_start",
        {
            "message": "并行生成证据查询…",
            "dimensions": [{"id": d["id"], "question_count": len(d.get("questions") or [])} for d in dimensions],
        },
    )

    sem = asyncio.Semaphore(4)

    async def _run_one_query(
        dim_id: str,
        qid: str,
        qtype: str,
        qtext: str,
        sheet: SheetInfo,
    ) -> Dict[str, Any]:
        schema_single = prompts.build_schema_prompt(
            file_name=sheet.file_name,
            sheet_name=sheet.sheet_name,
            data_table_name=sheet.data_table_name,
            total_rows=sheet.total_rows or 0,
            columns=sheet.columns_json,
            understanding_md=sheet.understanding_md or None,
        )
        err = "unknown_error"
        async with sem:
            try:
                sql_obj = await _evidence_sql(
                    choice,
                    schema_block=schema_single,
                    evidence_question=qtext,
                    evidence_type=qtype,
                    table_name=sheet.data_table_name,
                    language=ctx.language,
                )
            except HTTPException as e:
                return {
                    "dim_id": dim_id,
                    "question_id": qid,
                    "evidence_type": qtype,
                    "business_question": qtext,
                    "supported": False,
                    "error": str(e.detail),
                }

            if not sql_obj.get("supported", True):
                return {
                    "dim_id": dim_id,
                    "question_id": qid,
                    "evidence_type": qtype,
                    "business_question": qtext,
                    "supported": False,
                    "reason": sql_obj.get("explain") or "not_supported",
                }

            sql = (sql_obj.get("sql") or "").strip()
            if not sql:
                return {
                    "dim_id": dim_id,
                    "question_id": qid,
                    "evidence_type": qtype,
                    "business_question": qtext,
                    "supported": False,
                    "reason": "empty_sql",
                }

            try:
                cols, rows, _, truncated = await asyncio.to_thread(
                    run_select,
                    ctx.engine,
                    sql,
                    allowed_tables=[sheet.data_table_name],
                    max_rows=ctx.sql_max_rows,
                    timeout_ms=ctx.sql_timeout_ms,
                )
                cols_list = list(cols)
                rows_list = [_jsonable_sql_row(r) for r in rows]
                fetched_rows = len(rows_list)
                # run_select 的第三返回值等于 len(rows)；截断时表示至少还有一行未返回
                total_rows = fetched_rows + 1 if truncated else fetched_rows
                chart = _chart_payload(
                    cols=cols_list,
                    rows=rows_list,
                    chart_type=str(sql_obj.get("chart_type") or "bar"),
                    dimension_field=sql_obj.get("dimension_field"),
                    metric_fields=sql_obj.get("metric_fields"),
                    title=qtext[:80],
                )
                return {
                    "dim_id": dim_id,
                    "question_id": qid,
                    "evidence_type": qtype,
                    "business_question": qtext,
                    "supported": True,
                    "sql": sql,
                    "explain": sql_obj.get("explain") or "",
                    "columns": cols_list,
                    "rows": rows_list,
                    "total_rows": total_rows,
                    "fetched_rows": fetched_rows,
                    "truncated": bool(truncated),
                    "chart": chart,
                }
            except SqlSafetyError as e:
                err = str(e)
            except Exception as e:  # noqa: BLE001
                err = str(e)

            return {
                "dim_id": dim_id,
                "question_id": qid,
                "evidence_type": qtype,
                "business_question": qtext,
                "supported": False,
                "sql": sql,
                "error": err,
            }

    pending_jobs: List[Tuple[str, str, str, str, SheetInfo]] = []
    for d in dimensions:
        sheet = _resolve_sheet_by_id(sheets, d.get("target_sheet_id"))
        qs = (d.get("questions") or [])[: ctx.max_queries_per_dimension]
        for q in qs:
            qid = str(q.get("id") or "").strip()
            qtype = str(q.get("type") or "overview")
            qtext = str(q.get("text") or "").strip()
            if not qtext:
                continue
            if not qid:
                qid = f"{d['id']}_q_{len(pending_jobs)}"
            pending_jobs.append((d["id"], qid, qtype, qtext, sheet))

    for dim_id, qid, qtype, _qtext, _sh in pending_jobs:
        yield _sse(
            "query_start",
            {
                "dim_id": dim_id,
                "question_id": qid,
                "evidence_type": qtype,
                "message": "生成查询…",
            },
        )

    async def _job(meta: Tuple[str, str, str, str, SheetInfo]) -> Dict[str, Any]:
        dim_id, qid, qtype, qtext, sheet = meta
        try:
            return await _run_one_query(dim_id, qid, qtype, qtext, sheet)
        except Exception as e:  # noqa: BLE001
            logger.warning("insight.query unexpected failed dim=%s q=%s: %s", dim_id, qid, e)
            return {
                "dim_id": dim_id,
                "question_id": qid,
                "evidence_type": qtype,
                "business_question": qtext,
                "supported": False,
                "error": str(e),
            }

    query_tasks = [asyncio.create_task(_job(m)) for m in pending_jobs]

    for finished in asyncio.as_completed(query_tasks):
        try:
            res = await finished
        except Exception as e:  # noqa: BLE001
            res = e
        if isinstance(res, Exception):
            logger.warning("insight.query failed: %s", res)
            continue
        if not isinstance(res, dict):
            continue
        payload = {k: v for k, v in res.items() if k != "sql"}
        if res.get("supported"):
            payload["sql"] = res.get("sql")
        yield _sse("query_result", payload)
        did = res.get("dim_id")
        if did:
            evidence_by_dim.setdefault(str(did), []).append(res)
            _persist_report(phase="evidence", evidence_json=evidence_by_dim)

    queue: asyncio.Queue = asyncio.Queue()
    stream_sem = asyncio.Semaphore(min(4, max(1, len(dimensions))))

    def _profile_for_sheet(sheet_id: Any) -> Dict[str, Any]:
        sid = _normalize_sheet_id(sheets, sheet_id)
        for item in profile_bundle.get("sheets") or []:
            try:
                if int(item.get("sheet_id")) == sid:
                    return item
            except (TypeError, ValueError):
                continue
        return {}

    async def _dimension_writer(dim: Dict[str, Any]) -> None:
        dim_id = dim["id"]
        dim_title = dim.get("title") or dim_id
        evs = evidence_by_dim.get(dim_id) or []

        buf: List[str] = []
        try:
            sheet = _resolve_sheet_by_id(sheets, dim.get("target_sheet_id"))

            await queue.put({"kind": "start", "dim_id": dim_id})
            sys_tmpl = prompts.INSIGHT_DIM_ANALYSIS_SYSTEM.replace("{dimension_title}", dim_title)
            system = prompts._with_language_policy(sys_tmpl, ctx.language)
            schema_single = prompts.build_schema_prompt(
                file_name=sheet.file_name,
                sheet_name=sheet.sheet_name,
                data_table_name=sheet.data_table_name,
                total_rows=sheet.total_rows or 0,
                columns=sheet.columns_json,
                understanding_md=sheet.understanding_md or None,
            )
            user = (
                f"{schema_single}\n\n"
                f"=== MODULE UNDERSTANDING ===\n{ctx.module_understanding_md or '(none)'}\n\n"
                f"=== TARGET SHEET PROFILE JSON ===\n"
                f"{_dumps(_profile_for_sheet(sheet.sheet_id))}\n\n"
                f"=== DIMENSION META ===\n{_dumps(_dim_public(dim))}\n\n"
                "=== CURATED EVIDENCE DIGEST (prefer these facts for narrative and tables) ===\n"
                f"{_dumps(_evidence_digest(evs))}\n\n"
                "=== QUERY EVIDENCE (JSON, truncated rows) ===\n"
                f"{_dumps(_evidence_compact(evs))}\n"
            )
            logger.info(
                "insight.dimension_writer stream_prepare dim=%s evidence_n=%d user_chars=%d",
                dim_id,
                len(evs),
                len(user),
            )
            try:
                async with stream_sem:
                    async with asyncio.timeout(ctx.dimension_stream_timeout):
                        async for delta in llm_client.chat_stream(
                            choice,
                            system=system,
                            user=user,
                            temperature=0.35,
                            max_tokens=6200,
                            timeout=float(ctx.dimension_stream_timeout),
                            stream_label=f"insight_dim:{dim_id}",
                        ):
                            buf.append(delta)
                            await queue.put({"kind": "delta", "dim_id": dim_id, "delta": delta})
            except TimeoutError:
                logger.warning("insight.dimension_stream timeout dim=%s", dim_id)
                err_txt = "\n\n（本维度解读等待模型响应超时，已跳过。已有证据图表仍可参考。）\n"
                buf.append(err_txt)
                await queue.put({"kind": "delta", "dim_id": dim_id, "delta": err_txt})
            except Exception as e:  # noqa: BLE001
                logger.warning("insight.dimension_stream failed dim=%s: %s", dim_id, e)
                err_txt = f"\n\n（本维度解读生成失败：{e}）\n"
                buf.append(err_txt)
                await queue.put({"kind": "delta", "dim_id": dim_id, "delta": err_txt})
        except Exception as e:  # noqa: BLE001
            logger.exception("insight.dimension_writer setup failed dim=%s", dim_id)
            err_txt = f"\n\n（本维度解读前置步骤失败：{e}）\n"
            buf.append(err_txt)
            try:
                await queue.put({"kind": "delta", "dim_id": dim_id, "delta": err_txt})
            except Exception:  # noqa: BLE001
                pass
        finally:
            dim_markdown[dim_id] = "".join(buf)
            await queue.put({"kind": "done_dim", "dim_id": dim_id})

    writers = [asyncio.create_task(_dimension_writer(d)) for d in dimensions]
    pending_done = len(writers)

    try:
        while pending_done > 0:
            msg = await queue.get()
            k = msg.get("kind")
            if k == "start":
                yield _sse("dimension_analysis_start", {"dim_id": msg["dim_id"]})
            elif k == "delta":
                yield _sse(
                    "dimension_analysis_delta",
                    {"dim_id": msg["dim_id"], "delta": msg.get("delta") or ""},
                )
            elif k == "done_dim":
                yield _sse("dimension_analysis_done", {"dim_id": msg["dim_id"]})
                _persist_report(
                    phase="dim_analysis",
                    dim_texts_json=dim_markdown,
                    evidence_json=evidence_by_dim,
                )
                pending_done -= 1
    finally:
        await asyncio.gather(*writers, return_exceptions=True)

    yield _sse("final_start", {"message": "正在生成洞察总结…"})
    _persist_report(phase="final", dim_texts_json=dim_markdown)
    final_system = prompts._with_language_policy(prompts.INSIGHT_FINAL_SYSTEM, ctx.language)
    final_user = _dumps(
        {
            "dimension_reports": dim_markdown,
            "dimensions": dimensions_state,
            "evidence_digest": {k: _evidence_digest(v) for k, v in evidence_by_dim.items()},
            "evidence": _evidence_compact_all(evidence_by_dim),
            "module_name": ctx.module_name,
        },
    )
    try:
        async with asyncio.timeout(ctx.final_stream_timeout):
            async for delta in llm_client.chat_stream(
                choice,
                system=final_system,
                user=final_user,
                temperature=0.35,
                max_tokens=7600,
                timeout=float(ctx.final_stream_timeout),
                stream_label="insight_final",
            ):
                final_buf.append(delta)
                yield _sse("final_delta", {"delta": delta})
    except TimeoutError:
        _persist_report(
            status="failed",
            phase="final",
            final_md="".join(final_buf),
            error_message="最终总结等待模型响应超时，已结束本次报告。",
        )
        yield _sse(
            "insight_error",
            {"stage": "final_stream", "message": "最终总结等待模型响应超时，已结束本次报告。"},
        )
        return
    except Exception as e:  # noqa: BLE001
        _persist_report(status="failed", phase="final", final_md="".join(final_buf), error_message=str(e))
        yield _sse("insight_error", {"stage": "final_stream", "message": str(e)})
        return

    yield _sse("final_done", {})

    elapsed_ms = int((time.time() - t0) * 1000)
    _persist_report(
        status="done",
        phase="done",
        role_cards_json=role_cards_state,
        dimensions_json=dimensions_state,
        evidence_json=evidence_by_dim,
        dim_texts_json=dim_markdown,
        final_md="".join(final_buf),
        elapsed_ms=elapsed_ms,
        error_message=None,
    )
    yield _sse(
        "insight_done",
        {
            "elapsed_ms": elapsed_ms,
            "dimensions": dimensions_state,
        },
    )


def _evidence_compact(evs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for e in evs:
        out.append(
            {
                "question_id": e.get("question_id"),
                "evidence_type": e.get("evidence_type"),
                "business_question": e.get("business_question"),
                "supported": e.get("supported"),
                "columns": e.get("columns"),
                "rows": (e.get("rows") or [])[:30],
                "total_rows": e.get("total_rows"),
                "fetched_rows": e.get("fetched_rows", len(e.get("rows") or [])),
                "truncated": e.get("truncated"),
                "chart": e.get("chart"),
                "error": e.get("error"),
                "reason": e.get("reason"),
            }
        )
    return out


def _evidence_digest(evs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Create a curated evidence view so report tables focus on key content."""
    digest: List[Dict[str, Any]] = []
    for e in evs:
        rows = e.get("rows") or []
        cols = e.get("columns") or []
        supported = bool(e.get("supported"))
        item: Dict[str, Any] = {
            "question_id": e.get("question_id"),
            "evidence_type": e.get("evidence_type"),
            "business_question": e.get("business_question"),
            "supported": supported,
        }
        if not supported:
            item["reason"] = e.get("reason") or e.get("error")
            digest.append(item)
            continue

        item["columns"] = cols
        item["row_count"] = len(rows)
        item["key_rows"] = rows[:6]
        if len(rows) > 6:
            item["tail_rows"] = rows[-3:]

        numeric_cols: List[Tuple[int, str]] = []
        for idx, col in enumerate(cols):
            sample = [r[idx] for r in rows[:20] if idx < len(r) and r[idx] is not None]
            if not sample:
                continue
            ok = 0
            for v in sample:
                try:
                    float(str(v).replace(",", "").replace("%", "").strip())
                    ok += 1
                except (TypeError, ValueError):
                    pass
            if ok >= max(1, int(len(sample) * 0.65)):
                numeric_cols.append((idx, col))

        ranges = []
        for idx, col in numeric_cols[:3]:
            vals: List[float] = []
            for r in rows:
                if idx >= len(r) or r[idx] is None:
                    continue
                try:
                    vals.append(float(str(r[idx]).replace(",", "").replace("%", "").strip()))
                except (TypeError, ValueError):
                    continue
            if vals:
                ranges.append(
                    {
                        "metric": col,
                        "min": round(min(vals), 1),
                        "max": round(max(vals), 1),
                        "avg": round(sum(vals) / len(vals), 1),
                    }
                )
        if ranges:
            item["numeric_ranges"] = ranges

        digest.append(item)
    return digest


def _evidence_compact_all(by_dim: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    return {k: _evidence_compact(v) for k, v in by_dim.items()}
