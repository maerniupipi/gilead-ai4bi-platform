"""
AutoBI 实验室 HTTP 网关：与前端 runAutobiLabPipelineReal 同序执行；全量步骤写入 Redis（追踪日志）。
对话列表与轮次正文由 chat-state 接口存 MySQL。响应体仅 SSE 输出 trace_id + 数据总结增量。
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.schemas.autobi_atomic import (
    ESValueRetrieverRequest,
    ESKnowledgeRetrieverRequest,
    MultiGlobalValueMetaRetrieverRequest,
    NerRetrieverRequest,
    NerRetrieverResponse,
    SQLTemplateRetrieverRequest,
    TableMetaRetrieverRequest,
    TableValueRetrieverRequest,
    GlobalValueMetaRetrieverRequest,
)
from app.schemas.chat import ChatRequest
from app.services.chat.service import ChatService
from app.services.knowledge.autobi_atomic import AutoBIAtomicService
from app.services.knowledge.knowledge_base.service import (
    execute_knowledge_base_sql_service,
    get_knowledge_base_database_type_service,
)

from app.core.redis_client import trace_set
from app.core.trace_writer import write_trace
from app.core.execution import read_database
from app.core.model_observation import collect_model_usage
from .lab_tool_outputs import output_stage, recall_items, sql_output
from app.repositories.knowledge.knowledge_base.repository import list_kb_recall_field_descriptions
from .lab_prompt_agg import (
    build_bi_summary_user_message,
    build_icl_example_prompt_data,
    build_knowledge_knowledge_map_object,
    build_knowledge_words_for_prompt,
    build_long_es_query_with_annotations,
    build_qs_recall,
    build_table_field_prompt_data,
    build_step_feature_values,
    collect_field_codes_for_multi_column,
    collect_field_tables_from_meta_steps,
    collect_qs_recall_values,
    extract_sql_from_model_text,
    format_sql_execute_result_for_summary,
    normalize_rewritten_query,
    parse_chart_spec_from_llm,
    parse_ner_entities_from_llm,
    replace_template_vars,
    strip_lab_template_noise,
    to_json_safe,
)
from .lab_features import replace_features_in_template, without_runtime_features

logger = logging.getLogger(__name__)

_COLORS = [
    "#5B8FF9",
    "#61DDAA",
    "#65789B",
    "#F6BD16",
    "#7262FD",
    "#78D3F8",
    "#9661BC",
    "#F6903D",
    "#008685",
    "#F08BB4",
    "#9AD681",
    "#FF9845",
    "#1E9493",
    "#FF99C3",
    "#BD6EAF",
    "#5AD8A6",
    "#9270CA",
    "#E8684A",
    "#269A99",
]


def _pipeline_steps_meta() -> List[Dict[str, Any]]:
    raw = [
        (1, "ES表值召回", "elasticsearch-value-retriever"),
        (2, "elasticsearch-alias（跳过）", "pipeline-skip"),
        (3, "ES知识词召回", "elasticsearch-knowledge-retriever"),
        (4, "知识改写", "knowledge-rewrite"),
        (5, "SQL样例精准查询（跳过）", "pipeline-skip"),
        (6, "表字段召回", "table-meta-retriever"),
        (7, "表值召回(对应字段)", "global-value-meta-retriever"),
        (8, "SQL样例召回", "icl-template-retriever"),
        (9, "ES表值召回（双次检索合并）", "elasticsearch-value-retriever"),
        (10, "elasticsearch-alias（跳过）", "pipeline-skip"),
        (11, "表值召回", "table-value-retriever"),
        (12, "多列同值召回", "multi-global-value-meta-retriever"),
        (13, "NER 大模型召回", "ner-retrieval"),
        (14, "nl2sql", "nl2sql"),
        (15, "SQL改写", "sql-permission-rewrite"),
        (16, "sql-data-retriever", "sql-data-retriever"),
        (17, "数据总结", "bi-data-summary"),
        (18, "智能图表配置", "chart-spec"),
    ]
    out = []
    for sid, title, api_key in raw:
        out.append(
            {
                "stepId": sid,
                "title": title,
                "apiKey": api_key,
                "color": _COLORS[(sid - 1) % len(_COLORS)],
            }
        )
    return out


def _adv(lab_config: Dict[str, Any]) -> Dict[str, Any]:
    return (lab_config.get("request") or {}).get("advanced_config") or {}


def _knowledge_base_database_type(db: Session, kb_id: int) -> str:
    # A failed DB transaction cannot safely continue into the next model query.
    return get_knowledge_base_database_type_service(db, kb_id)


def _bindings(lab_config: Dict[str, Any]) -> Dict[str, Any]:
    return lab_config.get("model_bindings") or {}


def _runtime_prompt(template: str, features: Optional[Dict[str, Any]]) -> str:
    """Render configured variables without adding unconfigured instructions."""
    return replace_features_in_template(template, features or {})


def _extract_agent_sql(result: Dict[str, Any]) -> str:
    exports = result.get("exports") if isinstance(result, dict) else {}
    if isinstance(exports, dict):
        for key in ("sql", "content", "output", "result"):
            val = exports.get(key)
            if val is not None:
                return str(val).strip()
        for key, val in exports.items():
            if str(key).split(".")[-1] in ("sql", "content", "output", "result") and val is not None:
                return str(val).strip()
    val = result.get("output") if isinstance(result, dict) else None
    return str(val).strip() if val is not None else ""


async def _call_llm(
    db: Session, lab_config: Dict[str, Any], binding_key: str, message: str, extra: Dict[str, Any]
) -> str:
    b = _bindings(lab_config).get(binding_key) or {}
    pid, model = b.get("provider_id"), b.get("model_name")
    if not pid or not model:
        raise ValueError(f"缺少 model_bindings.{binding_key}")
    cfg = _adv(lab_config).get(f"{binding_key}_config") or {}
    req = ChatRequest(
        provider_id=int(pid),
        model=str(model),
        message=message,
        temperature=float(extra.get("temperature", 0.2)),
        max_tokens=int(extra.get("max_tokens", 4096)),
        top_p=float(extra.get("top_p", 0.9)),
        timeout_seconds=float(extra.get("timeout_seconds") or extra.get("timeout")
                              or cfg.get("timeout_seconds") or cfg.get("timeout") or 600),
    )
    from ...core.model_observation import model_scope
    with model_scope(stage=binding_key):
        res = await ChatService.send_chat(db, req)
    return (res.content or "") if res else ""


def _init_steps_state(meta_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows = []
    for m in meta_list:
        rows.append(
            {
                "step_uuid": str(uuid.uuid4()),
                "step_id": m["stepId"],
                "title": m["title"],
                "api_key": m["apiKey"],
                "color": m["color"],
                "status": "pending",
                "request": None,
                "response": None,
                "error": None,
                "duration_ms": None,
            }
        )
    return rows


async def _persist_trace(
    trace_id: str,
    project_id: int,
    project_name: Optional[str],
    user_message: str,
    kb_id: Optional[int],
    created_at: int,
    steps_state: List[Dict[str, Any]],
) -> None:
    payload = {
        "trace_id": trace_id,
        "project_id": str(project_id),
        "project_name": project_name,
        "user_message": user_message,
        "knowledge_base_id": kb_id,
        "created_at": created_at,
        "updated_at": int(time.time() * 1000),
        "steps": steps_state,
    }
    await write_trace(trace_set, trace_id, payload)


async def _dispatch_step(
    db: Session,
    step_id: int,
    user_message: str,
    lab_config: Dict[str, Any],
    kb_id: int,
    acc: Dict[str, Any],
    by_step: Dict[int, Dict[str, Any]],
    features: Optional[Dict[str, Any]] = None,
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    adv = _adv(lab_config)

    if step_id in (2, 5, 10):
        return {}, {}

    if step_id == 12:
        mc = adv.get("value_multi_column_embedding_config") or {"top_k": 10, "threshold": 0.6}
        if not bool(mc.get("enable")):
            return {}, {"skipped": True, "reason": "多列同值未开启"}
        q = acc.get("rewritten_query") or user_message
        tokens = collect_field_codes_for_multi_column(by_step)
        if not tokens:
            return {
                "query": q,
                "table_name": [],
            }, {"skipped": True, "reason": "第 6/7 步未提炼到 field_code，无法多路召回"}
        top_k = int(mc.get("top_k") or 10)
        th = mc.get("threshold")
        req = MultiGlobalValueMetaRetrieverRequest(
            query=q,
            table_name=tokens,
            top_k=top_k,
            score_threshold=th,
            keyword_score_threshold=mc.get("keyword_score_threshold"),
        )
        res = await AutoBIAtomicService.multi_global_value_meta_retrieve(db, kb_id, req)
        return req.model_dump(), to_json_safe(res)

    if step_id == 13:
        ner = adv.get("ner_retrieval_config") or {}
        if not bool(ner.get("enable")):
            return {}, {"skipped": True, "reason": "NER 召回未开启"}
        if not ner.get("prompt"):
            raise ValueError("缺少 ner_retrieval_config.prompt")
        rw = acc.get("rewritten_query") or user_message
        entity_types = (ner.get("entity_types") or ner.get("filed") or "").strip()
        if not entity_types:
            entity_types = (
                "业务相关实体（如产品名、地区、时间口径、品牌名等），"
                "凡在文中出现且可能影响 SQL 条件的词。"
            )
        prompt = replace_template_vars(
            _runtime_prompt(ner["prompt"], features),
            {"query": rw, "filed": entity_types},
        )
        llm_text = await _call_llm(
            db,
            lab_config,
            "ner_retrieval",
            prompt,
            {
                "temperature": float(ner.get("temperature", 0.3)),
                "max_tokens": int(ner.get("max_tokens", 2048)),
                "top_p": float(ner.get("top_p", 0.9)),
            },
        )
        entities = parse_ner_entities_from_llm(llm_text)
        alias_top = int(ner.get("ner_alias_top_k") or 30)
        if not entities:
            ner_res = NerRetrieverResponse(
                results=[],
                total=0,
                narrative="NER 模型未抽取到实体，已跳过别名库检索。",
            )
            atomic_req_dump = None
        else:
            nreq = NerRetrieverRequest(query=rw, entity=entities, top_k=alias_top)
            ner_res = await AutoBIAtomicService.ner_retrieve(db, kb_id, nreq)
            atomic_req_dump = nreq.model_dump()
        return {
            "llm_prompt_preview": prompt[:2000],
            "full_prompt": prompt,
            "ner_atomic_request": atomic_req_dump,
        }, {
            "llm_raw": llm_text,
            "entities": entities,
            "ner_atomic": to_json_safe(ner_res),
            "narrative": ner_res.narrative,
        }

    if step_id == 1:
        cfg = adv.get("value_embedding_config") or {"top_k": 10, "threshold": 0.6}
        req = ESValueRetrieverRequest(
            query=user_message,
            top_k=cfg.get("top_k", 10),
            score_threshold=cfg.get("threshold"),
        )
        res = await AutoBIAtomicService.es_value_retrieve(db, kb_id, req)
        return req.model_dump(), to_json_safe(res)

    if step_id == 3:
        cfg = adv.get("knowledge_es_config") or {"top_k": 3, "threshold": 0.3}
        if cfg.get("enable") is False:
            return {}, {"skipped": True, "reason": "关键词召回未开启", "results": []}
        req = ESKnowledgeRetrieverRequest(
            query=user_message,
            top_k=cfg.get("top_k", 3),
            score_threshold=cfg.get("threshold"),
        )
        res = await AutoBIAtomicService.es_knowledge_retrieve(db, kb_id, req)
        return req.model_dump(), to_json_safe(res)

    if step_id == 4:
        cfg = adv.get("knowledge_rewrite_config") or {}
        results = (by_step.get(3) or {}).get("response", {}).get("results") or []
        acc["knowledge_map"] = build_knowledge_knowledge_map_object(results)
        if cfg.get("enable") is False:
            acc["rewritten_query"] = user_message
            return {}, {"skipped": True, "reason": "知识改写未开启", "rewritten_query": user_message}
        if not cfg.get("prompt"):
            raise ValueError("缺少 knowledge_rewrite_config.prompt")
        knowledge_words = build_knowledge_words_for_prompt(results)
        prompt = replace_template_vars(
            _runtime_prompt(cfg["prompt"], features),
            {"rewrite_query": user_message, "knowledge_words": knowledge_words or "（无知识词召回）"},
        )
        text = await _call_llm(
            db,
            lab_config,
            "knowledge_rewrite",
            prompt,
            {
                "temperature": cfg.get("temperature", 0.2),
                "max_tokens": cfg.get("max_tokens", 4096),
                "top_p": cfg.get("top_p", 0.9),
            },
        )
        acc["rewritten_query"] = normalize_rewritten_query(text, user_message)
        return {"prompt_preview": prompt[:2000], "full_prompt": prompt}, {
            "content": text,
            "rewritten_query": acc["rewritten_query"],
        }

    if step_id == 17 and (adv.get("bi_summary_config") or {}).get("enable") is False:
        return {}, {"skipped": True, "reason": "总结摘要未开启"}

    if step_id in (6, 7, 8):
        q = acc.get("rewritten_query") or user_message
        meta_cfg = adv.get("meta_embedding_config") or {"top_k": 15, "threshold": 0.3}
        icl_cfg = adv.get("icl_embedding_config") or {"top_k": 3, "threshold": 0}

        if step_id == 6:
            req = TableMetaRetrieverRequest(
                query=q, top_k=meta_cfg.get("top_k", 5), score_threshold=meta_cfg.get("threshold")
            )
            res = await AutoBIAtomicService.table_meta_retrieve(db, kb_id, req)
            return req.model_dump(), to_json_safe(res)
        if step_id == 7:
            value_cfg = adv.get("value_embedding_config") or {"top_k": 10, "threshold": 0.6}
            req = GlobalValueMetaRetrieverRequest(
                query=q, top_k=value_cfg.get("top_k", 10), score_threshold=value_cfg.get("threshold")
            )
            res = await AutoBIAtomicService.global_value_meta_retrieve(db, kb_id, req)
            return req.model_dump(), to_json_safe(res)
        req = SQLTemplateRetrieverRequest(
            query=q, top_k=icl_cfg.get("top_k", 3), score_threshold=icl_cfg.get("threshold", 0)
        )
        res = await AutoBIAtomicService.sql_template_retrieve(db, kb_id, req)
        return req.model_dump(), to_json_safe(res)

    if step_id == 9:
        cfg = adv.get("value_embedding_config") or {"top_k": 10, "threshold": 0.6}
        rw = acc.get("rewritten_query") or user_message
        q_long = build_long_es_query_with_annotations(user_message, acc.get("knowledge_map") or {})
        req_a = ESValueRetrieverRequest(
            query=q_long, top_k=cfg.get("top_k", 10), score_threshold=cfg.get("threshold")
        )
        req_b = ESValueRetrieverRequest(
            query=rw, top_k=cfg.get("top_k", 10), score_threshold=cfg.get("threshold")
        )
        res_a, res_b = await asyncio.gather(
            AutoBIAtomicService.es_value_retrieve(db, kb_id, req_a),
            AutoBIAtomicService.es_value_retrieve(db, kb_id, req_b),
        )
        ja, jb = to_json_safe(res_a), to_json_safe(res_b)
        merged_results = []
        seen = set()
        for r in (ja.get("results") or []) + (jb.get("results") or []):
            fc = (r.get("metadata") or {}).get("field_code") or ""
            key = (fc, (r.get("content") or "").strip())
            if key in seen:
                continue
            seen.add(key)
            merged_results.append(r)
        merged = {
            "results": merged_results,
            "total": len(merged_results),
            "dual": {"query_a": q_long, "query_b": rw},
        }
        return {"calls": [req_a.model_dump(), req_b.model_dump()], "merge_strategy": "dedup_by_field_code_and_value"}, merged

    if step_id == 11:
        mc = adv.get("value_multi_column_embedding_config") or {}
        if bool(mc.get("enable")):
            return {}, {"skipped": True, "reason": "已开启多列同值，跳过表值召回（第 11 步）"}
        q = acc.get("rewritten_query") or user_message
        val_cfg = adv.get("value_embedding_config") or {"top_k": 10, "threshold": 0.6}
        top_k = val_cfg.get("top_k", 10)
        th = val_cfg.get("threshold")
        tables = collect_field_tables_from_meta_steps(by_step)
        if not tables:
            req = TableValueRetrieverRequest(query=q, top_k=top_k, score_threshold=th)
            res = await AutoBIAtomicService.table_value_retrieve(db, kb_id, req)
            return req.model_dump(), to_json_safe(res)

        async def _tv(tbl: str) -> Tuple[TableValueRetrieverRequest, Any]:
            req = TableValueRetrieverRequest(
                query=q, table_name=tbl, top_k=top_k, score_threshold=th
            )
            res = await AutoBIAtomicService.table_value_retrieve(db, kb_id, req)
            return req, res

        pairs: List[Tuple[TableValueRetrieverRequest, Any]] = await asyncio.gather(
            *[_tv(t) for t in tables]
        )
        merged_results: List[Any] = []
        seen = set()
        for _req, res in pairs:
            for r in res.results:
                fc = (r.metadata or {}).get("field_code") or ""
                key = (fc, (r.content or "").strip())
                if key in seen:
                    continue
                seen.add(key)
                merged_results.append(r)
        merged = {
            "results": merged_results,
            "total": len(merged_results),
            "parallel_tables": tables,
        }
        return {
            "calls": [p[0].model_dump() for p in pairs],
            "merge_strategy": "per_table_parallel",
        }, to_json_safe(merged)

    if step_id == 14:
        cfg = adv.get("nl2sql_config") or {}
        if not cfg.get("prompt"):
            raise ValueError("缺少 nl2sql_config.prompt")
        table_field = build_table_field_prompt_data(by_step)
        icl_example = build_icl_example_prompt_data(by_step)
        q = acc.get("rewritten_query") or user_message
        kw_nl = build_knowledge_words_for_prompt(
            (by_step.get(3) or {}).get("response", {}).get("results") or []
        )
        s13 = (by_step.get(13) or {}).get("response") or {}
        ner_nl = ""
        if s13 and not s13.get("skipped"):
            ner_nl = (s13.get("narrative") or "").strip()
        if not ner_nl:
            ner_nl = "（无 NER 映射信息）"
        database_type = _knowledge_base_database_type(db, kb_id)
        prompt = replace_template_vars(
            _runtime_prompt(cfg["prompt"], features),
            {
                "database_type": database_type,
                "table_field_prompt_data": table_field,
                "table_join_relation_prompt_data": "",
                "default_field_prompt_data": "",
                "icl_example_prompt_data": icl_example,
                "knowledge_prompt_data": kw_nl or "（无知识词扩展说明）",
                "query": q,
                "ner_info": ner_nl,
            },
        )
        text = await _call_llm(
            db,
            lab_config,
            "nl2sql",
            prompt,
            {
                "temperature": cfg.get("temperature", 0.2),
                "max_tokens": cfg.get("max_tokens", 4096),
                "top_p": cfg.get("top_p", 0.9),
            },
        )
        acc["generated_sql"] = extract_sql_from_model_text(text)
        return {"prompt_preview": prompt[:3000], "full_prompt": prompt, "database_type": database_type}, {
            "content": text,
            "sql": acc["generated_sql"],
            "database_type": database_type,
        }

    if step_id == 15:
        cfg = adv.get("sql_permission_rewrite_config") or {}
        original_sql = (acc.get("generated_sql") or "").strip()
        base_resp = {
            "original_sql": original_sql,
            "rewritten_sql": original_sql,
            "sql": original_sql,
        }
        if not bool(cfg.get("enable")):
            return {"sql": original_sql}, {
                **base_resp,
                "skipped": True,
                "reason": "SQL 权限改写未开启",
            }
        if not original_sql or original_sql.lower() == "none":
            return {"sql": original_sql}, {
                **base_resp,
                "skipped": True,
                "reason": "nl2sql 未生成可改写 SQL（空或 None）",
            }
        target_app = cfg.get("target_app_id")
        target_version = cfg.get("target_version_id")
        if target_app is None or target_version is None:
            raise ValueError("SQL 权限改写已开启，但未选择智能体 ID 或版本")
        target_app = int(target_app)
        target_version = int(target_version)
        from app.services.agent_app.workflow_engine import run_nested_agent_workflow

        permission_features = dict(features or {})
        nested = await run_nested_agent_workflow(
            db,
            agent_app_id=target_app,
            version_id=target_version,
            inputs={
                "input": original_sql,
                "query": original_sql,
                "user_id": permission_features.get("user_id"),
                "features": permission_features,
            },
            call_stack=[(target_app, target_version)],
        )
        rewritten_sql = _extract_agent_sql(nested)
        if not rewritten_sql:
            raise ValueError("SQL 权限改写智能体未返回 SQL")
        acc["generated_sql"] = extract_sql_from_model_text(rewritten_sql) or rewritten_sql
        return {
            "target_app_id": target_app,
            "target_version_id": target_version,
            "input": original_sql,
            "features": permission_features,
        }, {
            **base_resp,
            "rewritten_sql": acc["generated_sql"],
            "sql": acc["generated_sql"],
            "agent_output": nested.get("output"),
            "agent_exports": nested.get("exports"),
        }

    if step_id == 16:
        sql = (acc.get("generated_sql") or "").strip()
        if not sql or sql.lower() == "none":
            resp = {
                "skipped": True,
                "reason": "nl2sql 未生成可执行 SQL（空或 None）",
                "columns": [],
                "rows": [],
                "row_count": 0,
            }
            return {"sql": sql or ""}, resp
        try:
            # A slow synchronous driver must not block SSE heartbeats or stop requests.
            # The worker owns its session so cancellation never closes a session it is using.
            from app.services.knowledge.sql_runtime import execute_knowledge_sql_async
            res = await execute_knowledge_sql_async(db, kb_id, sql, execute=execute_knowledge_base_sql_service)
            return {"sql": sql}, to_json_safe(res)
        except HTTPException as e:
            resp = {
                "skipped": True,
                "error": str(e.detail),
                "reason": str(e.detail),
                "columns": [],
                "rows": [],
                "row_count": 0,
            }
            return {"sql": sql}, resp

    if step_id == 18:
        cfg = adv.get("chart_drawing_config") or {}
        if cfg.get("enable") is False:
            acc["chart_spec"] = None
            return {"skipped": True, "reason": "chart_drawing_config.enable=false"}, {"chart_spec": None}
        if not cfg.get("prompt"):
            acc["chart_spec"] = None
            return {"skipped": True, "reason": "缺少 chart_drawing_config.prompt"}, {"chart_spec": None}
        sql_res = (by_step.get(16) or {}).get("response")
        if not sql_res or sql_res.get("skipped") or not (sql_res.get("rows") or []):
            acc["chart_spec"] = None
            return {"skipped": True, "reason": "无 SQL 结果或已跳过执行"}, {"chart_spec": None}
        max_rows = int(cfg.get("max_preview_rows") or 80)
        cols = sql_res.get("columns") or []
        field_mapping = "; ".join(f"{c}:{c}" for c in cols)
        rows = sql_res.get("rows") or []
        total_rows = sql_res.get("row_count", len(rows))
        # A single aggregate has no dimension for an axis. The result table and
        # summary already display it; asking a model for axes can invent fields.
        if len(cols) == 1 and len(rows) == 1 and total_rows == 1:
            chart_spec = {"type": "D", "xaxis": [], "yaxis": [], "title": user_message}
            acc["chart_spec"] = chart_spec
            return {"columns": cols, "row_count": 1}, {
                "chart_spec": chart_spec, "reason": "单值结果使用表格展示",
            }
        preview = {
            "columns": cols,
            "rows": rows[:max_rows],
            "row_count": total_rows,
            "preview_note": (
                f"（以下为前 {max_rows} 行样本，总行数 {total_rows}）" if len(rows) > max_rows else ""
            ),
        }
        sql_result_json = json.dumps(preview, ensure_ascii=False, indent=2)
        prompt = replace_template_vars(
            _runtime_prompt(cfg["prompt"], features),
            {
                "original_query": user_message,
                "rewrite_query": acc.get("rewritten_query") or user_message,
                "execute_sql": acc.get("generated_sql") or "无",
                "field_mapping": field_mapping,
                "sql_result_json": sql_result_json,
            },
        )
        # Older projects used a Jinja loop instead of {{field_mapping}}. Render
        # that specific legacy placeholder without evaluating arbitrary templates.
        prompt = re.sub(
            r"\{%\s*for\s+key\s*,\s*value\s+in\s+rich_sql_data\.column_names\.items\(\)\s*%\}.*?\{%\s*endfor\s*%\}",
            lambda _: field_mapping, prompt, flags=re.S,
        )
        prompt = re.sub(r"\{%\s*if\s+execute_sql\s+is\s+not\s+none\s*%\}.*?\{%\s*endif\s*%\}",
                        lambda _: acc.get("generated_sql") or "无", prompt, flags=re.S)
        prompt = strip_lab_template_noise(prompt)
        prompt += ("\n\n实际查询结果列名：" + json.dumps(cols, ensure_ascii=False)
                   + '\n仅输出一个 JSON 对象，包含 type、xaxis、yaxis、title。'
                   + 'xaxis/yaxis 只能使用以上查询结果列名（聚合列使用输出别名），不要输出推理过程或其他代码块。')
        try:
            text = await _call_llm(
                db,
                lab_config,
                "chart_drawing",
                prompt,
                {
                    "temperature": cfg.get("temperature", 0.2),
                    "max_tokens": cfg.get("max_tokens", 4096),
                    "top_p": cfg.get("top_p", 0.9),
                },
            )
            chart_spec = parse_chart_spec_from_llm(text)
            if chart_spec is None or chart_spec.get("error"):
                raise ValueError("图表模型未返回有效图表配置")
            if chart_spec["type"] != "D" and (
                not chart_spec["xaxis"] or not chart_spec["yaxis"]
                or any(key not in cols for key in chart_spec["xaxis"] + chart_spec["yaxis"])
            ):
                raise ValueError("图表字段与实际查询结果不匹配")
            acc["chart_spec"] = chart_spec
            return {"prompt_preview": prompt[:2500], "full_prompt": prompt}, {
                "chart_spec": chart_spec,
                "raw_text_preview": text[:4000],
            }
        except Exception as e:
            acc["chart_spec"] = None
            return {"prompt_preview": prompt[:2500], "full_prompt": prompt}, {"chart_spec": None, "error": str(e)}

    raise ValueError(f"未实现的步骤 {step_id}")


def _sse(obj: Dict[str, Any]) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


async def _typewriter_pieces(
    text: str,
    *,
    tick_seconds: float = 0.05,
    min_step: int = 10,
    max_ticks: int = 100,
) -> AsyncGenerator[str, None]:
    """总结打字机切片。

    模型网关按大块(数百字)批量下发总结文本，直接透传会导致前端"攒一大段
    突然全部出现"。这里把大块按固定节奏切片输出，伪造逐字流式效果：
    - 每 50ms 出一片，每片最少 10 字；
    - 步长自适应 ceil(len/100)，任意大块最多约 5 秒(100 片)放完；
    - 小文本一次出完，不引入额外延迟(网关将来真逐 token 下发时无感)。
    """
    if not text:
        return
    step = max(min_step, -(-len(text) // max_ticks))
    for i in range(0, len(text), step):
        if i:
            await asyncio.sleep(tick_seconds)
        yield text[i : i + step]


async def run_autobi_lab_gateway_sse(
    db: Session,
    *,
    user_message: str,
    lab_config: Dict[str, Any],
    kb_id: int,
    project_id: int,
    project_name: Optional[str],
    trace_id: str,
    trace_started_at: int,
    bailian_compat: bool = False,
    features: Optional[Dict[str, Any]] = None,
    emit_step_events: bool = False,
) -> AsyncGenerator[str, None]:
    yield _sse({"type": "trace_id", "trace_id": trace_id})
    adv = _adv(lab_config)
    features = features or {}
    try:
        stage = output_stage(adv, features)
    except ValueError as error:
        yield _sse({"type": "error", "message": str(error)})
        yield _sse({"type": "done"})
        return
    if features.get("capability_check") is True:
        binding = _bindings(lab_config).get("nl2sql") or {}
        configured = bool(kb_id and (stage == "recall" or
                          stage == "sql" and binding.get("provider_id") and binding.get("model_name")))
        yield _sse({"type": "lab_result", "kind": "capability", "mode": stage, "configured": configured})
        yield _sse({"type": "done"})
        return
    if bailian_compat:
        # 与百炼流样例一致的首条进度（在 trace 之后）
        yield _sse({"type": "bailian_progress", "progress": "检索知识词..."})

    meta_list = _pipeline_steps_meta()
    if stage == "recall":
        meta_list = [m for m in meta_list if m["stepId"] <= 13 and m["stepId"] != 8]
    elif stage == "sql":
        meta_list = [m for m in meta_list if m["stepId"] <= 15]
    steps_state = _init_steps_state(meta_list)
    usage = []
    by_step: Dict[int, Dict[str, Any]] = {}
    acc: Dict[str, Any] = {
        "rewritten_query": "",
        "generated_sql": "",
        "knowledge_map": {},
        "chart_spec": None,
    }
    runtime_features: Dict[str, Any] = without_runtime_features(features or {})
    current_step = None
    t0 = time.perf_counter()

    try:
        for i, meta in enumerate(meta_list):
            sid = meta["stepId"]
            current_step = steps_state[i]
            t0 = time.perf_counter()
            steps_state[i]["status"] = "running"
            await _persist_trace(
                trace_id, project_id, project_name, user_message, kb_id, trace_started_at, steps_state
            )
            if emit_step_events:
                yield _sse({"type": "step_started", "step_id": sid, "title": meta["title"]})

            if bailian_compat:
                if sid == 4:
                    yield _sse({"type": "bailian_progress", "progress": "多轮改写中..."})
                    yield _sse({"type": "bailian_progress", "progress": "知识词改写中..."})
                elif sid == 6:
                    yield _sse({"type": "bailian_progress", "progress": "检索召回中..."})
                elif sid == 14:
                    yield _sse({"type": "bailian_progress", "progress": "生成SQL中..."})
                elif sid == 15:
                    yield _sse({"type": "bailian_progress", "progress": "SQL权限改写中..."})
                elif sid == 16:
                    yield _sse({"type": "bailian_progress", "progress": "查询数据中..."})

            if sid == 17 and (_adv(lab_config).get("bi_summary_config") or {}).get("enable") is not False:
                if bailian_compat:
                    yield _sse({"type": "bailian_progress", "progress": "归纳总结中..."})
                cfg = _adv(lab_config).get("bi_summary_config") or {}
                if not cfg.get("prompt"):
                    raise ValueError("缺少 bi_summary_config.prompt")
                sql = acc.get("generated_sql") or "无"
                sql_data_text = format_sql_execute_result_for_summary(
                    (by_step.get(16) or {}).get("response")
                )
                message = build_bi_summary_user_message(
                    _runtime_prompt(cfg["prompt"], runtime_features),
                    original_query=user_message,
                    execute_sql=sql,
                    sql_data_text=sql_data_text,
                )
                b = _bindings(lab_config).get("bi_summary") or {}
                if not b.get("provider_id") or not b.get("model_name"):
                    raise ValueError("缺少 model_bindings.bi_summary")
                req = ChatRequest(
                    provider_id=int(b["provider_id"]),
                    model=str(b["model_name"]),
                    message=message,
                    temperature=float(cfg.get("temperature", 0.2)),
                    max_tokens=int(cfg.get("max_tokens", 4096)),
                    top_p=float(cfg.get("top_p", 0.9)),
                    timeout_seconds=float(cfg.get("timeout_seconds") or cfg.get("timeout") or 600),
                )
                full = ""
                async for delta in ChatService.stream_chat_text_deltas(db, req):
                    full += delta
                    # 网关大块下发总结文本，切片打字机输出，保证前端逐字流式呈现
                    async for piece in _typewriter_pieces(delta):
                        yield _sse({"type": "summary", "delta": piece})
                duration_ms = int((time.perf_counter() - t0) * 1000)
                request_obj = {"message_preview": message[:2500], "full_message": message}
                response_obj = {"content": full}
                by_step[17] = {"request": request_obj, "response": response_obj}
                runtime_features.update(
                    build_step_feature_values(
                        step_id=sid,
                        api_key=meta["apiKey"],
                        title=meta["title"],
                        response=response_obj,
                    )
                )
                steps_state[i].update(
                    {
                        "status": "done",
                        "request": request_obj,
                        "response": response_obj,
                        "error": None,
                        "duration_ms": duration_ms,
                    }
                )
                await _persist_trace(
                    trace_id, project_id, project_name, user_message, kb_id, trace_started_at, steps_state
                )
                if emit_step_events:
                    yield _sse({"type": "step_finished", "step_id": sid, "status": "succeeded"})
                continue

            with collect_model_usage(usage if stage else None):
                request_obj, response_obj = await _dispatch_step(
                    db, sid, user_message, lab_config, kb_id, acc, by_step, features=runtime_features
                )
            if stage == "sql" and sid == 15:
                output = sql_output(acc.get("generated_sql"), features.get("data_scope"),
                                    adv.get("data_scope_policy"),
                                    (by_step[14]["response"] or {}).get("database_type"))
                acc["generated_sql"] = output.get("sql", "")
                response_obj = {**(response_obj or {}), "sql": acc["generated_sql"]}
            duration_ms = int((time.perf_counter() - t0) * 1000)
            by_step[sid] = {"request": request_obj, "response": response_obj}
            runtime_features.update(
                build_step_feature_values(
                    step_id=sid,
                    api_key=meta["apiKey"],
                    title=meta["title"],
                    response=response_obj,
                )
            )
            if sid == 12:
                # 第 11 / 12 步互斥；包括第 12 步跳过时，所有值召回均已完成。
                multi_enabled = bool((_adv(lab_config).get("value_multi_column_embedding_config") or {}).get("enable"))
                tables = list(collect_qs_recall_values(by_step, multi_column_enabled=multi_enabled))
                descriptions = await read_database(db, list_kb_recall_field_descriptions, kb_id, tables) if tables else []
                runtime_features["qs_recall"] = build_qs_recall(
                    by_step, descriptions, multi_column_enabled=multi_enabled,
                )
                if isinstance(runtime_features.get("features"), dict):
                    runtime_features["features"].update({
                        key: runtime_features[key] for key in ("qs_recall",)
                    })
            steps_state[i].update(
                {
                    "status": "done",
                    "request": to_json_safe(request_obj),
                    "response": to_json_safe(response_obj),
                    "error": None,
                    "duration_ms": duration_ms,
                }
            )
            await _persist_trace(
                trace_id, project_id, project_name, user_message, kb_id, trace_started_at, steps_state
            )

            if emit_step_events:
                if isinstance(response_obj, dict) and response_obj.get("error"):
                    raise RuntimeError(f"{meta['title']}执行失败: {response_obj['error']}")
                yield _sse({"type": "step_finished", "step_id": sid, "status": "succeeded"})

            if bailian_compat and sid == 15:
                sql = (acc.get("generated_sql") or "").strip()
                if sql and sql.lower() != "none":
                    yield _sse({"type": "bailian_sql", "sql": sql, "query": user_message})

            if bailian_compat and sid == 16:
                if response_obj and not response_obj.get("skipped"):
                    rows = response_obj.get("rows") or []
                    if rows or emit_step_events:
                        yield _sse(
                            {
                                "type": "bailian_data",
                                "query": user_message,
                                "data": rows,
                                "columns": response_obj.get("columns", []),
                                "total_count": response_obj.get("row_count", len(rows)),
                            }
                        )

            if bailian_compat and sid == 18:
                chart_spec = (response_obj or {}).get("chart_spec")
                step16_resp = ((by_step.get(16) or {}).get("response") or {})
                rows = step16_resp.get("rows") or []
                if isinstance(chart_spec, dict) and chart_spec and rows and not step16_resp.get("skipped"):
                    yield _sse(
                        {
                            "type": "bailian_chart",
                            "chart_spec": chart_spec,
                            "sql_data": {
                                "columns": step16_resp.get("columns") or [],
                                "rows": rows,
                                "row_count": step16_resp.get("row_count"),
                                "skipped": step16_resp.get("skipped"),
                            },
                        }
                    )

        if stage == "recall":
            yield _sse({"type": "lab_result", "kind": "recall", "items": recall_items(by_step), "usage": usage})
        elif stage == "sql":
            yield _sse({"type": "lab_result", **output, "usage": usage})
        yield _sse({"type": "done"})
    except (Exception, asyncio.CancelledError, GeneratorExit) as e:
        cancelled = isinstance(e, (asyncio.CancelledError, GeneratorExit))
        if current_step is not None and (not cancelled or current_step["status"] == "running"):
            current_step.update({
                "status": "error",
                "error": str(e) or ("执行已取消或中断" if cancelled else type(e).__name__),
                "duration_ms": int((time.perf_counter() - t0) * 1000),
            })
            try:
                await _persist_trace(
                    trace_id, project_id, project_name, user_message, kb_id, trace_started_at, steps_state
                )
            except Exception:
                logger.exception("保存失败步骤追踪日志失败 trace_id=%s", trace_id)
        if cancelled:
            raise
        logger.exception("autobi lab gateway 流水线失败 trace_id=%s", trace_id)
        yield _sse({"type": "error", "message": str(e), **({"usage": usage} if stage else {})})
        yield _sse({"type": "done"})


async def collect_autobi_lab_gateway_json(
    db: Session,
    *,
    user_message: str,
    lab_config: Dict[str, Any],
    kb_id: int,
    project_id: int,
    project_name: Optional[str],
    trace_id: str,
    trace_started_at: int,
    features: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    消费 run_autobi_lab_gateway_sse 产出的 SSE 片段，拼成一次性 JSON 载荷（智能体工作流 lab 节点等使用）。
    字段：trace_id、summary（数据总结全文）、sql（权限改写后查询 SQL）、error（成功为 null）。
    """
    trace_out: Optional[str] = None
    summary_parts: List[str] = []
    sql = ""
    error_msg: Optional[str] = None
    events: List[Dict[str, Any]] = []
    buf = ""
    async for chunk in run_autobi_lab_gateway_sse(
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
        buf += chunk
        while "\n\n" in buf:
            raw, buf = buf.split("\n\n", 1)
            for line in raw.split("\n"):
                line = line.strip()
                if not line.startswith("data: "):
                    continue
                try:
                    obj = json.loads(line[6:].strip())
                except json.JSONDecodeError:
                    continue
                events.append(obj)
                t = obj.get("type")
                if t == "trace_id":
                    trace_out = obj.get("trace_id")
                elif t == "summary":
                    summary_parts.append(str(obj.get("delta") or ""))
                elif t == "lab_result" and obj.get("kind") == "sql":
                    sql = str(obj.get("sql") or "")
                elif t == "bailian_sql":
                    sql = str(obj.get("sql") or "").strip()
                elif t == "error":
                    err = obj.get("message")
                    error_msg = str(err) if err is not None else "error"
    return {
        "trace_id": trace_out,
        "summary": "".join(summary_parts),
        "sql": sql,
        "error": error_msg,
        "events": events,
    }
