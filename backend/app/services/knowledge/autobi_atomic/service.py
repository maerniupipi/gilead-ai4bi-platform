"""
AutoBI 原子能力服务
"""
import asyncio
import json
import logging
from difflib import SequenceMatcher
from typing import List, Dict, Any, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload

from app.core.execution import isolated_retrieval, read_database, release_read_connection, RETRIEVAL_WORK
from app.core.resources import thread_resource
from app import models
from app.repositories.knowledge.knowledge_base.repository import get_knowledge_base_active
from app.repositories.knowledge.kb_ner_repository import (
    search_kb_ner_rows_alias_contains_entities,
)
from app.schemas.autobi_atomic import (
    ESValueRetrieverRequest,
    ESValueRetrieverResponse,
    ESKnowledgeRetrieverRequest,
    ESKnowledgeRetrieverResponse,
    SQLTemplateRetrieverRequest,
    SQLTemplateRetrieverResponse,
    TableMetaRetrieverRequest,
    TableMetaRetrieverResponse,
    TableValueRetrieverRequest,
    TableValueRetrieverResponse,
    GlobalValueMetaRetrieverRequest,
    GlobalValueMetaRetrieverResponse,
    MultiGlobalValueMetaRetrieverRequest,
    NerRetrieverRequest,
    NerRetrieverResponse,
    GenerateSqlRequest,
    GenerateSqlResponse,
    ExecuteSqlRequest,
    ExecuteSqlResponse,
    RetrieverResult,
)
from app.schemas.chat import ChatRequest
from app.services.chat.service import ChatService
from app.services.knowledge.embedding_service import EmbeddingService
from app.services.vector_store.service import VectorStoreService
from app.services.knowledge.es_service import ElasticsearchService
from app.services.knowledge.knowledge_base.service import (
    execute_knowledge_base_sql_service,
)
from app.services.config_resolver import ConfigNotFoundError, resolve_embedding_config, resolve_es_config, resolve_vector_store_config

logger = logging.getLogger(__name__)


def _resolve_vs_config(db: Session, space_id: int = None, kb_id: int = None):
    """默认配置缺失时允许文本回退；显式绑定错误必须暴露。"""
    try:
        return resolve_vector_store_config(db, space_id, kb_id=kb_id)
    except ConfigNotFoundError:
        return None

def _resolve_es_config_safe(db: Session, space_id: int = None):
    """从数据库获取 ES 配置，获取失败返回 None。"""
    try:
        return resolve_es_config(db, space_id)
    except Exception:
        return None


def _milvus_escape(s: str) -> str:
    """Milvus 表达式中双引号字符串转义。"""
    return (s or "").replace("\\", "\\\\").replace('"', '\\"')


def _normalize_es_hits(
    hits: List[Dict[str, Any]],
    top_k: int,
    threshold: Optional[float],
) -> List[Tuple[float, Dict[str, Any]]]:
    """将 ES 原始 _score 按批次最大值归一化到 0~1，过滤阈值后取前 top_k 条。"""
    if not hits:
        return []
    scores = [float(h.get("score") or 0.0) for h in hits]
    mx = max(scores) if scores else 0.0
    out: List[Tuple[float, Dict[str, Any]]] = []
    for h in hits:
        raw = float(h.get("score") or 0.0)
        norm = (raw / mx) if mx > 0 else 0.0
        if threshold is not None and threshold > 0 and norm < threshold:
            continue
        out.append((norm, {**h, "normalized_score": norm, "es_raw_score": raw}))
    return out[:top_k]


def _retriever_identity(row: RetrieverResult) -> Tuple[str, str, str]:
    metadata = row.metadata or {}
    code = str(metadata.get("field_code") or "").strip()
    table = str(metadata.get("field_table") or code.split("&&")[0]).strip()
    return table, code, row.content.strip()


def _unique_retriever_results(rows: List[RetrieverResult]) -> List[RetrieverResult]:
    unique = {}
    for row in rows:
        if row.content.strip():
            unique.setdefault(_retriever_identity(row), row)
    return list(unique.values())


def _union_multi_column_results(
    parts: List[Tuple[List[RetrieverResult], List[RetrieverResult]]],
    top_k: int,
) -> List[RetrieverResult]:
    """每列每路最多 TopK，按输入/向量/关键词顺序稳定去重，不重新排序。"""
    merged: Dict[Tuple[str, str, str], RetrieverResult] = {}
    seen = {"vector": set(), "keyword": set()}
    counts = {"vector": {}, "keyword": {}}
    for vector_rows, keyword_rows in parts:
        for source, rows in (("vector", vector_rows), ("keyword", keyword_rows)):
            for row in rows:
                key = _retriever_identity(row)
                field = key[:2]
                if not key[2] or key in seen[source] or counts[source].get(field, 0) >= top_k:
                    continue
                seen[source].add(key)
                counts[source][field] = counts[source].get(field, 0) + 1
                if key not in merged:
                    metadata = {
                        **row.metadata, "sources": [],
                        "score_type": "vector" if source == "vector" else "keyword_normalized",
                    }
                    merged[key] = RetrieverResult(score=row.score, content=key[2], metadata=metadata)
                item = merged[key]
                for name, value in row.metadata.items():
                    item.metadata.setdefault(name, value)
                item.metadata["sources"].append(source)
                item.metadata[f"{source}_score"] = row.score
    return list(merged.values())


def _parse_global_value_table_param(raw: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """
    解析「表值召回(对应字段)」的 table_name：
    表名.字段名（推荐）、表名&字段名、表名&&字段名（与 Milvus 存储一致），或仅表名。
    返回 (field_table 过滤用表名, field_code)；field_code 与 Milvus 存储一致时为 表&&字段。
    """
    if raw is None:
        return None, None
    s = str(raw).strip()
    if not s:
        return None, None
    if "&&" in s:
        return None, s
    if "&" in s:
        left, right = s.split("&", 1)
        left, right = left.strip(), right.strip()
        if left and right:
            return None, f"{left}&&{right}"
        if left:
            return left, None
        return None, None
    # 表.字段 → 内部统一为 表&&字段（与向量库 field_code 一致）
    if "." in s:
        left, right = s.split(".", 1)
        left, right = left.strip(), right.strip()
        if left and right:
            return None, f"{left}&&{right}"
    return s, None


def _field_code_matches_filter(
    field_code: Optional[str],
    resolved: Optional[str],
    table_name: Optional[str],
    field_name: Optional[str],
) -> bool:
    """在无法使用 Milvus expr 精确过滤时，对结果做后过滤。"""
    fc = (field_code or "").strip()
    resolved_str = (resolved or "").strip()
    tn = (table_name or "").strip()
    fn_raw = (field_name or "").strip()

    # 1) 最严格：如果 resolved 与存储一致，则必命中
    if resolved_str:
        if fc == resolved_str:
            return True

    # 2) 没有任何额外约束：全部放行
    if not fn_raw and not tn:
        return True

    # 3) 宽松字段匹配：
    #    - 支持 field_name 传入：`table&&field` / `field` / `table.field` / 带空格的变体
    #    - 若表名不一致，至少保证字段名后缀匹配：`&&field`
    if fn_raw:
        # field_name 直接给了完整 field_code
        if "&&" in fn_raw:
            return fc == fn_raw

        # field_name 可能是 table.field
        if "." in fn_raw:
            fn_candidate = fn_raw.split(".")[-1].strip()
        else:
            fn_candidate = fn_raw

        if fc.endswith(f"&&{fn_candidate}") or fc == fn_candidate:
            return True

        # 兜底：fc 若形如 "tn&&fn"，取最后一个段再比
        if "&&" in fc:
            fc_last = fc.split("&&")[-1].strip()
            if fc_last == fn_candidate:
                return True

    # 4) 仅表名约束（弱匹配）：只要字段编码以该表名前缀开头即可
    if tn:
        if fc.startswith(f"{tn}&&"):
            return True

    return False


def _build_table_value_expr(
    kb_id: int,
    table_name: Optional[str],
    field_code_full: Optional[str],
) -> str:
    """构造 Milvus 中 table_value 域过滤表达式。"""
    parts = [f'field_type == "table_value"', f"kb_id == {int(kb_id)}"]
    if field_code_full:
        parts.append(f'field_code == "{_milvus_escape(field_code_full)}"')
    elif table_name:
        parts.append(f'field_table == "{_milvus_escape(table_name)}"')
    return " && ".join(parts)


def _extract_sql_from_text(text: str) -> str:
    """从模型输出中提取 SQL，兼容 ```sql 代码块与纯文本。"""
    raw = (text or "").strip()
    if not raw:
        return ""
    import re

    m = re.search(r"```(?:sql)?\s*([\s\S]*?)```", raw, re.IGNORECASE)
    if m:
        raw = m.group(1).strip()
    raw = re.sub(r"^\s*SQL\s*[:：]\s*", "", raw, flags=re.IGNORECASE).strip()
    return raw.rstrip(";").strip() + (";" if raw and not raw.rstrip().endswith(";") else "")


def _format_prompt_value(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, default=str)
    if value is None:
        return ""
    return str(value)


def _render_generate_sql_prompt(request: GenerateSqlRequest) -> str:
    import re

    database_type = str((request.context or {}).get("database_type") or "SQL")
    default_prompt = (
        f"你是 Text-to-SQL 助手。请根据用户问题和上下文生成一条 {database_type} 只读 SELECT 查询。\n"
        "要求：\n"
        "1. 只输出 SQL，不要 Markdown、解释或代码围栏。\n"
        "2. 禁止 INSERT、UPDATE、DELETE、DROP、ALTER、TRUNCATE 等写操作。\n"
        "3. 表名、字段名必须来自上下文；无法确认时生成保守查询或返回 SELECT NULL AS result。\n"
        "4. 优先参考知识信息与 SQL 样例。\n\n"
        "【知识信息】\n{{knowledge}}\n\n"
        "【SQL样例】\n{{examples}}\n\n"
        "【用户问题】\n{{query}}\n\n"
        "SQL:"
    )
    template = (request.system_prompt or "").strip() or default_prompt
    context = dict(request.context or {})
    context.setdefault("query", request.query)

    def repl(m: re.Match) -> str:
        key = m.group(1).strip()
        if key not in context:
            return m.group(0)
        return _format_prompt_value(context.get(key))

    return re.sub(r"\{\{\s*([^}]+?)\s*\}\}", repl, template)


def _hits_to_table_value_results(
    hits: List[Dict[str, Any]],
    threshold: Optional[float],
    limit: int,
) -> List[RetrieverResult]:
    """将 Milvus 命中转为 RetrieverResult（COSINE 距离越大越相似）。"""
    rows: List[RetrieverResult] = []
    for h in hits:
        dist = float(h.get("distance") or 0.0)
        fv = (h.get("field_value") or "").strip()
        rows.append(
            RetrieverResult(
                score=dist,
                content=fv,
                metadata={
                    "field_table": h.get("field_table") or "",
                    "field_code": h.get("field_code") or "",
                    "field_value": fv,
                    "vec_score": round(dist, 6),
                    "source": "vector_store",
                    "field_type": h.get("field_type") or "table_value",
                },
            )
        )
    rows = _apply_score_threshold(rows, threshold)
    return rows[:limit]


def _collection_name(kb: models.KnowledgeBase) -> str:
    name = (kb.vector_collection_name or "").strip()
    if name:
        return name
    return f"v_kb{kb.id}"


def _text_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, (a or "").lower(), (b or "").lower()).ratio()


def _apply_score_threshold(
    rows: List[RetrieverResult],
    threshold: Optional[float],
) -> List[RetrieverResult]:
    """COSINE 距离在 Milvus 中越大越相似；低于 threshold 的丢弃。"""
    if threshold is None or threshold <= 0:
        return rows
    return [r for r in rows if r.score >= threshold]


def _sql_samples_from_db(
    db: Session,
    knowledge_base_id: int,
    query: str,
    top_k: int,
    threshold: Optional[float],
) -> Tuple[List[RetrieverResult], int]:
    """从 kb_sample_library 表做文本相似度召回（无向量时的回退）。"""
    rows = (
        db.query(models.KbSampleLibrary)
        .filter(models.KbSampleLibrary.knowledge_base_id == knowledge_base_id)
        .all()
    )
    scored: List[Tuple[float, models.KbSampleLibrary]] = []
    for r in rows:
        sim = _text_similarity(query, r.sample_name)
        scored.append((sim, r))
    scored.sort(key=lambda x: x[0], reverse=True)
    out: List[RetrieverResult] = []
    for sim, r in scored[:top_k]:
        if threshold is not None and threshold > 0 and sim < threshold:
            continue
        meta = {
            "query": r.sample_name,
            "answer": r.sample_content,
            "vec_score": round(sim, 6),
            "source": "kb_sample_library",
        }
        out.append(
            RetrieverResult(
                score=sim,
                content=r.sample_name,
                metadata=meta,
            )
        )
    return out, len(rows)


def _table_fields_from_db(
    db: Session,
    knowledge_base_id: int,
    query: str,
    top_k: int,
    threshold: Optional[float],
) -> Tuple[List[RetrieverResult], int]:
    """从 kb_table_field + kb_table_structure 做文本相似度召回（无向量时的回退）。"""
    rows = (
        db.query(models.KbTableField)
        .options(joinedload(models.KbTableField.kb_table_structure))
        .join(
            models.KbTableStructure,
            models.KbTableField.kb_table_structure_id == models.KbTableStructure.id,
        )
        .filter(
            models.KbTableStructure.knowledge_base_id == knowledge_base_id,
            models.KbTableField.is_enabled == True,  # noqa: E712
        )
        .all()
    )
    scored: List[Tuple[float, models.KbTableField, str, str, str]] = []
    for f in rows:
        ts = f.kb_table_structure
        table_name = ts.table_name if ts else ""
        table_alias = (ts.table_alias or table_name) if ts else ""
        field_display = f.field_alias or f.field_name
        page_line = f"{table_alias}&&{field_display}"
        sim = _text_similarity(query, page_line)
        field_code = f"{table_name}&&{f.field_name}" if table_name else f.field_name
        scored.append((sim, f, table_name, field_code, page_line))
    scored.sort(key=lambda x: x[0], reverse=True)
    eff_threshold = 0.3 if threshold is None else threshold
    out: List[RetrieverResult] = []
    for sim, _f, table_name, field_code, page_line in scored:
        if eff_threshold > 0 and sim < eff_threshold:
            continue
        out.append(
            RetrieverResult(
                score=sim,
                content=page_line,
                metadata={
                    "field_table": table_name,
                    "field_code": field_code,
                    "field_value": page_line,
                    "vec_score": round(sim, 6),
                    "source": "kb_table_field",
                },
            )
        )
        if len(out) >= top_k:
            break
    return out, len(rows)


class AutoBIAtomicService:
    """AutoBI原子能力服务"""
    
    @staticmethod
    @isolated_retrieval
    def es_value_retrieve(db: Session, knowledge_base_id: int, request: ESValueRetrieverRequest) -> ESValueRetrieverResponse:
        """
        ES表值召回
        索引 `es_kb{knowledge_base_id}_table_value`（见 vectorization.md 步骤3）。
        对 field_value 做 match 检索，分数按本批最大 _score 归一化到 0~1。
        """
        kb = get_knowledge_base_active(db, knowledge_base_id)
        if not kb:
            raise HTTPException(status_code=404, detail="知识库不存在或已删除")

        top_k = request.top_k or 5
        q = (request.query or "").strip()
        logger.info(
            "ES value retrieve: query=%s, kb_id=%s, top_k=%s",
            q[:200],
            knowledge_base_id,
            top_k,
        )

        index_name = f"es_kb{knowledge_base_id}_table_value"
        results: List[RetrieverResult] = []

        # 获取 ES 配置
        es_config = _resolve_es_config_safe(db, getattr(kb, 'space_id', None))
        if not es_config:
            logger.warning("ES 未配置，ES 表值召回返回空")
            return ESValueRetrieverResponse(results=[], total=0)
        release_read_connection(db)
        es_svc = thread_resource(ElasticsearchService, es_config)

        try:
            fetch_size = max(top_k, 1) * 2
            raw = es_svc.search_table_values(
                knowledge_base_id, q, top_k=fetch_size
            )
        except Exception as e:
            logger.exception("ES 表值搜索失败: %s", e)
            return ESValueRetrieverResponse(results=[], total=0)

        logger.info(
            "ES value retrieve pipeline: index=%s query=%r fetch_size=%s "
            "raw_rows=%s threshold=%s top_k=%s",
            index_name,
            q,
            fetch_size,
            len(raw),
            request.score_threshold,
            top_k,
        )

        normed = _normalize_es_hits(raw, top_k=top_k, threshold=request.score_threshold)
        logger.info(
            "ES value retrieve after normalize/threshold: kept=%s (threshold 过滤后条数)",
            len(normed),
        )
        for norm, row in normed:
            fv = (row.get("field_value") or "").strip()
            results.append(
                RetrieverResult(
                    score=norm,
                    content=fv,
                    metadata={
                        "field_table": row.get("field_table"),
                        "field_code": row.get("field_code"),
                        "field_value": fv,
                        "es_score": round(norm, 6),
                        "es_raw_score": row.get("es_raw_score"),
                        "normalized_score": round(norm, 6),
                        "index": index_name,
                        "source": "elasticsearch",
                    },
                )
            )

        return ESValueRetrieverResponse(results=results, total=len(results))

    @staticmethod
    async def generate_sql(
        db: Session,
        request: GenerateSqlRequest,
    ) -> GenerateSqlResponse:
        """基于提示词模板、上下文变量和用户问题生成只读 SQL。"""
        database_type = str((request.context or {}).get("database_type") or "SQL")
        prompt = _render_generate_sql_prompt(request)
        resp = await ChatService.send_chat(
            db,
            ChatRequest(
                provider_id=int(request.provider_id),
                model=(request.model_name or "").strip(),
                message=prompt,
                system=f"你只输出可执行 {database_type} SELECT SQL。",
                temperature=request.temperature if request.temperature is not None else 0.2,
                max_tokens=request.max_tokens or 2048,
                top_p=request.top_p if request.top_p is not None else 0.9,
            ),
        )
        content = resp.content or ""
        return GenerateSqlResponse(
            sql=_extract_sql_from_text(content),
            content=content,
            prompt_preview=prompt[:3000],
        )

    @staticmethod
    async def execute_sql(
        db: Session,
        knowledge_base_id: int,
        request: ExecuteSqlRequest,
    ) -> ExecuteSqlResponse:
        """按知识库关联数据源只读执行 SQL。"""
        from app.services.knowledge.sql_runtime import execute_knowledge_sql_async
        res = await execute_knowledge_sql_async(db, knowledge_base_id, request.sql,
                                               execute=execute_knowledge_base_sql_service)
        return ExecuteSqlResponse(
            sql=request.sql,
            columns=list(getattr(res, "columns", []) or []),
            rows=list(getattr(res, "rows", []) or []),
            row_count=int(getattr(res, "row_count", 0) or 0),
        )
    
    @staticmethod
    @isolated_retrieval
    def es_knowledge_retrieve(db: Session, knowledge_base_id: int, request: ESKnowledgeRetrieverRequest) -> ESKnowledgeRetrieverResponse:
        """
        ES知识词召回
        索引 `es_kb{knowledge_base_id}_knowledge`（见 vectorization.md 步骤4）。
        对 data_detail（词条 key）做 match 检索，分数按本批最大 _score 归一化。
        """
        kb = get_knowledge_base_active(db, knowledge_base_id)
        if not kb:
            raise HTTPException(status_code=404, detail="知识库不存在或已删除")

        top_k = request.top_k or 8
        q = (request.query or "").strip()
        logger.info(
            "ES knowledge retrieve: query=%s, kb_id=%s, top_k=%s",
            q[:200],
            knowledge_base_id,
            top_k,
        )

        index_name = f"es_kb{knowledge_base_id}_knowledge"
        results: List[RetrieverResult] = []

        # 获取 ES 配置
        es_config = _resolve_es_config_safe(db, getattr(kb, 'space_id', None))
        if not es_config:
            logger.warning("ES 未配置，ES 知识词召回返回空")
            return ESKnowledgeRetrieverResponse(results=[], total=0)
        release_read_connection(db)
        es_svc = thread_resource(ElasticsearchService, es_config)

        try:
            fetch_size = max(top_k, 1) * 2
            raw = es_svc.search_knowledge_terms(
                knowledge_base_id, q, top_k=fetch_size
            )
        except Exception as e:
            logger.exception("ES 知识词搜索失败: %s", e)
            return ESKnowledgeRetrieverResponse(results=[], total=0)

        logger.info(
            "ES knowledge retrieve pipeline: index=%s query=%r fetch_size=%s "
            "raw_rows=%s threshold=%s top_k=%s",
            index_name,
            q,
            fetch_size,
            len(raw),
            request.score_threshold,
            top_k,
        )

        normed = _normalize_es_hits(raw, top_k=top_k, threshold=request.score_threshold)
        logger.info(
            "ES knowledge retrieve after normalize/threshold: kept=%s",
            len(normed),
        )
        for norm, row in normed:
            detail = (row.get("data_detail") or "").strip()
            results.append(
                RetrieverResult(
                    score=norm,
                    content=detail,
                    metadata={
                        "data_detail": detail,
                        "quote_extend": row.get("quote_extend"),
                        "es_score": round(norm, 6),
                        "es_raw_score": row.get("es_raw_score"),
                        "normalized_score": round(norm, 6),
                        "index": index_name,
                        "source": "elasticsearch",
                    },
                )
            )

        return ESKnowledgeRetrieverResponse(results=results, total=len(results))
    
    @staticmethod
    @isolated_retrieval
    def sql_template_retrieve(
        db: Session,
        knowledge_base_id: int,
        request: SQLTemplateRetrieverRequest,
    ) -> SQLTemplateRetrieverResponse:
        """
        SQL 样例召回（对齐 Milvus field_type=sql_sample，见 docs/vectorization.md 步骤5）。
        优先：Embedding + Milvus 向量检索；否则：kb_sample_library 文本相似度回退。
        """
        top_k = request.top_k or 5
        threshold = request.score_threshold

        kb = get_knowledge_base_active(db, knowledge_base_id)
        if not kb:
            raise HTTPException(status_code=404, detail="知识库不存在或已删除")

        space_id = getattr(kb, 'space_id', None)

        logger.info(
            "SQL template retrieve: query=%s, kb_id=%s, top_k=%s",
            request.query,
            knowledge_base_id,
            top_k,
)

        results: List[RetrieverResult] = []

        # 获取 embedding 和向量库配置
        embedding_config = resolve_embedding_config(db, space_id, kb_id=knowledge_base_id)
        embedding_svc = EmbeddingService(embedding_config)
        vs_config = _resolve_vs_config(db, space_id, kb_id=knowledge_base_id)
        release_read_connection(db)

        if vs_config:
            try:
                qv = embedding_svc.get_embedding(request.query)
                if qv:
                    expr = f'field_type == "sql_sample" && kb_id == {int(knowledge_base_id)}'
                    hits = VectorStoreService.search_vectors_with_config(
                        vs_config,
                        knowledge_base_id,
                        qv,
                        top_k=top_k,
                        expr=expr,
                    )
                    for h in hits:
                        dist = float(h.get("distance") or 0.0)
                        name = (h.get("field_value") or "").strip()
                        sql_text = (h.get("sql_content") or "").strip()
                        results.append(
                            RetrieverResult(
                                score=dist,
                                content=name or sql_text[:200],
                                metadata={
                                    "query": name,
                                    "answer": sql_text,
                                    "vec_score": round(dist, 6),
                                    "source": "vector_store",
                                    "field_type": h.get("field_type"),
                                },
                            )
                        )
                    results = _apply_score_threshold(results, threshold)
            except Exception as e:
                logger.exception("SQL 样例 Milvus 召回失败，回退 DB: %s", e)

        return SQLTemplateRetrieverResponse(results=results, total=len(results))

    @staticmethod
    @isolated_retrieval
    def table_meta_retrieve(
        db: Session,
        knowledge_base_id: int,
        request: TableMetaRetrieverRequest,
    ) -> TableMetaRetrieverResponse:
        """
        表字段召回（对齐 Milvus field_type=table_column，见 docs/vectorization.md 步骤1）。
        优先：Embedding + Milvus；否则：kb_table_field 文本相似度回退。
        """
        top_k = request.top_k or 15
        threshold = request.score_threshold

        kb = get_knowledge_base_active(db, knowledge_base_id)
        if not kb:
            raise HTTPException(status_code=404, detail="知识库不存在或已删除")

        space_id = getattr(kb, 'space_id', None)

        logger.info(
            "Table meta retrieve: query=%s, kb_id=%s, top_k=%s",
            request.query,
            knowledge_base_id,
            top_k,
        )

        results: List[RetrieverResult] = []

        # 获取 embedding 和向量库配置
        embedding_config = resolve_embedding_config(db, space_id, kb_id=knowledge_base_id)
        embedding_svc = EmbeddingService(embedding_config)
        vs_config = _resolve_vs_config(db, space_id, kb_id=knowledge_base_id)
        release_read_connection(db)

        if vs_config:
            try:
                qv = embedding_svc.get_embedding(request.query)
                if qv:
                    expr = f'field_type == "table_column" && kb_id == {int(knowledge_base_id)}'
                    hits = VectorStoreService.search_vectors_with_config(
                        vs_config,
                        knowledge_base_id,
                        qv,
                        top_k=top_k,
                        expr=expr,
                    )
                    for h in hits:
                        dist = float(h.get("distance") or 0.0)
                        fv = (h.get("field_value") or "").strip()
                        results.append(
                            RetrieverResult(
                                score=dist,
                                content=fv,
                                metadata={
                                    "field_table": h.get("field_table") or "",
                                    "field_code": h.get("field_code") or "",
                                    "field_value": fv,
                                    "vec_score": round(dist, 6),
                                    "source": "vector_store",
                                    "field_type": h.get("field_type"),
                                },
                            )
                        )
                    results = _apply_score_threshold(results, threshold if threshold > 0 else None)
            except Exception as e:
                logger.exception("表字段 Milvus 召回失败，回退 DB: %s", e)

        return TableMetaRetrieverResponse(results=results, total=len(results))
    
    @staticmethod
    @isolated_retrieval
    def table_value_retrieve(
        db: Session,
        knowledge_base_id: int,
        request: TableValueRetrieverRequest,
    ) -> TableValueRetrieverResponse:
        """
        表值召回（对齐 Milvus field_type=table_value，见 vectorization.md 步骤2）。
        优先：Embedding + Milvus；若无结果且 ES 可用：对 es_kb*_table_value 做关键词回退。
        """
        top_k = request.top_k or 6
        threshold = request.score_threshold

        kb = get_knowledge_base_active(db, knowledge_base_id)
        if not kb:
            raise HTTPException(status_code=404, detail="知识库不存在或已删除")

        space_id = getattr(kb, 'space_id', None)

        logger.info(
            "Table value retrieve: query=%s, kb_id=%s, table_name=%s, top_k=%s",
            request.query,
            knowledge_base_id,
            request.table_name,
            top_k,
        )

        results: List[RetrieverResult] = []

        # 获取 embedding 和向量库配置
        embedding_config = resolve_embedding_config(db, space_id, kb_id=knowledge_base_id)
        embedding_svc = EmbeddingService(embedding_config)
        vs_config = _resolve_vs_config(db, space_id, kb_id=knowledge_base_id)
        release_read_connection(db)

        expr = _build_table_value_expr(
            knowledge_base_id, request.table_name, None
        )

        if vs_config:
            try:
                qv = embedding_svc.get_embedding(request.query)
                if qv:
                    hits = VectorStoreService.search_vectors_with_config(
                        vs_config,
                        knowledge_base_id,
                        qv,
                        top_k=max(top_k * 4, 20),
                        expr=expr,
                    )
                    results = _hits_to_table_value_results(hits, threshold, top_k)
            except Exception as e:
                logger.exception("表值 Milvus 召回失败，尝试 ES 回退: %s", e)

        # 获取 ES 配置
        return TableValueRetrieverResponse(results=results, total=len(results))

    @staticmethod
    @isolated_retrieval
    def global_value_meta_retrieve(
        db: Session,
        knowledge_base_id: int,
        request: GlobalValueMetaRetrieverRequest,
        *,
        _shared_query_vector: Optional[List[float]] = None,
    ) -> GlobalValueMetaRetrieverResponse:
        """
        表值召回（对应字段）（对齐 global-value-meta-retriever：在 table_value 域上检索并绑定 field_code）。
        若可解析出完整 field_code（表&&字段），则在 Milvus 中精确过滤该列上的取值；
        否则在向量检索结果上按 field_code 规则后过滤。
        table_name 可为：表名.字段名（推荐）、表名&字段名、表名&&字段名（与存储一致）、或仅表名。
        """
        top_k = request.top_k or 10
        threshold = request.score_threshold

        kb = get_knowledge_base_active(db, knowledge_base_id)
        if not kb:
            raise HTTPException(status_code=404, detail="知识库不存在或已删除")

        space_id = getattr(kb, 'space_id', None)

        table_only, resolved = _parse_global_value_table_param(request.table_name)
        if resolved and "&&" in resolved:
            segs = resolved.split("&&", 1)
            tn_hint = (segs[0] or "").strip()
            fn_hint = (segs[1] or "").strip()
        else:
            tn_hint = (table_only or "").strip()
            fn_hint = ""

        logger.info(
            "Global value meta retrieve: query=%s, kb_id=%s, table_name_param=%s, "
            "table_only=%s, resolved_field_code=%s, top_k=%s",
            request.query,
            knowledge_base_id,
            request.table_name,
            table_only,
            resolved,
            top_k,
        )

        results: List[RetrieverResult] = []

        # 获取 embedding 和向量库配置
        embedding_config = resolve_embedding_config(db, space_id, kb_id=knowledge_base_id)
        embedding_svc = EmbeddingService(embedding_config)
        vs_config = _resolve_vs_config(db, space_id, kb_id=knowledge_base_id)
        release_read_connection(db)

        expr_primary = _build_table_value_expr(
            knowledge_base_id,
            table_only,
            resolved,
        )
        post_filter_required = bool(resolved or tn_hint)

        if vs_config:
            try:
                qv = _shared_query_vector if _shared_query_vector is not None else embedding_svc.get_embedding(request.query)
                if qv:
                    logger.info(
                        "Global value meta retrieve: expr_primary=%s query=%r",
                        expr_primary,
                        request.query,
                    )
                    hits = VectorStoreService.search_vectors_with_config(
                        vs_config,
                        knowledge_base_id,
                        qv,
                        top_k=max(top_k * 8, 40),
                        expr=expr_primary,
                    )
                    logger.info(
                        "Global value meta retrieve: raw_hits=%s",
                        len(hits) if hits else 0,
                    )

                    if post_filter_required and hits:
                        filtered: List[Dict[str, Any]] = []
                        for h in hits:
                            fc = h.get("field_code")
                            if _field_code_matches_filter(
                                str(fc) if fc is not None else None,
                                resolved,
                                tn_hint,
                                fn_hint,
                            ):
                                filtered.append(h)
                        hits = filtered

                    results = _hits_to_table_value_results(hits, threshold, top_k)

            except Exception as e:
                logger.exception("表值(对应字段) Milvus 召回失败: %s", e)

        return GlobalValueMetaRetrieverResponse(
            results=results, total=len(results)
        )

    @staticmethod
    async def multi_global_value_meta_retrieve(
        db: Session,
        knowledge_base_id: int,
        request: MultiGlobalValueMetaRetrieverRequest,
    ) -> GlobalValueMetaRetrieverResponse:
        """每列向量/关键词各取 TopK 后稳定合并去重，最多 2*TopK，不重排。"""
        query = request.query.strip()
        scopes = {}
        for token in request.table_name:
            token = token.strip()
            if token:
                table_only, resolved = _parse_global_value_table_param(token)
                scopes.setdefault((table_only, resolved), token)
        if not scopes or not query:
            return GlobalValueMetaRetrieverResponse(results=[], total=0)

        top_k = request.top_k or 10

        def load_config(db):
            kb = get_knowledge_base_active(db, knowledge_base_id)
            if not kb:
                raise HTTPException(status_code=404, detail="知识库不存在或已删除")
            space_id = getattr(kb, "space_id", None)
            store = None
            embedding_svc = None
            try:
                store = _resolve_vs_config(db, space_id, kb_id=knowledge_base_id)
                if store:
                    embedding_config = resolve_embedding_config(db, space_id, kb_id=knowledge_base_id)
                    embedding_svc = EmbeddingService(embedding_config)
            except Exception:
                logger.exception("多列同值向量配置不可用，继续关键词召回")
            es_config = _resolve_es_config_safe(db, space_id)
            return store, embedding_svc, es_config

        store, embedding_svc, es_config = await read_database(db, load_config)
        semaphore = asyncio.Semaphore(8)

        async def _embed():
            try:
                return await RETRIEVAL_WORK.run(embedding_svc.get_embedding, query)
            except Exception:
                logger.exception("多列同值 query embedding 失败，继续关键词召回")
                return None

        embedding_task = asyncio.create_task(_embed()) if embedding_svc else None

        def _in_scope(hit, table_only, resolved):
            if resolved:
                return hit.get("field_code") == resolved
            return not table_only or hit.get("field_table") == table_only

        async def _vector(table_only, resolved):
            if embedding_task is None:
                return []
            query_vector = await embedding_task
            if not query_vector:
                return []
            try:
                async with semaphore:
                    hits = await RETRIEVAL_WORK.run(
                        VectorStoreService.search_vectors_with_config,
                        store, knowledge_base_id, query_vector,
                        top_k=top_k,
                        expr=_build_table_value_expr(knowledge_base_id, table_only, resolved),
                    )
                hits = [h for h in list(hits or [])[:top_k] if _in_scope(h, table_only, resolved)]
                rows = _hits_to_table_value_results(hits, request.score_threshold, len(hits))
                rows = _unique_retriever_results(rows)
                return rows[:top_k]
            except Exception:
                logger.exception("多列同值字段 %s 向量召回失败，继续关键词召回", resolved or table_only)
                return []

        def _search_keywords(table_only, resolved):
            return thread_resource(ElasticsearchService, es_config).search_table_values(
                knowledge_base_id, query, top_k=top_k,
                field_table=table_only, field_code=resolved,
            )

        async def _keyword(table_only, resolved):
            if not es_config:
                return []
            try:
                async with semaphore:
                    hits = await RETRIEVAL_WORK.run(_search_keywords, table_only, resolved)
                hits = [h for h in list(hits or [])[:top_k] if _in_scope(h, table_only, resolved)]
                rows = [RetrieverResult(
                    score=score, content=str(hit.get("field_value") or "").strip(),
                    metadata={
                        "field_table": hit.get("field_table"), "field_code": hit.get("field_code"),
                        "field_value": hit.get("field_value"), "source": "elasticsearch",
                        "es_raw_score": hit.get("es_raw_score"), "es_score": score,
                    },
                ) for score, hit in _normalize_es_hits(
                    hits, top_k=len(hits), threshold=request.keyword_score_threshold,
                )]
                rows = _unique_retriever_results(rows)
                return rows[:top_k]
            except Exception:
                logger.exception("多列同值字段 %s 关键词召回失败，继续向量召回", resolved or table_only)
                return []

        async def _one(table_only, resolved):
            vectors, keywords = await asyncio.gather(_vector(table_only, resolved), _keyword(table_only, resolved))
            return vectors, keywords

        parts = await asyncio.gather(*[_one(*scope) for scope in scopes])
        merged = _union_multi_column_results(parts, top_k)
        return GlobalValueMetaRetrieverResponse(results=merged, total=len(merged))

    @staticmethod
    def _build_ner_narrative(query: str, rows: List[models.KbNerRow]) -> str:
        if not rows:
            return "未在知识库 NER 映射中找到别名字段包含所给实体的记录。"
        head = (
            f"结合问句「{query.strip()}」，"
            if (query or "").strip()
            else ""
        )
        lines = [
            f"{head}根据别名匹配，实体与数据表的对应关系如下：",
        ]
        for r in rows:
            std = (r.standard_name or "").strip() or "（未配置标准名）"
            al = (r.alias or "").strip()
            lines.append(
                f"• 别名「{al}」对应数据表 `{r.table_name}` 的字段 `{r.field_name}`，"
                f"标准库名称为「{std}」。"
            )
        return "\n".join(lines)

    @staticmethod
    @isolated_retrieval
    def ner_retrieve(
        db: Session,
        knowledge_base_id: int,
        request: NerRetrieverRequest,
    ) -> NerRetrieverResponse:
        """
        在 kb_ner_row 中按别名 LIKE 匹配实体子串，返回表名、字段名、标准名(作 database_name)、别名及自然语言摘要。
        """
        if not get_knowledge_base_active(db, knowledge_base_id):
            raise HTTPException(status_code=404, detail="知识库不存在或已删除")

        entities = [str(x).strip() for x in (request.entity or []) if str(x).strip()]
        if not entities:
            return NerRetrieverResponse(results=[], total=0, narrative="实体列表为空。")

        top_k = request.top_k or 20
        rows = search_kb_ner_rows_alias_contains_entities(
            db, knowledge_base_id, entities, top_k
        )
        results: List[RetrieverResult] = []
        for r in rows:
            al = (r.alias or "").strip()
            std = (r.standard_name or "").strip()
            results.append(
                RetrieverResult(
                    score=1.0,
                    content=al or f"{r.table_name}.{r.field_name}",
                    metadata={
                        "table_name": r.table_name,
                        "field_name": r.field_name,
                        "database_name": std,
                        "alias": al,
                        "source": "kb_ner_row",
                    },
                )
            )
        narrative = AutoBIAtomicService._build_ner_narrative(
            request.query or "", rows
        )
        return NerRetrieverResponse(
            results=results, total=len(results), narrative=narrative
        )
