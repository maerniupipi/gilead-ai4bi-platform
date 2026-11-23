import json
import re
from typing import Any, Dict

from app.schemas.autobi_atomic import (
    ESValueRetrieverRequest,
    ESKnowledgeRetrieverRequest,
    SQLTemplateRetrieverRequest,
    GenerateSqlRequest,
    ExecuteSqlRequest,
    TableMetaRetrieverRequest,
    TableValueRetrieverRequest,
    GlobalValueMetaRetrieverRequest,
    MultiGlobalValueMetaRetrieverRequest,
    NerRetrieverRequest,
)
from app.services.knowledge.autobi_atomic.service import AutoBIAtomicService
from app.services.knowledge.knowledge_base.service import get_knowledge_base_database_type_service

from ..workflow_run_ctx import WorkflowRunContext, resolve_dotted
from ._values import as_text, coerce_value


_CAPABILITY_MAP = {
    "elasticsearch-value-retriever": (ESValueRetrieverRequest, AutoBIAtomicService.es_value_retrieve),
    "elasticsearch-knowledge-retriever": (ESKnowledgeRetrieverRequest, AutoBIAtomicService.es_knowledge_retrieve),
    "sql-template-retriever": (SQLTemplateRetrieverRequest, AutoBIAtomicService.sql_template_retrieve),
    "generate-sql": (GenerateSqlRequest, AutoBIAtomicService.generate_sql),
    "execute-sql": (ExecuteSqlRequest, AutoBIAtomicService.execute_sql),
    "table-meta-retriever": (TableMetaRetrieverRequest, AutoBIAtomicService.table_meta_retrieve),
    "table-value-retriever": (TableValueRetrieverRequest, AutoBIAtomicService.table_value_retrieve),
    "global-value-meta-retriever": (GlobalValueMetaRetrieverRequest, AutoBIAtomicService.global_value_meta_retrieve),
    "multi-global-value-meta-retriever": (
        MultiGlobalValueMetaRetrieverRequest,
        AutoBIAtomicService.multi_global_value_meta_retrieve,
    ),
    "ner-retriever": (NerRetrieverRequest, AutoBIAtomicService.ner_retrieve),
}

_TEMPLATE_RE = re.compile(r"\{\{\s*([^}]+?)\s*\}\}")


def _jsonable(obj: Any) -> Any:
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "dict"):
        return obj.dict()
    return obj


def _coerce_const_value(raw: Any) -> Any:
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


def _resolve_template_value(ctx: WorkflowRunContext, raw: Any) -> Any:
    if isinstance(raw, dict):
        return {k: _resolve_template_value(ctx, v) for k, v in raw.items()}
    if isinstance(raw, list):
        return [_resolve_template_value(ctx, v) for v in raw]
    if not isinstance(raw, str):
        return raw

    stripped = raw.strip()
    full = _TEMPLATE_RE.fullmatch(stripped)
    if full:
        return resolve_dotted(ctx, full.group(1).strip())

    def repl(m: re.Match) -> str:
        val = resolve_dotted(ctx, m.group(1).strip())
        return as_text(val)

    return _TEMPLATE_RE.sub(repl, raw)


def _build_request_body(ctx: WorkflowRunContext, cfg: Dict[str, Any]) -> Dict[str, Any]:
    body: Dict[str, Any] = {}
    for row in cfg.get("input_vars") or []:
        key = (row.get("key") or "").strip()
        if not key or key == "knowledge_base_id":
            continue
        mode = (row.get("source_mode") or "const").strip()
        if mode == "ref":
            ref = (row.get("source_ref") or row.get("ref") or "").strip()
            body[key] = resolve_dotted(ctx, ref) if ref else None
        else:
            raw = row.get("const_value")
            # STRING constants such as "123" and "false" must remain strings.
            value = raw if str(row.get("type") or "").lower() == "string" else _coerce_const_value(raw)
            value = _resolve_template_value(ctx, value)
            if value == "" and key in (
                "top_k", "score_threshold", "table_name", "temperature", "max_tokens", "top_p",
                "keyword_enable", "keyword_top_k", "keyword_score_threshold",
            ):
                continue  # Leave optional blank fields to the request model's defaults.
            body[key] = coerce_value(value, row.get("type"), key)
    return body


def _build_context_vars(ctx: WorkflowRunContext, cfg: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for row in cfg.get("context_vars") or []:
        name = (row.get("name") or "").strip()
        if not name:
            continue
        mode = (row.get("source_mode") or "ref").strip()
        if mode == "const":
            out[name] = _resolve_template_value(ctx, _coerce_const_value(row.get("const_value")))
        else:
            ref = (row.get("source_ref") or row.get("ref") or "").strip()
            if ref:
                out[name] = resolve_dotted(ctx, ref)
    return out


def _resolve_knowledge_base_id(ctx: WorkflowRunContext, cfg: Dict[str, Any]) -> int:
    row = next((r for r in (cfg.get("input_vars") or []) if (r.get("key") or "") == "knowledge_base_id"), None)
    if not row:
        raise ValueError("原子能力节点缺少 knowledge_base_id 输入")
    if (row.get("source_mode") or "const") == "ref":
        ref = (row.get("source_ref") or row.get("ref") or "").strip()
        value = resolve_dotted(ctx, ref) if ref else None
    else:
        value = row.get("const_value")
    try:
        if isinstance(value, bool) or isinstance(value, float) and not value.is_integer():
            raise ValueError("知识库 ID 必须是整数")
        kb_id = int(value)
    except Exception as e:
        raise ValueError("原子能力节点 knowledge_base_id 无效") from e
    if kb_id <= 0:
        raise ValueError("原子能力节点 knowledge_base_id 无效")
    return kb_id


async def execute(ctx: WorkflowRunContext, node: dict) -> dict:
    data = node.get("data") or {}
    cfg = data.get("atomic_config") or {}
    capability = (cfg.get("capability") or "").strip()
    pair = _CAPABILITY_MAP.get(capability)
    if not pair:
        raise ValueError("原子能力节点未选择有效能力")

    request_model, service_call = pair
    body = _build_request_body(ctx, cfg)
    if capability == "generate-sql":
        body["context"] = _build_context_vars(ctx, cfg)
        kb_row = next((row for row in cfg.get("input_vars") or [] if row.get("key") == "knowledge_base_id"), None)
        # A missing optional KB is supported for legacy prompt-only SQL generation;
        # a configured invalid ID or failed lookup must never be silently ignored.
        if kb_row and (kb_row.get("source_mode") == "ref" or kb_row.get("const_value") not in (None, "")):
            kb_id = _resolve_knowledge_base_id(ctx, cfg)
            if "database_type" not in body["context"]:
                body["context"]["database_type"] = get_knowledge_base_database_type_service(ctx.db, kb_id)
        body["system_prompt"] = cfg.get("system_prompt") or body.get("system_prompt") or ""
        req = request_model(**body)
        res = await service_call(ctx.db, req)
    else:
        kb_id = _resolve_knowledge_base_id(ctx, cfg)
        req = request_model(**body)
        res = await service_call(ctx.db, kb_id, req)
    out = _jsonable(res)
    if not isinstance(out, dict):
        out = {"result": out}

    output_vars = cfg.get("output_vars") or []
    if isinstance(output_vars, list) and output_vars:
        fixed = {}
        for item in output_vars:
            name = item.get("key") if isinstance(item, dict) else str(item)
            if name and name in out:
                fixed[name] = out.get(name)
        return fixed
    return out
