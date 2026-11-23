import logging
import asyncio
import re
import threading
import hashlib
import json
import uuid
import time
from tempfile import SpooledTemporaryFile
from datetime import date, datetime
from decimal import Decimal
from functools import wraps
from urllib.parse import quote_plus

from fastapi import HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from .... import models
from ....core.crypto import decrypt_password
from ....core.database import create_external_mysql_engine, query_engine
from ....repositories.knowledge.knowledge_base.repository import (
    apply_knowledge_base_update,
    count_kb_table_structures,
    create_knowledge_base,
    get_kb_table_structure_by_id_with_fields,
    get_knowledge_access_active_by_id,
    apply_kb_table_structure_update,
    delete_kb_table_structure_by_id,
    get_kb_table_structure_by_id,
    apply_kb_table_field_update,
    delete_kb_table_field_by_id,
    get_kb_table_field_by_id,
    delete_kb_knowledge_term_by_id,
    delete_kb_sample_library_by_id,
    get_knowledge_base_active,
    get_knowledge_base_detail,
    clone_knowledge_base_relationships,
    list_sample_libraries_by_ids_and_access,
    list_knowledge_terms_by_ids_and_access,
    list_table_fields_by_ids_and_table_ids,
    list_knowledge_bases,
    list_table_structures_by_ids_and_access,
    upsert_kb_sample_libraries,
    upsert_kb_knowledge_terms,
    upsert_kb_table_structures_and_fields_new_format,
    upsert_kb_table_structures_and_fields_old_format,
    soft_delete_knowledge_base,
    set_knowledge_base_table_count_by_id,
)
from ..embedding_service import EmbeddingService
from ..es_service import ElasticsearchService
from ....schemas.knowledge_base import KnowledgeBaseExecuteSqlResponse
from ...config_resolver import resolve_embedding_config, resolve_es_config
from ...vector_store.service import VectorStoreService
from ...vector_store.providers import get_vector_store_provider

logger = logging.getLogger(__name__)


def _external_db_type(data_source) -> str:
    return (getattr(data_source, "database_type", "") or "").strip().lower()


def _is_postgresql_source(data_source) -> bool:
    return _external_db_type(data_source) in {"postgresql", "postgres", "pgsql"}


def _quote_identifier(identifier: str, *, postgres: bool = False) -> str:
    raw = str(identifier or "")
    if postgres:
        return '"' + raw.replace('"', '""') + '"'
    return "`" + raw.replace("`", "``") + "`"


def _external_db_name(data_source) -> str:
    if _is_postgresql_source(data_source):
        db_name = (data_source.default_database or "").strip()
        if not db_name or db_name == "public":
            return "postgres"
        return db_name
    return data_source.default_database


def _create_external_source_engine(data_source, streaming_query=False):
    encoded_password = quote_plus(decrypt_password(data_source.password))
    if _is_postgresql_source(data_source):
        url = (
            f"postgresql+psycopg2://{data_source.username}:{encoded_password}"
            f"@{data_source.host}:{data_source.port}/{_external_db_name(data_source)}"
        )
    elif _external_db_type(data_source) in {"mysql", ""}:
        driver = 'mysql+pymysql' if streaming_query else 'mysql+mysqlconnector'
        url = (
            f"{driver}://{data_source.username}:{encoded_password}"
            f"@{data_source.host}:{data_source.port}/{data_source.default_database}"
        )
    else:
        raise HTTPException(status_code=400, detail=f"暂不支持的数据源类型: {data_source.database_type}")
    return query_engine(url) if streaming_query else create_external_mysql_engine(url)


def _distinct_values_sql(data_source, table_name: str, field_name: str) -> str:
    postgres = _is_postgresql_source(data_source)
    field_sql = _quote_identifier(field_name, postgres=postgres)
    table_sql = _quote_identifier(table_name, postgres=postgres)
    return f"SELECT DISTINCT {field_sql} FROM {table_sql} WHERE {field_sql} IS NOT NULL ORDER BY {field_sql}"


VECTORIZATION_MODE_FULL = "full"
VECTORIZATION_MODE_INCREMENTAL = "incremental"
VALUE_EMBEDDING_BATCH_SIZE = 1000
DEFAULT_EMBEDDING_BATCH_SLEEP_SECONDS = 0.5
SOURCE_FETCH_MANY_SIZE = 5000


class VectorizationCancelled(Exception):
    """Raised when a running vectorization task is cancelled by the user."""


def _normalize_vectorization_mode(mode: str = None) -> str:
    mode = (mode or VECTORIZATION_MODE_INCREMENTAL).strip().lower()
    if mode not in {VECTORIZATION_MODE_FULL, VECTORIZATION_MODE_INCREMENTAL}:
        raise HTTPException(status_code=400, detail="向量化模式仅支持 full 或 incremental")
    return mode


def _transition_vectorization_status(db: Session, knowledge_base_id: int, expected, status: str, **values) -> bool:
    """Change job state only if another request has not already changed it."""
    changed = (
        db.query(models.KnowledgeBase)
        .filter(
            models.KnowledgeBase.id == knowledge_base_id,
            models.KnowledgeBase.vectorization_status.in_(expected),
        )
        .update({"vectorization_status": status, **values}, synchronize_session=False)
    )
    db.commit()
    return bool(changed)


def _finish_vectorization(db: Session, knowledge_base_id: int, status: str) -> None:
    values = {"vector_progress": 100, "current_vectorization_step": None} if status == "completed" else {}
    if not _transition_vectorization_status(db, knowledge_base_id, ("processing",), status, **values):
        # A cancellation accepted before completion/failure wins the race.
        _mark_vectorization_cancelled(db, knowledge_base_id)


def _is_vectorization_cancelled(db: Session, knowledge_base_id: int) -> bool:
    check_db = db
    should_close = False
    if isinstance(db, Session):
        from ....core.database import SessionLocal

        check_db = SessionLocal()
        should_close = True

    try:
        status = (
            check_db.query(models.KnowledgeBase.vectorization_status)
            .filter(models.KnowledgeBase.id == knowledge_base_id)
            .scalar()
        )
    finally:
        if should_close:
            check_db.close()
    return status in {"cancelling", "cancelled"}


def _raise_if_vectorization_cancelled(db: Session, knowledge_base_id: int) -> None:
    if _is_vectorization_cancelled(db, knowledge_base_id):
        raise VectorizationCancelled(f"Vectorization cancelled for knowledge base {knowledge_base_id}")


def _mark_vectorization_cancelled(db: Session, knowledge_base_id: int):
    return _transition_vectorization_status(
        db, knowledge_base_id, ("cancelling",), "cancelled", current_vectorization_step=None,
    )


def _hash_text(*parts) -> str:
    raw = "\u001f".join("" if p is None else str(p) for p in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _canonical_value(value) -> str:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    return str(value)


def _manifest_key(kb_id: int, domain: str, *parts) -> str:
    raw = "|".join([str(kb_id), domain] + ["" if p is None else str(p) for p in parts])
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    prefix_parts = [str(kb_id), domain] + [("" if p is None else str(p))[:48] for p in parts[:2]]
    prefix = "|".join(prefix_parts)
    return f"{prefix}|{digest}"[:512]


def _load_manifest_map(db: Session, kb_id: int, domain: str, table_name: str = None, field_code: str = None):
    query = db.query(models.KbVectorManifest).filter(
        models.KbVectorManifest.kb_id == kb_id,
        models.KbVectorManifest.domain == domain,
    )
    if table_name is not None:
        query = query.filter(models.KbVectorManifest.table_name == table_name)
    if field_code is not None:
        query = query.filter(models.KbVectorManifest.field_code == field_code)
    return {row.item_key: row for row in query.all()}


def _upsert_manifest(
    db: Session,
    *,
    kb_id: int,
    domain: str,
    item_key: str,
    run_id: str,
    table_name: str = None,
    field_code: str = None,
    item_value: str = None,
    embedding_hash: str = None,
    payload_hash: str = None,
    existing_rows: dict = None,
):
    row = existing_rows.get(item_key) if existing_rows is not None else (
        db.query(models.KbVectorManifest)
        .filter(
            models.KbVectorManifest.kb_id == kb_id,
            models.KbVectorManifest.domain == domain,
            models.KbVectorManifest.item_key == item_key,
        )
        .first()
    )
    if row is None:
        row = models.KbVectorManifest(
            kb_id=kb_id,
            domain=domain,
            item_key=item_key,
        )
        db.add(row)
        if existing_rows is not None:
            existing_rows[item_key] = row
    row.table_name = table_name
    row.field_code = field_code
    row.item_value = item_value
    row.embedding_hash = embedding_hash
    row.payload_hash = payload_hash
    row.last_seen_run_id = run_id
    return row


def _delete_manifest_scope(db: Session, kb_id: int, domain: str, table_name: str = None, field_code: str = None):
    query = db.query(models.KbVectorManifest).filter(
        models.KbVectorManifest.kb_id == kb_id,
        models.KbVectorManifest.domain == domain,
    )
    if table_name is not None:
        query = query.filter(models.KbVectorManifest.table_name == table_name)
    if field_code is not None:
        query = query.filter(models.KbVectorManifest.field_code == field_code)
    query.delete(synchronize_session=False)


def _vector_sync_fingerprint(db, knowledge_base, embedding_config):
    """A manifest is reusable only for the same model and destination."""
    store = VectorStoreService.resolve_active_store(
        db, getattr(knowledge_base, "space_id", None), kb_id=knowledge_base.id
    )
    identity = {
        "version": 2,
        "embedding": {key: embedding_config.get(key) for key in ("provider", "base_url", "model", "dimension")},
        "store": {key: store.get(key) for key in ("provider", "host", "port", "database", "collection_prefix", "username")},
    }
    return _hash_text(json.dumps(identity, sort_keys=True, ensure_ascii=False))


def _es_sync_fingerprint(config):
    return _hash_text(json.dumps(
        {key: config.get(key) for key in ("host", "port", "username")}, sort_keys=True
    ))


def _ensure_vector_collection(db, knowledge_base, dimension):
    kb_id = knowledge_base.id
    space_id = getattr(knowledge_base, "space_id", None)
    if not VectorStoreService.collection_exists_for_kb(db, kb_id, space_id=space_id):
        # All vector domains share a collection. Keep unselected domains pending
        # too, so a later incremental step cannot trust a disappeared target.
        for domain in ("table_column", "table_value", "sql_sample"):
            _invalidate_manifest_scope(db, kb_id, domain)
    if not VectorStoreService.create_collection_for_kb(db, kb_id, dimension=dimension, space_id=space_id):
        raise RuntimeError("Failed to create vector collection; check the configured embedding dimension")


def _ensure_es_manifest_target(db, kb_id, domain, es_svc, index_name):
    if not es_svc.index_exists(index_name):
        _invalidate_manifest_scope(db, kb_id, domain)


def _invalidate_manifest_scope(db, kb_id, domain, table_name=None, field_code=None):
    query = db.query(models.KbVectorManifest).filter_by(kb_id=kb_id, domain=domain)
    if table_name is not None:
        query = query.filter_by(table_name=table_name)
    if field_code is not None:
        query = query.filter_by(field_code=field_code)
    query.update({"embedding_hash": None, "payload_hash": None}, synchronize_session="fetch")
    # Persist before external deletes, which cannot be rolled back with SQL.
    db.commit()


def _reset_vector_domain(db, knowledge_base, domain):
    kb_id = knowledge_base.id
    _raise_if_vectorization_cancelled(db, kb_id)
    _invalidate_manifest_scope(db, kb_id, domain)
    if not VectorStoreService.delete_vectors_by_table_field(
        db, kb_id, domain, space_id=getattr(knowledge_base, "space_id", None)
    ):
        raise RuntimeError(f"Failed to reset {domain} vectors")
    _delete_manifest_scope(db, kb_id, domain)
    db.commit()


def _reset_es_domain(db, kb_id, domain, delete_index):
    _raise_if_vectorization_cancelled(db, kb_id)
    _invalidate_manifest_scope(db, kb_id, domain)
    if not delete_index(kb_id):
        raise RuntimeError(f"Failed to reset {domain} index")
    _delete_manifest_scope(db, kb_id, domain)
    db.commit()


def _manifest_field_scopes(db, kb_id, domain):
    return set(db.query(models.KbVectorManifest.table_name, models.KbVectorManifest.field_code)
               .filter_by(kb_id=kb_id, domain=domain).distinct().all())


def _remove_inactive_vector_scopes(db, knowledge_base, domain, active_scopes):
    for table_name, field_code in _manifest_field_scopes(db, knowledge_base.id, domain) - active_scopes:
        _raise_if_vectorization_cancelled(db, knowledge_base.id)
        _invalidate_manifest_scope(db, knowledge_base.id, domain, table_name, field_code)
        if not VectorStoreService.delete_vectors_by_table_field(
            db, knowledge_base.id, domain, table_name=table_name, field_code=field_code,
            space_id=getattr(knowledge_base, "space_id", None),
        ):
            raise RuntimeError(f"Failed to delete inactive {domain}: {table_name}.{field_code}")
        _delete_manifest_scope(db, knowledge_base.id, domain, table_name, field_code)
        db.commit()


def _manifest_rows_for_batch(db, manifests):
    if not manifests:
        return {}
    first = manifests[0]
    rows = db.query(models.KbVectorManifest).filter(
        models.KbVectorManifest.kb_id == first["kb_id"],
        models.KbVectorManifest.domain == first["domain"],
        models.KbVectorManifest.item_key.in_([item["item_key"] for item in manifests]),
    ).all()
    return {row.item_key: row for row in rows}


def _prepare_manifest_writes(db, manifests):
    rows = _manifest_rows_for_batch(db, manifests)
    for manifest in manifests:
        _upsert_manifest(db, **dict(manifest, embedding_hash=None, payload_hash=None), existing_rows=rows)
    # Pending entries retain identity even if an external bulk write only partly
    # succeeds. A retry must rewrite them or remove them if the source vanished.
    db.commit()


def _confirm_manifest_writes(db, manifests):
    rows = _manifest_rows_for_batch(db, manifests)
    for manifest in manifests:
        _upsert_manifest(db, **manifest, existing_rows=rows)
    db.commit()


def _checked_embeddings(embedding_svc, texts):
    embeddings = embedding_svc.get_embeddings(texts)
    if len(embeddings) != len(texts) or any(len(vector) != embedding_svc.dimension for vector in embeddings):
        raise RuntimeError("Embedding response count or dimension does not match the request")
    return embeddings


def _write_vector_batch(db, knowledge_base, domain, data, manifests):
    if not data:
        return
    kb_id = knowledge_base.id
    space_id = getattr(knowledge_base, "space_id", None)
    _raise_if_vectorization_cancelled(db, kb_id)
    _prepare_manifest_writes(db, manifests)
    delete_items = []
    for item in data:
        selector = {key: item[key] for key in ("field_table", "field_code")}
        if domain == "table_value":
            selector["field_value"] = item["field_value"]
        delete_items.append(selector)
    # Milvus uses auto-generated primary keys: delete before every insertion,
    # including retries of an interrupted full rebuild.
    if not VectorStoreService.delete_vector_items(db, kb_id, domain, delete_items, space_id):
        raise RuntimeError(f"Failed to replace {domain} vectors")
    _raise_if_vectorization_cancelled(db, kb_id)
    if not VectorStoreService.insert_vectors(db, kb_id, data, space_id):
        raise RuntimeError(f"Failed to insert {domain} vectors")
    _confirm_manifest_writes(db, manifests)


def _delete_stale_vectors(db, knowledge_base, domain, rows):
    if not rows:
        return
    items = []
    for row in rows:
        row.embedding_hash = row.payload_hash = None
        item = {"field_table": row.table_name or "", "field_code": row.field_code or ""}
        if domain == "table_value":
            item["field_value"] = row.item_value or ""
        items.append(item)
    db.commit()
    _raise_if_vectorization_cancelled(db, knowledge_base.id)
    if not VectorStoreService.delete_vector_items(
        db, knowledge_base.id, domain, items, getattr(knowledge_base, "space_id", None)
    ):
        raise RuntimeError(f"Failed to delete stale {domain} vectors")
    for row in rows:
        db.delete(row)
    db.commit()


def _delete_stale_es(db, kb_id, rows, index_name, delete_by_ids):
    if not rows:
        return
    for row in rows:
        row.embedding_hash = row.payload_hash = None
    db.commit()
    _raise_if_vectorization_cancelled(db, kb_id)
    ids = [ElasticsearchService._doc_id(index_name, row.item_key) for row in rows]
    if not delete_by_ids(kb_id, ids):
        raise RuntimeError(f"Failed to delete stale documents from {index_name}")
    for row in rows:
        db.delete(row)
    db.commit()


def _keep_manifest_snapshot(func):
    dirty_field = {
        "_do_knowledge_term_to_es": "knowledge_term_dirty",
        "_do_sample_library_vectorization": "sample_library_dirty",
    }.get(func.__name__)

    @wraps(func)
    async def sync_step(db, *args, **kwargs):
        if not isinstance(db, Session):
            return await func(db, *args, **kwargs)
        previous = db.expire_on_commit
        knowledge_base = args[0] if args else kwargs.get("knowledge_base")
        kb_id = knowledge_base.id if dirty_field else None
        persisted_kb = isinstance(knowledge_base, models.KnowledgeBase)
        # A step reads one source snapshot. Keep its manifest snapshot through
        # batch commits instead of reloading every remaining value one by one.
        # Cancellation always reads from a separate fresh session.
        db.expire_on_commit = False
        try:
            if dirty_field:
                if persisted_kb:
                    db.query(models.KnowledgeBase).filter_by(id=kb_id).update(
                        {dirty_field: False}, synchronize_session=False,
                    )
                else:
                    setattr(knowledge_base, dirty_field, False)
                db.commit()
                # Details may have been eager-loaded before the flag was cleared.
                # Reload the source after this boundary, including nested rows.
                db.expire_all()
            return await func(db, *args, **kwargs)
        except BaseException:
            if dirty_field:
                try:
                    db.rollback()
                    if persisted_kb:
                        db.query(models.KnowledgeBase).filter_by(id=kb_id).update(
                            {dirty_field: True}, synchronize_session=False,
                        )
                    else:
                        setattr(knowledge_base, dirty_field, True)
                    db.commit()
                except Exception:
                    logger.exception("Failed to restore %s for knowledge base %s", dirty_field, kb_id)
            raise
        finally:
            db.expire_on_commit = previous
    return sync_step


def _iter_distinct_values(source_engine, data_source, table_name: str, field_name: str, fetch_size: int = SOURCE_FETCH_MANY_SIZE):
    """Release the source transaction before slow embedding or ES requests.

    Spooling preserves one complete DISTINCT result while bounding memory. A
    disconnected read can restart safely because no values have been yielded.
    """
    query = text(_distinct_values_sql(data_source, table_name, field_name))
    with SpooledTemporaryFile(max_size=1024 * 1024, mode="w+t", encoding="utf-8") as values:
        for attempt in range(2):
            values.seek(0)
            values.truncate()
            try:
                with source_engine.connect() as source_conn:
                    result = source_conn.execution_options(stream_results=True).execute(query)
                    try:
                        while True:
                            rows = result.fetchmany(fetch_size)
                            if not rows:
                                break
                            for row in rows:
                                if row[0] is not None:
                                    values.write(json.dumps(_canonical_value(row[0]), ensure_ascii=False) + "\n")
                    finally:
                        result.close()
                break
            except DBAPIError as exc:
                if not exc.connection_invalidated or attempt:
                    raise
                logger.warning("Source connection lost reading %s.%s; reconnecting", table_name, field_name)

        values.seek(0)
        for line in values:
            yield json.loads(line)


def data_source_database_type_label(data_source) -> str:
    db_type = _external_db_type(data_source)
    if db_type in {"postgresql", "postgres", "pgsql"}:
        return "PostgreSQL"
    if db_type in {"mysql", ""}:
        return "MySQL"
    return data_source.database_type or "SQL"


def get_knowledge_base_database_type_service(db: Session, knowledge_base_id: int, space_id: int = None) -> str:
    knowledge_base = get_knowledge_base_detail(db, knowledge_base_id, space_id)
    if not knowledge_base or not knowledge_base.knowledge_access or not knowledge_base.knowledge_access.data_source:
        return "SQL"
    return data_source_database_type_label(knowledge_base.knowledge_access.data_source)


def get_knowledge_base_detail_service(db: Session, knowledge_base_id: int, space_id: int = None):
    knowledge_base = get_knowledge_base_detail(db, knowledge_base_id, space_id)
    if knowledge_base is None:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    return knowledge_base


def create_knowledge_base_service(db: Session, knowledge_base, space_id: int = None):
    # 验证知识接入是否存在
    knowledge_access = get_knowledge_access_active_by_id(db, knowledge_base.knowledge_access_id, space_id)
    if not knowledge_access:
        raise HTTPException(status_code=404, detail="Knowledge access not found")

    data_dict = knowledge_base.dict()
    if space_id is not None:
        data_dict['space_id'] = space_id
    db_knowledge_base = create_knowledge_base(db, data_dict)
    db.commit()
    db.refresh(db_knowledge_base)
    return db_knowledge_base


def list_knowledge_base_service(db: Session, skip: int, limit: int, space_id: int = None):
    return list_knowledge_bases(db, skip, limit, space_id)


def get_kb_table_structure_service(db: Session, kb_table_structure_id: int, space_id: int = None):
    kb_table_structure = get_kb_table_structure_by_id_with_fields(db, kb_table_structure_id, space_id)
    if not kb_table_structure:
        raise HTTPException(status_code=404, detail="KB table structure not found")
    return kb_table_structure


def update_knowledge_base_service(db: Session, knowledge_base_id: int, knowledge_base_update, space_id: int = None):
    db_knowledge_base = get_knowledge_base_active(db, knowledge_base_id, space_id)
    if db_knowledge_base is None:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    # 如果更新了知识接入ID，校验新接入是否存在
    if knowledge_base_update.knowledge_access_id:
        knowledge_access = get_knowledge_access_active_by_id(db, knowledge_base_update.knowledge_access_id, space_id)
        if not knowledge_access:
            raise HTTPException(status_code=404, detail="Knowledge access not found")

    update_data = knowledge_base_update.dict(exclude_unset=True)
    if space_id is not None and 'space_id' not in update_data:
        update_data['space_id'] = space_id
    apply_knowledge_base_update(db, db_knowledge_base, update_data)

    db.commit()
    db.refresh(db_knowledge_base)
    return db_knowledge_base


def delete_knowledge_base_service(db: Session, knowledge_base_id: int, space_id: int = None):
    db_knowledge_base = get_knowledge_base_active(db, knowledge_base_id, space_id)
    if db_knowledge_base is None:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    soft_delete_knowledge_base(db, db_knowledge_base)
    db.commit()
    return {"message": "Knowledge base deleted successfully"}


async def _do_vectorization(knowledge_base_id: int, steps_config: dict = None, mode: str = VECTORIZATION_MODE_INCREMENTAL):
    """
    执行向量化任务（异步）
    在新线程中运行，每个步骤使用独立的数据库会话以避免长事务连接泄漏。

    Args:
        steps_config: 向量化步骤配置，包含5个步骤的布尔值
    """
    from ....core.database import SessionLocal
    import json

    mode = _normalize_vectorization_mode(mode)

    # 默认步骤配置
    if steps_config is None:
        steps_config = {
            "field_vectorization": True,
            "value_vectorization": True,
            "table_field_to_es": False,
            "knowledge_term_to_es": False,
            "sample_library_to_es": False,
        }

    collection_name = f"v_kb{knowledge_base_id}"
    enabled_steps = [k for k, v in steps_config.items() if v]
    total_steps = len(enabled_steps)
    current_step_index = 0

    logger.info(f"Starting vectorization for knowledge base {knowledge_base_id} with mode={mode}, steps: {enabled_steps}")

    try:
        # The request owns the processing state; never reset a cancellation here.
        db = SessionLocal()
        try:
            kb = get_knowledge_base_active(db, knowledge_base_id)
            if not kb or kb.vectorization_status == "cancelled":
                return
            _raise_if_vectorization_cancelled(db, knowledge_base_id)
            kb.vector_collection_name = collection_name
            db.commit()
        finally:
            db.close()

        # 步骤1: 字段向量化
        if steps_config.get("field_vectorization", False):
            current_step_index += 1
            db = SessionLocal()
            try:
                _raise_if_vectorization_cancelled(db, knowledge_base_id)
                kb = get_knowledge_base_detail(db, knowledge_base_id)
                if not kb:
                    raise Exception("Failed to get knowledge base detail")
                kb.current_vectorization_step = "field_vectorization"
                db.commit()
                logger.info(f"Step {current_step_index}/{total_steps}: Field vectorization")
                await _do_field_vectorization(db, kb, collection_name, current_step_index, total_steps, mode)
                _raise_if_vectorization_cancelled(db, knowledge_base_id)
            finally:
                db.close()

        # 步骤2: 值向量化
        if steps_config.get("value_vectorization", False):
            current_step_index += 1
            db = SessionLocal()
            try:
                _raise_if_vectorization_cancelled(db, knowledge_base_id)
                kb = get_knowledge_base_detail(db, knowledge_base_id)
                if not kb:
                    raise Exception("Failed to get knowledge base detail")
                kb.current_vectorization_step = "value_vectorization"
                db.commit()
                logger.info(f"Step {current_step_index}/{total_steps}: Value vectorization")
                await _do_table_value_vectorization(db, kb, collection_name, current_step_index, total_steps, mode)
                _raise_if_vectorization_cancelled(db, knowledge_base_id)
            finally:
                db.close()

        # 步骤3: 值存ES
        if steps_config.get("table_field_to_es", False):
            current_step_index += 1
            db = SessionLocal()
            try:
                _raise_if_vectorization_cancelled(db, knowledge_base_id)
                kb = get_knowledge_base_detail(db, knowledge_base_id)
                if not kb:
                    raise Exception("Failed to get knowledge base detail")
                kb.current_vectorization_step = "table_field_to_es"
                kb.vector_progress = 0
                db.commit()
                logger.info(f"Step {current_step_index}/{total_steps}: Table field values to ES")
                await _do_table_values_to_es(db, kb, current_step_index, total_steps, mode)
                _raise_if_vectorization_cancelled(db, knowledge_base_id)
            finally:
                db.close()

        # 步骤4: 知识词存ES
        if steps_config.get("knowledge_term_to_es", False):
            current_step_index += 1
            db = SessionLocal()
            try:
                _raise_if_vectorization_cancelled(db, knowledge_base_id)
                kb = get_knowledge_base_detail(db, knowledge_base_id)
                if not kb:
                    raise Exception("Failed to get knowledge base detail")
                kb.current_vectorization_step = "knowledge_term_to_es"
                kb.vector_progress = 0
                db.commit()
                logger.info(f"Step {current_step_index}/{total_steps}: Knowledge term to ES")
                await _do_knowledge_term_to_es(db, kb, current_step_index, total_steps, mode)
                _raise_if_vectorization_cancelled(db, knowledge_base_id)
            finally:
                db.close()

        # 步骤5: 样例库向量化
        if steps_config.get("sample_library_to_es", False):
            current_step_index += 1
            db = SessionLocal()
            try:
                _raise_if_vectorization_cancelled(db, knowledge_base_id)
                kb = get_knowledge_base_detail(db, knowledge_base_id)
                if not kb:
                    raise Exception("Failed to get knowledge base detail")
                kb.current_vectorization_step = "sample_library_to_es"
                kb.vector_progress = 0
                db.commit()
                logger.info(f"Step {current_step_index}/{total_steps}: Sample library vectorization")
                await _do_sample_library_vectorization(db, kb, collection_name, current_step_index, total_steps, mode)
                _raise_if_vectorization_cancelled(db, knowledge_base_id)
            finally:
                db.close()

        # 完成向量化 — 独立短会话
        db = SessionLocal()
        try:
            _finish_vectorization(db, knowledge_base_id, "completed")
            logger.info(f"Vectorization completed for knowledge base {knowledge_base_id}")
        finally:
            db.close()

    except VectorizationCancelled:
        logger.info("Vectorization cancelled for knowledge base %s", knowledge_base_id)
        db = SessionLocal()
        try:
            _mark_vectorization_cancelled(db, knowledge_base_id)
        except Exception:
            logger.exception("vectorization cancelled status update failed")
        finally:
            db.close()

    except Exception as e:
        logger.error(f"Vectorization failed for knowledge base {knowledge_base_id}: {e}", exc_info=True)
        # 更新状态为失败 — 使用全新会话
        db = SessionLocal()
        try:
            _finish_vectorization(db, knowledge_base_id, "failed")
        except Exception:
            logger.exception("vectorization status update failed")
        finally:
            db.close()


@_keep_manifest_snapshot
async def _do_field_vectorization(db: Session, knowledge_base, collection_name: str, current_step: int, total_steps: int, mode: str = VECTORIZATION_MODE_INCREMENTAL):
    """Synchronize enabled columns, including removed tables and empty selections."""
    kb_id = knowledge_base.id
    space_id = getattr(knowledge_base, "space_id", None)
    _raise_if_vectorization_cancelled(db, kb_id)
    embedding_config = resolve_embedding_config(db, space_id, kb_id=kb_id)
    embedding_svc = EmbeddingService(embedding_config)
    fingerprint = _vector_sync_fingerprint(db, knowledge_base, embedding_config)
    _ensure_vector_collection(db, knowledge_base, embedding_svc.dimension)

    tables_data = {}
    active_scopes = set()
    for table in knowledge_base.kb_table_structures:
        items = []
        for field in table.kb_table_fields:
            if not field.is_enabled:
                continue
            field_code = f"{table.table_name}&&{field.field_name}"
            active_scopes.add((table.table_name, field_code))
            items.append({
                "kb_id": kb_id, "field_type": "table_column", "field_table": table.table_name,
                "field_code": field_code,
                "field_value": f"{table.table_alias or table.table_name}&&{field.field_alias or field.field_name}",
            })
        if items:
            tables_data[table.table_name] = items

    if mode == VECTORIZATION_MODE_FULL or not active_scopes:
        _reset_vector_domain(db, knowledge_base, "table_column")
    else:
        _remove_inactive_vector_scopes(db, knowledge_base, "table_column", active_scopes)

    run_id = str(uuid.uuid4())
    for processed_tables, (table_name, items) in enumerate(tables_data.items(), 1):
        _raise_if_vectorization_cancelled(db, kb_id)
        manifest_map = _load_manifest_map(db, kb_id, "table_column", table_name=table_name)
        changed = []
        for item in items:
            item_key = _manifest_key(kb_id, "table_column", item["field_code"])
            embedding_hash = _hash_text(fingerprint, item["field_value"])
            payload_hash = _hash_text(item["field_value"])
            old = manifest_map.get(item_key)
            if old and old.embedding_hash == embedding_hash and old.payload_hash == payload_hash:
                old.last_seen_run_id = run_id
                continue
            manifest = dict(
                kb_id=kb_id, domain="table_column", table_name=table_name,
                field_code=item["field_code"], item_key=item_key, item_value=item["field_value"],
                embedding_hash=embedding_hash, payload_hash=payload_hash, run_id=run_id,
            )
            changed.append((item, manifest))
        for offset in range(0, len(changed), 100):
            _raise_if_vectorization_cancelled(db, kb_id)
            batch = changed[offset:offset + 100]
            embeddings = _checked_embeddings(embedding_svc, [item["field_value"] for item, _ in batch])
            data = [dict(item, embedding=embeddings[i]) for i, (item, _) in enumerate(batch)]
            _write_vector_batch(db, knowledge_base, "table_column", data, [manifest for _, manifest in batch])
            if offset + 100 < len(changed):
                await asyncio.sleep(DEFAULT_EMBEDDING_BATCH_SLEEP_SECONDS)
        knowledge_base.vector_progress = int(processed_tables / len(tables_data) * 100)
        db.commit()
    knowledge_base.vector_progress = 100
    db.commit()


@_keep_manifest_snapshot
async def _do_table_value_vectorization(db: Session, knowledge_base, collection_name: str, current_step: int, total_steps: int, mode: str = VECTORIZATION_MODE_INCREMENTAL):
    """Synchronize distinct field values with replayable batch checkpoints."""
    kb_id = knowledge_base.id
    space_id = getattr(knowledge_base, "space_id", None)
    _raise_if_vectorization_cancelled(db, kb_id)
    embedding_config = resolve_embedding_config(db, space_id, kb_id=kb_id)
    embedding_svc = EmbeddingService(embedding_config)
    fingerprint = _vector_sync_fingerprint(db, knowledge_base, embedding_config)

    fields = []
    for table in knowledge_base.kb_table_structures:
        for field in table.kb_table_fields:
            field.is_value_vectorized = False
            if field.is_vectorized and field.is_enabled:
                fields.append((table.table_name, field))
    knowledge_base.vector_progress = 0
    db.commit()
    _ensure_vector_collection(db, knowledge_base, embedding_svc.dimension)
    active_scopes = {(table, f"{table}&&{field.field_name}") for table, field in fields}
    if mode == VECTORIZATION_MODE_FULL or not active_scopes:
        _reset_vector_domain(db, knowledge_base, "table_value")
    else:
        _remove_inactive_vector_scopes(db, knowledge_base, "table_value", active_scopes)
    if not fields:
        knowledge_base.vector_progress = 100
        db.commit()
        return

    if not knowledge_base.knowledge_access or not knowledge_base.knowledge_access.data_source:
        raise RuntimeError("No data source found for knowledge base")
    data_source = knowledge_base.knowledge_access.data_source
    source_engine = _create_external_source_engine(data_source)
    run_id = str(uuid.uuid4())
    try:
        for processed_fields, (table_name, field) in enumerate(fields, 1):
            field_name = field.field_name
            field_code = f"{table_name}&&{field_name}"
            try:
                _raise_if_vectorization_cancelled(db, kb_id)
                manifest_map = _load_manifest_map(db, kb_id, "table_value", table_name=table_name, field_code=field_code)
                pending = []

                async def flush_pending():
                    if not pending:
                        return
                    _raise_if_vectorization_cancelled(db, kb_id)
                    embeddings = _checked_embeddings(embedding_svc, [content for _, _, content in pending])
                    data = [dict(item, embedding=embeddings[i]) for i, (item, _, _) in enumerate(pending)]
                    _write_vector_batch(db, knowledge_base, "table_value", data, [manifest for _, manifest, _ in pending])
                    pending.clear()
                    await asyncio.sleep(DEFAULT_EMBEDDING_BATCH_SLEEP_SECONDS)

                for count, value in enumerate(_iter_distinct_values(source_engine, data_source, table_name, field_name), 1):
                    if count % SOURCE_FETCH_MANY_SIZE == 0:
                        _raise_if_vectorization_cancelled(db, kb_id)
                    value_text = _canonical_value(value)
                    content = f"{field.field_alias or field_name}:{value_text}"
                    item_key = _manifest_key(kb_id, "table_value", field_code, value_text)
                    embedding_hash = _hash_text(fingerprint, content)
                    payload_hash = _hash_text(value_text)
                    old = manifest_map.get(item_key)
                    if old and old.embedding_hash == embedding_hash and old.payload_hash == payload_hash:
                        old.last_seen_run_id = run_id
                        continue
                    item = dict(kb_id=kb_id, field_type="table_value", field_table=table_name,
                                field_code=field_code, field_value=value_text)
                    manifest = dict(
                        kb_id=kb_id, domain="table_value", table_name=table_name, field_code=field_code,
                        item_key=item_key, item_value=value_text, embedding_hash=embedding_hash,
                        payload_hash=payload_hash, run_id=run_id,
                    )
                    pending.append((item, manifest, content))
                    if len(pending) >= VALUE_EMBEDDING_BATCH_SIZE:
                        await flush_pending()
                await flush_pending()
                _raise_if_vectorization_cancelled(db, kb_id)
                _delete_stale_vectors(db, knowledge_base, "table_value", [
                    row for row in manifest_map.values() if row.last_seen_run_id != run_id
                ])
                field.is_value_vectorized = True
                knowledge_base.vector_progress = int(processed_fields / len(fields) * 100)
                db.commit()
            except VectorizationCancelled:
                db.rollback()
                raise
            except Exception as exc:
                db.rollback()
                raise RuntimeError(f"Table value vectorization failed for {table_name}.{field_name}: {exc}") from exc
    finally:
        source_engine.dispose()


@_keep_manifest_snapshot
async def _do_knowledge_term_to_es(db: Session, knowledge_base, current_step: int, total_steps: int, mode: str = VECTORIZATION_MODE_INCREMENTAL):
    kb_id = knowledge_base.id
    _raise_if_vectorization_cancelled(db, kb_id)
    config = resolve_es_config(db, getattr(knowledge_base, "space_id", None))
    es_svc = ElasticsearchService(config)
    fingerprint = _es_sync_fingerprint(config)
    _ensure_es_manifest_target(db, kb_id, "es_knowledge", es_svc, f"es_kb{kb_id}_knowledge")
    if mode == VECTORIZATION_MODE_FULL or not knowledge_base.kb_knowledge_terms:
        _reset_es_domain(db, kb_id, "es_knowledge", es_svc.delete_knowledge_index)
    manifest_map = _load_manifest_map(db, kb_id, "es_knowledge")
    run_id = str(uuid.uuid4())
    terms, manifests = [], []
    for kb_term in knowledge_base.kb_knowledge_terms:
        if kb_term.knowledge_term and not kb_term.knowledge_term.is_deleted:
            name, value = kb_term.knowledge_term.term_name, kb_term.knowledge_term.term_value
        else:
            name, value = kb_term.term_name_cache or "", kb_term.term_value_cache or ""
        if not name:
            continue
        term_key = str(getattr(kb_term, "knowledge_term_id", None) or kb_term.id)
        item_key = _manifest_key(kb_id, "es_knowledge", term_key)
        payload_hash = _hash_text(fingerprint, name, value)
        old = manifest_map.get(item_key)
        if old and old.payload_hash == payload_hash:
            old.last_seen_run_id = run_id
            continue
        terms.append(dict(id=ElasticsearchService._doc_id(f"es_kb{kb_id}_knowledge", item_key),
                          term_key=term_key, term_name=name, term_value=value))
        manifests.append(dict(kb_id=kb_id, domain="es_knowledge", item_key=item_key,
                              item_value=name, payload_hash=payload_hash, run_id=run_id))
    if terms:
        _raise_if_vectorization_cancelled(db, kb_id)
        _prepare_manifest_writes(db, manifests)
        if not es_svc.upsert_knowledge_terms(kb_id, terms):
            raise RuntimeError("Failed to index knowledge terms to ES")
        _confirm_manifest_writes(db, manifests)
    _delete_stale_es(db, kb_id, [row for row in manifest_map.values() if row.last_seen_run_id != run_id],
                     f"es_kb{kb_id}_knowledge", es_svc.delete_knowledge_terms_by_ids)
    knowledge_base.vector_progress = 100
    db.commit()


@_keep_manifest_snapshot
async def _do_table_values_to_es(db: Session, knowledge_base, current_step: int, total_steps: int, mode: str = VECTORIZATION_MODE_INCREMENTAL):
    kb_id = knowledge_base.id
    _raise_if_vectorization_cancelled(db, kb_id)
    config = resolve_es_config(db, getattr(knowledge_base, "space_id", None))
    es_svc = ElasticsearchService(config)
    fingerprint = _es_sync_fingerprint(config)
    _ensure_es_manifest_target(db, kb_id, "es_table_value", es_svc, f"es_kb{kb_id}_table_value")
    fields = [(table.table_name, field.field_name)
              for table in knowledge_base.kb_table_structures for field in table.kb_table_fields
              if field.is_vectorized and field.is_enabled]
    active_scopes = {(table, f"{table}&&{field}") for table, field in fields}
    if mode == VECTORIZATION_MODE_FULL or not active_scopes:
        _reset_es_domain(db, kb_id, "es_table_value", es_svc.delete_table_value_index)
    else:
        for table_name, field_code in _manifest_field_scopes(db, kb_id, "es_table_value") - active_scopes:
            rows = list(_load_manifest_map(db, kb_id, "es_table_value", table_name, field_code).values())
            _delete_stale_es(db, kb_id, rows, f"es_kb{kb_id}_table_value", es_svc.delete_table_values_by_ids)
    if not fields:
        knowledge_base.vector_progress = 100
        db.commit()
        return
    knowledge_base.vector_progress = 0
    db.commit()
    if not knowledge_base.knowledge_access or not knowledge_base.knowledge_access.data_source:
        raise RuntimeError("No data source found for knowledge base")
    data_source = knowledge_base.knowledge_access.data_source
    source_engine = _create_external_source_engine(data_source)
    run_id = str(uuid.uuid4())
    try:
        for processed, (table_name, field_name) in enumerate(fields, 1):
            try:
                _raise_if_vectorization_cancelled(db, kb_id)
                field_code = f"{table_name}&&{field_name}"
                manifest_map = _load_manifest_map(db, kb_id, "es_table_value", table_name, field_code)
                pending, manifests = [], []

                def flush_pending():
                    if not pending:
                        return
                    _raise_if_vectorization_cancelled(db, kb_id)
                    _prepare_manifest_writes(db, manifests)
                    if not es_svc.upsert_table_values(kb_id, pending):
                        raise RuntimeError("Failed to upsert table values to ES")
                    _confirm_manifest_writes(db, manifests)
                    pending.clear()
                    manifests.clear()

                for count, value in enumerate(_iter_distinct_values(source_engine, data_source, table_name, field_name), 1):
                    if count % SOURCE_FETCH_MANY_SIZE == 0:
                        _raise_if_vectorization_cancelled(db, kb_id)
                    value_text = _canonical_value(value)
                    item_key = _manifest_key(kb_id, "es_table_value", field_code, value_text)
                    payload_hash = _hash_text(fingerprint, value_text)
                    old = manifest_map.get(item_key)
                    if old and old.payload_hash == payload_hash:
                        old.last_seen_run_id = run_id
                        continue
                    pending.append(dict(id=ElasticsearchService._doc_id(f"es_kb{kb_id}_table_value", item_key),
                                        field_table=table_name, field_code=field_code, field_value=value_text))
                    manifests.append(dict(
                        kb_id=kb_id, domain="es_table_value", table_name=table_name, field_code=field_code,
                        item_key=item_key, item_value=value_text, payload_hash=payload_hash, run_id=run_id,
                    ))
                    if len(pending) >= SOURCE_FETCH_MANY_SIZE:
                        flush_pending()
                flush_pending()
                _delete_stale_es(db, kb_id, [row for row in manifest_map.values() if row.last_seen_run_id != run_id],
                                 f"es_kb{kb_id}_table_value", es_svc.delete_table_values_by_ids)
                knowledge_base.vector_progress = int(processed / len(fields) * 100)
                db.commit()
            except VectorizationCancelled:
                db.rollback()
                raise
            except Exception as exc:
                db.rollback()
                raise RuntimeError(f"ES value synchronization failed for {table_name}.{field_name}: {exc}") from exc
    finally:
        source_engine.dispose()


@_keep_manifest_snapshot
async def _do_sample_library_vectorization(db: Session, knowledge_base, collection_name: str, current_step: int, total_steps: int, mode: str = VECTORIZATION_MODE_INCREMENTAL):
    kb_id = knowledge_base.id
    space_id = getattr(knowledge_base, "space_id", None)
    _raise_if_vectorization_cancelled(db, kb_id)
    config = resolve_embedding_config(db, space_id, kb_id=kb_id)
    embedding_svc = EmbeddingService(config)
    fingerprint = _vector_sync_fingerprint(db, knowledge_base, config)
    _ensure_vector_collection(db, knowledge_base, embedding_svc.dimension)
    if mode == VECTORIZATION_MODE_FULL or not knowledge_base.kb_sample_libraries:
        _reset_vector_domain(db, knowledge_base, "sql_sample")
    else:
        # Previous versions keyed samples by name and wrote an empty field_code.
        # Migrate that namespace once without deleting samples with stable IDs.
        legacy = [row for row in _load_manifest_map(db, kb_id, "sql_sample").values() if not row.field_code]
        if legacy:
            for row in legacy:
                row.embedding_hash = row.payload_hash = None
            db.commit()
            if not VectorStoreService.delete_vectors_by_table_field(
                db, kb_id, "sql_sample", field_code="", space_id=space_id
            ):
                raise RuntimeError("Failed to remove legacy sample vectors")
            for row in legacy:
                db.delete(row)
            db.commit()

    manifest_map = _load_manifest_map(db, kb_id, "sql_sample")
    run_id = str(uuid.uuid4())
    changed = []
    for sample in knowledge_base.kb_sample_libraries:
        sample_id = getattr(sample, "sample_id", None) or sample.id
        field_code = f"sample:{sample_id}"
        item_key = _manifest_key(kb_id, "sql_sample", sample_id)
        embedding_hash = _hash_text(fingerprint, sample.sample_name)
        payload_hash = _hash_text(field_code, sample.sample_name, sample.sample_content)
        old = manifest_map.get(item_key)
        if old and old.embedding_hash == embedding_hash and old.payload_hash == payload_hash:
            old.last_seen_run_id = run_id
            continue
        item = dict(kb_id=kb_id, field_type="sql_sample", field_table="", field_code=field_code,
                    field_value=sample.sample_name, sql_content=sample.sample_content)
        manifest = dict(kb_id=kb_id, domain="sql_sample", table_name="", field_code=field_code,
                        item_key=item_key, item_value=sample.sample_name, embedding_hash=embedding_hash,
                        payload_hash=payload_hash, run_id=run_id)
        changed.append((item, manifest))
    for offset in range(0, len(changed), 100):
        _raise_if_vectorization_cancelled(db, kb_id)
        batch = changed[offset:offset + 100]
        embeddings = _checked_embeddings(embedding_svc, [item["field_value"] for item, _ in batch])
        data = [dict(item, embedding=embeddings[i]) for i, (item, _) in enumerate(batch)]
        _write_vector_batch(db, knowledge_base, "sql_sample", data, [manifest for _, manifest in batch])
        knowledge_base.vector_progress = int(min(offset + 100, len(changed)) / len(changed) * 90)
        db.commit()
        if offset + 100 < len(changed):
            await asyncio.sleep(DEFAULT_EMBEDDING_BATCH_SLEEP_SECONDS)
    _delete_stale_vectors(db, knowledge_base, "sql_sample", [
        row for row in manifest_map.values() if row.last_seen_run_id != run_id
    ])
    knowledge_base.vector_progress = 100
    db.commit()


def vectorize_knowledge_base_service(db: Session, knowledge_base_id: int, request=None, space_id: int = None):
    """
    启动知识库向量化任务

    Args:
        request: 包含 steps 字段，指定要执行的向量化步骤
    """
    knowledge_base = get_knowledge_base_active(db, knowledge_base_id, space_id)
    if not knowledge_base:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    # 检查是否已经在向量化中
    if knowledge_base.vectorization_status in {"processing", "cancelling"}:
        raise HTTPException(status_code=400, detail="Vectorization is already in progress")

    # 获取向量化步骤配置
    import json
    mode = _normalize_vectorization_mode(getattr(request, "mode", None) if request else None)
    if request and request.steps:
        steps_config = {
            "field_vectorization": request.steps.field_vectorization,
            "value_vectorization": request.steps.value_vectorization,
            "table_field_to_es": request.steps.table_field_to_es,
            "knowledge_term_to_es": request.steps.knowledge_term_to_es,
            "sample_library_to_es": request.steps.sample_library_to_es,
        }
    else:
        # 默认执行前两步
        steps_config = {
            "field_vectorization": True,
            "value_vectorization": True,
            "table_field_to_es": False,
            "knowledge_term_to_es": False,
            "sample_library_to_es": False,
        }

    if not any(steps_config.values()):
        raise HTTPException(status_code=400, detail="请至少选择一个向量化步骤")

    needs_vector_store = any(
        steps_config.get(key, False)
        for key in ("field_vectorization", "value_vectorization", "sample_library_to_es")
    )
    if needs_vector_store:
        store = VectorStoreService.resolve_active_store(db, knowledge_base.space_id, kb_id=knowledge_base_id)
        provider = get_vector_store_provider(store.get("provider", "milvus"))
        try:
            if not provider.test_connection(store):
                raise HTTPException(
                    status_code=503,
                    detail=(
                        "向量库连接失败，请检查向量库实例状态、公网访问、IP 白名单、"
                        "VPC 网络以及地址、端口和账号配置"
                    ),
                )
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception("Vector store preflight failed")
            raise HTTPException(status_code=503, detail=f"向量库连接失败: {exc}") from exc

    # Compare and set in the database: concurrent requests may both pass preflight.
    if not _transition_vectorization_status(
        db, knowledge_base_id, ("pending", "completed", "failed", "cancelled"), "processing",
        vector_progress=0,
        vectorization_steps=json.dumps({"mode": mode, "steps": steps_config}),
        current_vectorization_step=None,
    ):
        raise HTTPException(status_code=409, detail="向量化任务正在执行或结束中，请稍后重试")

    # 启动后台线程执行向量化
    def run_vectorization():
        from ....core.resources import close_thread_resources
        try:
            asyncio.run(_do_vectorization(knowledge_base_id, steps_config, mode))
        finally:
            close_thread_resources()

    try:
        thread = threading.Thread(target=run_vectorization)
        thread.daemon = True
        thread.start()
    except Exception as exc:
        _finish_vectorization(db, knowledge_base_id, "failed")
        logger.exception("Failed to start vectorization worker")
        raise HTTPException(status_code=503, detail="向量化任务启动失败，请重试") from exc

    return {
        "message": "Vectorization task started",
        "knowledge_base_id": knowledge_base_id,
        "status": "processing",
        "steps": steps_config
    }


def cancel_vectorization_service(db: Session, knowledge_base_id: int, space_id: int = None):
    """Request a running vectorization task to stop at the next checkpoint."""
    knowledge_base = get_knowledge_base_active(db, knowledge_base_id, space_id)
    if not knowledge_base:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    if knowledge_base.vectorization_status in {"cancelling", "cancelled"}:
        return {
            "message": "Vectorization cancellation already requested",
            "knowledge_base_id": knowledge_base_id,
            "status": knowledge_base.vectorization_status,
        }

    if knowledge_base.vectorization_status != "processing":
        raise HTTPException(status_code=400, detail="当前没有运行中的向量化任务")

    if not _transition_vectorization_status(db, knowledge_base_id, ("processing",), "cancelling"):
        db.refresh(knowledge_base)
        if knowledge_base.vectorization_status not in {"cancelling", "cancelled"}:
            raise HTTPException(status_code=400, detail="当前没有运行中的向量化任务")
        return {
            "message": "Vectorization cancellation already requested",
            "knowledge_base_id": knowledge_base_id,
            "status": knowledge_base.vectorization_status,
        }

    return {
        "message": "Vectorization cancellation requested",
        "knowledge_base_id": knowledge_base_id,
        "status": "cancelling",
    }


def batch_select_table_structures_service(db: Session, knowledge_base_id: int, request, space_id: int = None):
    knowledge_base = get_knowledge_base_active(db, knowledge_base_id, space_id)
    if not knowledge_base:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    # 老格式：request.ids
    if hasattr(request, "ids"):
        table_structures = list_table_structures_by_ids_and_access(
            db,
            request.ids,
            knowledge_base.knowledge_access_id,
        )

        if len(table_structures) != len(request.ids):
            raise HTTPException(
                status_code=400,
                detail="Some table structures not found or not belong to the knowledge access",
            )

        upsert_kb_table_structures_and_fields_old_format(
            db, knowledge_base_id=knowledge_base_id, table_structures=table_structures
        )

    # 新格式：request.fields[{table_id, field_id}]
    elif hasattr(request, "fields"):
        fields_by_table = {}
        for item in request.fields:
            table_id = item["table_id"]
            field_id = item["field_id"]
            fields_by_table.setdefault(table_id, []).append(field_id)

        table_ids = list(fields_by_table.keys())
        table_structures = list_table_structures_by_ids_and_access(
            db,
            table_ids,
            knowledge_base.knowledge_access_id,
        )

        if len(table_structures) != len(table_ids):
            raise HTTPException(
                status_code=400,
                detail="Some table structures not found or not belong to the knowledge access",
            )

        all_field_ids = []
        for field_ids in fields_by_table.values():
            all_field_ids.extend(field_ids)

        table_fields = list_table_fields_by_ids_and_table_ids(
            db,
            all_field_ids,
            table_ids,
        )

        if len(table_fields) != len(all_field_ids):
            raise HTTPException(
                status_code=400,
                detail="Some table fields not found or not belong to the selected tables",
            )

        field_map = {field.id: field for field in table_fields}
        table_map = {table.id: table for table in table_structures}

        upsert_kb_table_structures_and_fields_new_format(
            db,
            knowledge_base_id=knowledge_base_id,
            fields_by_table=fields_by_table,
            table_map=table_map,
            field_map=field_map,
        )

    knowledge_base.table_count = count_kb_table_structures(db, knowledge_base_id)
    db.commit()
    db.refresh(knowledge_base)
    return knowledge_base


def batch_select_knowledge_terms_service(db: Session, knowledge_base_id: int, request, space_id: int = None):
    knowledge_base = get_knowledge_base_active(db, knowledge_base_id, space_id)
    if not knowledge_base:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    knowledge_terms = list_knowledge_terms_by_ids_and_access(
        db,
        request.ids,
        knowledge_base.knowledge_access_id,
    )

    if len(knowledge_terms) != len(request.ids):
        raise HTTPException(
            status_code=400,
            detail="Some knowledge terms not found or not belong to the knowledge access",
        )

    upsert_kb_knowledge_terms(db, knowledge_base_id, knowledge_terms)

    # 标记知识词条脏数据
    knowledge_base.knowledge_term_dirty = True

    db.commit()
    db.refresh(knowledge_base)
    return knowledge_base


def batch_select_sample_libraries_service(db: Session, knowledge_base_id: int, request, space_id: int = None):
    knowledge_base = get_knowledge_base_active(db, knowledge_base_id, space_id)
    if not knowledge_base:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    sample_libraries = list_sample_libraries_by_ids_and_access(
        db,
        request.ids,
        knowledge_base.knowledge_access_id,
    )

    if len(sample_libraries) != len(request.ids):
        raise HTTPException(
            status_code=400,
            detail="Some sample libraries not found or not belong to the knowledge access",
        )

    upsert_kb_sample_libraries(db, knowledge_base_id, sample_libraries)

    # 标记样例库脏数据
    knowledge_base.sample_library_dirty = True

    db.commit()
    db.refresh(knowledge_base)
    return knowledge_base


def clone_knowledge_base_service(db: Session, knowledge_base_id: int, space_id: int = None):
    original = get_knowledge_base_active(db, knowledge_base_id, space_id)
    if not original:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    cloned = models.KnowledgeBase(
        name=f"{original.name}_clone",
        description=original.description,
        knowledge_access_id=original.knowledge_access_id,
        status=original.status,
        space_id=space_id or original.space_id,
    )
    db.add(cloned)
    db.flush()  # 获取 cloned.id，供写入 kb_* 关联表

    clone_knowledge_base_relationships(db, original, cloned)

    cloned.table_count = original.table_count
    db.commit()
    db.refresh(cloned)
    return cloned


def update_kb_table_structure_service(db: Session, kb_table_structure_id: int, kb_table_structure_update, space_id: int = None):
    db_kb_table_structure = get_kb_table_structure_by_id(db, kb_table_structure_id, space_id)
    if db_kb_table_structure is None:
        raise HTTPException(status_code=404, detail="KB table structure not found")

    update_data = kb_table_structure_update.dict(exclude_unset=True)
    apply_kb_table_structure_update(db, db_kb_table_structure, update_data)

    db.commit()
    db.refresh(db_kb_table_structure)
    return db_kb_table_structure


def delete_kb_table_structure_service(db: Session, kb_table_structure_id: int, space_id: int = None):
    knowledge_base_id = delete_kb_table_structure_by_id(db, kb_table_structure_id, space_id)
    if knowledge_base_id is None:
        raise HTTPException(status_code=404, detail="KB table structure not found")

    set_knowledge_base_table_count_by_id(db, knowledge_base_id)
    db.commit()
    return {"message": "KB table structure deleted successfully"}


def update_kb_table_field_service(db: Session, kb_table_field_id: int, kb_table_field_update):
    db_kb_table_field = get_kb_table_field_by_id(db, kb_table_field_id)
    if db_kb_table_field is None:
        raise HTTPException(status_code=404, detail="KB table field not found")

    update_data = kb_table_field_update.dict(exclude_unset=True)
    apply_kb_table_field_update(db_kb_table_field, update_data)

    db.commit()
    db.refresh(db_kb_table_field)
    return db_kb_table_field


def delete_kb_table_field_service(db: Session, kb_table_field_id: int):
    deleted = delete_kb_table_field_by_id(db, kb_table_field_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="KB table field not found")

    db.commit()
    return {"message": "KB table field deleted successfully"}


def delete_kb_knowledge_term_service(db: Session, kb_knowledge_term_id: int):
    # 先获取关联的知识库ID
    from ....repositories.knowledge.knowledge_base.repository import get_kb_knowledge_term_by_id
    kb_term = get_kb_knowledge_term_by_id(db, kb_knowledge_term_id)
    if not kb_term:
        raise HTTPException(status_code=404, detail="KB knowledge term not found")

    knowledge_base_id = kb_term.knowledge_base_id
    deleted = delete_kb_knowledge_term_by_id(db, kb_knowledge_term_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="KB knowledge term not found")

    # 标记知识词条脏数据
    knowledge_base = get_knowledge_base_active(db, knowledge_base_id)
    if knowledge_base:
        knowledge_base.knowledge_term_dirty = True

    db.commit()
    return {"message": "KB knowledge term deleted successfully"}


def delete_kb_sample_library_service(db: Session, kb_sample_library_id: int):
    # 先获取关联的知识库ID
    from ....repositories.knowledge.knowledge_base.repository import get_kb_sample_library_by_id
    kb_sample = get_kb_sample_library_by_id(db, kb_sample_library_id)
    if not kb_sample:
        raise HTTPException(status_code=404, detail="KB sample library not found")

    knowledge_base_id = kb_sample.knowledge_base_id
    deleted = delete_kb_sample_library_by_id(db, kb_sample_library_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="KB sample library not found")

    # 标记样例库脏数据
    knowledge_base = get_knowledge_base_active(db, knowledge_base_id)
    if knowledge_base:
        knowledge_base.sample_library_dirty = True

    db.commit()
    return {"message": "KB sample library deleted successfully"}


_DML_KEYWORD_PATTERN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|TRUNCATE|ALTER|CREATE|RENAME|GRANT|REVOKE"
    r"|LOAD\s+DATA|INTO\s+OUTFILE|INTO\s+DUMPFILE|CALL|EXEC|EXECUTE)\b",
    re.IGNORECASE,
)


def _strip_sql_comments(sql: str) -> str:
    """移除块注释与行注释，便于检测关键字（简化实现，不处理字符串内的注释符号）。"""
    s = sql
    while True:
        start = s.find("/*")
        if start == -1:
            break
        end = s.find("*/", start + 2)
        if end == -1:
            s = s[:start]
            break
        s = s[:start] + " " + s[end + 2 :]
    lines = []
    for line in s.split("\n"):
        if "--" in line:
            line = line[: line.index("--")]
        lines.append(line)
    return "\n".join(lines)


def _mask_sql_string_literals(sql: str) -> str:
    """将单/双引号字符串替换为空格，避免字面量中的词触发 DML 误判。"""
    result = []
    i, n = 0, len(sql)
    while i < n:
        c = sql[i]
        if c == "'":
            result.append(" ")
            i += 1
            while i < n:
                if sql[i] == "'" and i + 1 < n and sql[i + 1] == "'":
                    i += 2
                    continue
                if sql[i] == "\\" and i + 1 < n:
                    i += 2
                    continue
                if sql[i] == "'":
                    i += 1
                    break
                i += 1
            continue
        if c == '"':
            result.append(" ")
            i += 1
            while i < n:
                if sql[i] == "\\" and i + 1 < n:
                    i += 2
                    continue
                if sql[i] == '"':
                    i += 1
                    break
                i += 1
            continue
        result.append(c)
        i += 1
    return "".join(result)


def _sql_contains_forbidden_dml(sql: str) -> bool:
    prepared = _mask_sql_string_literals(_strip_sql_comments(sql))
    return _DML_KEYWORD_PATTERN.search(prepared) is not None


def _serialize_sql_cell(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    # Preserve integers outside JavaScript's exact range in JSON clients.
    if isinstance(value, int) and abs(value) > 9007199254740991:
        return str(value)
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def execute_knowledge_base_sql_service(db: Session, knowledge_base_id: int, sql: str, space_id: int = None):
    """
    根据知识库 ID 解析关联数据源，在对应数据库上只读执行 SQL。
    若语句含 INSERT/UPDATE/DELETE 关键字则拒绝执行。
    """
    raw = (sql or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="SQL 不能为空")

    if _sql_contains_forbidden_dml(raw):
        raise HTTPException(status_code=400, detail="只允许查询，请修改 SQL。")

    knowledge_base = get_knowledge_base_detail(db, knowledge_base_id, space_id)
    if knowledge_base is None:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    if not knowledge_base.knowledge_access:
        raise HTTPException(status_code=400, detail="知识库未关联知识接入，无法解析数据源")

    data_source = knowledge_base.knowledge_access.data_source
    if not data_source or data_source.is_deleted:
        raise HTTPException(status_code=400, detail="数据源不存在或已删除")

    from ..sql_runtime import bounded_query, query_timeout_seconds, result_row_limit, result_byte_limit
    dialect = 'postgres' if _is_postgresql_source(data_source) else 'mysql'
    bounded = bounded_query(raw, dialect)

    engine = _create_external_source_engine(data_source, True)
    from ....core.execution import release_read_connection
    release_read_connection(db)
    deadline = time.monotonic() + query_timeout_seconds()

    try:
        with engine.connect() as conn:
            timeout_ms = query_timeout_seconds() * 1000
            if engine.dialect.name == 'postgresql':
                conn.execute(text('SET TRANSACTION READ ONLY'))
                conn.execute(text("SELECT set_config('statement_timeout', :timeout, true)"), {'timeout': str(timeout_ms)})
            elif engine.dialect.name == 'mysql':
                conn.execute(text('SET SESSION MAX_EXECUTION_TIME = :timeout'), {'timeout': timeout_ms})
                conn.execute(text('SET SESSION TRANSACTION READ ONLY'))
            result = conn.execution_options(stream_results=True, max_row_buffer=20).execute(text(bounded))
            try:
                if not result.returns_rows:
                    return KnowledgeBaseExecuteSqlResponse(columns=[], rows=[], row_count=0)
                columns = list(result.keys())
                rows_out = []
                size = 0
                for row in result.mappings():
                    if time.monotonic() > deadline:
                        raise HTTPException(504, 'SQL 查询超时，请缩小查询范围后重试')
                    if len(rows_out) >= result_row_limit():
                        raise HTTPException(413, 'SQL 结果超过行数上限，请增加筛选条件或聚合后查询')
                    item = {k: _serialize_sql_cell(v) for k, v in row.items()}
                    size += len(json.dumps(item, ensure_ascii=False, default=str).encode('utf-8'))
                    if size > result_byte_limit():
                        raise HTTPException(413, 'SQL 结果超过容量上限，请减少返回字段或缩小查询范围')
                    rows_out.append(item)
                return KnowledgeBaseExecuteSqlResponse(
                    columns=columns,
                    rows=rows_out,
                    row_count=len(rows_out),
                )
            finally:
                result.close()
    except HTTPException:
        raise
    except Exception as e:
        original = getattr(e, 'orig', e)
        args = getattr(original, 'args', ())
        code = getattr(original, 'errno', None) or (args[0] if args else None)
        if getattr(original, 'pgcode', None) == '57014' or code == 3024:
            logger.warning('知识库 SQL 查询超时: kb_id=%s', knowledge_base_id)
            raise HTTPException(504, 'SQL 查询超时，请缩小查询范围后重试') from e
        logger.exception("执行知识库 SQL 失败: kb_id=%s", knowledge_base_id)
        raise HTTPException(status_code=400, detail="SQL 执行失败，请检查语句和数据源连接配置") from e
