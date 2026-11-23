"""Two independently callable DDI laboratory operations on the native gateway."""

import json
import logging
import re
import unicodedata

from requests import RequestException
from ...schemas.chat import ChatRequest
from ...core.execution import read_database
from ...core.resources import thread_resource
from ...models.knowledge_base import KnowledgeBase
from ..chat.service import ChatService
from ..config_resolver import resolve_embedding_config, resolve_es_config
from ..knowledge.embedding_service import EmbeddingService
from ..knowledge.es_service import ElasticsearchService
from ..vector_store.service import VectorStoreService
from .ddi_metrics import compile_sql, normalize_plan, plan_instructions, scoped_sql
from .ddi_atomic_samples import exact_sample, sample_sql


def glossary(db, kb_id, question):
    kb = db.get(KnowledgeBase, kb_id)
    if not kb:
        return []
    config = resolve_es_config(db, kb.space_id)
    if not config:
        return []
    search = thread_resource(ElasticsearchService, config)
    hits = search.search_knowledge_terms(kb_id, question, top_k=6)
    return [{"type": "knowledge_term", "text": h["data_detail"], "content": str(h["quote_extend"])[:1800]}
            for h in hits if h.get("data_detail") and h.get("quote_extend")]


def recall(db, kb_id, question):
    try:
        terms = glossary(db, kb_id, question)
    except Exception:
        logging.getLogger(__name__).warning("DDI glossary search unavailable for kb %s", kb_id)
        terms = []
    def normalized(text):
        return "".join(unicodedata.normalize("NFKC", text).casefold().split())
    text = normalized(question)
    matches = [item for item in terms if normalized(item["text"]) in text]
    if matches:
        return sorted(matches, key=lambda item: -len(item["text"])), None
    try:
        items, charge = vector_semantics(db, kb_id, question)
    except (RuntimeError, ValueError, RequestException):
        if terms:
            return terms, None
        raise
    if not items and terms:
        return terms, charge
    if not items:
        raise ValueError("知识库尚未索引，无法召回业务依据")
    return items, charge


def vector_semantics(db, kb_id, question):
    embedding = resolve_embedding_config(db, kb_id=kb_id)
    store = VectorStoreService.resolve_active_store(db, kb_id=kb_id)
    service = EmbeddingService(embedding)
    vector = service.get_embedding(question)
    if not vector:
        raise ValueError("向量模型未返回向量")
    items = []
    for kind, count in (
        ("knowledge_term", 5),
        ("table_column", 7),
        ("table_value", 6),
    ):
        hits = VectorStoreService.search_vectors_with_config(
            store,
            kb_id,
            vector,
            top_k=count,
            expr=f'field_type == "{kind}" && kb_id == {int(kb_id)}',
        )
        for hit in hits:
            items.append(
                {
                    "type": kind,
                    "table": hit.get("field_table", ""),
                    "field": hit.get("field_code", ""),
                    "text": str(hit.get("field_value", ""))[:1800],
                    "content": str(hit.get("sql_content", ""))[:1200],
                }
            )
    return items, {"model": embedding["model"], "usage": service.last_usage}


async def run_lab(db, mode, config, kb_id, question, features):
    if features.get("capability_check") is True:
        return {
            "kind": "capability",
            "mode": mode,
            "configured": bool(
                kb_id
                and (
                    mode == "recall"
                    or (config.get("model_bindings") or {})
                    .get("nl2sql", {})
                    .get("provider_id")
                )
            ),
        }
    if len(question) > 10000:
        raise ValueError("问题超过 10000 字")
    context = str(features.get("context") or "").strip()
    if mode == "sql" and (not context or context in question):
        sample = await read_database(db, exact_sample, kb_id, question)
        if sample is not None:
            return {"kind": "sql", "sql": sample_sql(sample, features.get("data_scope")), "usage": []}
    # Standalone SQL requests retrieve their own evidence. Requests from the
    # paired application may reuse the recall result from this same question.
    carried = features.get("recall") if mode == "sql" else None
    usage = []
    if not isinstance(carried, list) or not carried:
        items, charge = await read_database(db, recall, kb_id, question)
        if charge:
            usage.append(charge)
    else:
        items = [
            {
                k: str(v)[:1800]
                for k, v in x.items()
                if k in ("type", "table", "field", "text", "content")
            }
            for x in carried[:24]
            if isinstance(x, dict) and x.get("type") in {"knowledge_term", "table_column", "table_value"}
        ]
    if mode == "recall":
        return {"kind": "recall", "items": items, "usage": usage}
    binding = (config.get("model_bindings") or {}).get("nl2sql") or {}
    instructions = plan_instructions()
    rules = str(config.get("atomic_sql_rules") or "").strip()[:1000]
    if rules:
        instructions += "\n本实验室维护的原子问题解释规则（使用上述计划字段）：\n" + rules
    reference = {
        "问题": question,
        "已召回的参考资料": list(items),
        "前文": str(features.get("context") or "")[:4000],
    }
    # Keep two planning attempts within the caller's reservation and model window.
    while (
        len(json.dumps(reference, ensure_ascii=False).encode()) > 15500
        and reference["已召回的参考资料"]
    ):
        reference["已召回的参考资料"].pop()
    if len(json.dumps(reference, ensure_ascii=False).encode()) > 16500:
        raise ValueError("问题与历史过长，请缩短实验室请求")
    for attempt in range(2):
        response = await ChatService.send_chat(
            db,
            ChatRequest(
                provider_id=int(binding["provider_id"]),
                model=binding["model_name"],
                system=instructions,
                temperature=0,
                max_tokens=1200,
                timeout_seconds=90,
                message=json.dumps(reference, ensure_ascii=False),
            ),
        )
        usage.append({"model": response.model, "usage": response.usage})
        raw = re.sub(
            r"^" + chr(96) * 3 + r"(?:json)?\s*|\s*" + chr(96) * 3 + r"$",
            "",
            response.content.strip(),
            flags=re.I,
        )
        try:
            plan = json.loads(raw)
            if not isinstance(plan, dict):
                raise ValueError("模型计划必须是 JSON 对象")
            if plan.get("clarification"):
                return {
                    "kind": "clarification",
                    "message": str(plan["clarification"])[:500],
                    "usage": usage,
                }
            sql = scoped_sql(
                compile_sql(normalize_plan(plan, question)), features.get("data_scope")
            )
            return {"kind": "sql", "sql": sql, "usage": usage}
        except (ValueError, KeyError, TypeError) as err:
            if attempt:
                return {
                    "kind": "clarification",
                    "message": "请说明需要的指标、时间及分组。" + str(err)[:100],
                    "usage": usage,
                }
            reference["修正要求"] = (
                "前一次计划无效："
                + str(err)[:180]
                + "。严格使用可选 ID，日期和 Top N 用专用字段。"
            )
            reference["前一次计划"] = raw[:850]
