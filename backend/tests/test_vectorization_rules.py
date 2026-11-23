import asyncio
from types import SimpleNamespace

import pytest

from app.services.knowledge.knowledge_base import service
from app.services.knowledge import vector_service


def test_distinct_values_sql_streams_without_limit():
    data_source = SimpleNamespace(database_type="mysql")

    sql = service._distinct_values_sql(data_source, "sales", "city")

    assert "SELECT DISTINCT `city` FROM `sales`" in sql
    assert "WHERE `city` IS NOT NULL" in sql
    assert "ORDER BY `city`" in sql
    assert "LIMIT 1000" not in sql


def test_vectorization_mode_validation():
    assert service._normalize_vectorization_mode(None) == "incremental"
    assert service._normalize_vectorization_mode("FULL") == "full"
    assert service._normalize_vectorization_mode(" incremental ") == "incremental"

    with pytest.raises(Exception):
        service._normalize_vectorization_mode("partial")


def test_manifest_key_and_hash_are_stable():
    key1 = service._manifest_key(7, "table_value", "orders&&city", "上海")
    key2 = service._manifest_key(7, "table_value", "orders&&city", "上海")
    key3 = service._manifest_key(7, "table_value", "orders&&city", "北京")

    assert key1 == key2
    assert key1 != key3
    assert service._hash_text("城市", "上海") == service._hash_text("城市", "上海")
    assert service._hash_text("城市", "上海") != service._hash_text("城市", "北京")


def test_value_vectorization_batch_size_is_1000():
    assert service.VALUE_EMBEDDING_BATCH_SIZE == 1000
    assert service.DEFAULT_EMBEDDING_BATCH_SLEEP_SECONDS == 0.5


def test_cancel_vectorization_service_requests_cancellation(monkeypatch):
    kb = SimpleNamespace(
        id=37,
        vectorization_status="processing",
        current_vectorization_step="value_vectorization",
    )
    transitions = []

    def transition(db, kb_id, expected, status, **values):
        transitions.append((kb_id, expected, status, values))
        return True

    monkeypatch.setattr(service, "get_knowledge_base_active", lambda db, kb_id, space_id=None: kb)
    monkeypatch.setattr(service, "_transition_vectorization_status", transition)

    result = service.cancel_vectorization_service(object(), 37, space_id=1)

    assert result["status"] == "cancelling"
    assert transitions == [(37, ("processing",), "cancelling", {})]


@pytest.mark.parametrize("status", ["cancelling", "cancelled"])
def test_cancel_checkpoint_raises_when_status_is_cancelled(status):
    class FakeQuery:
        def filter(self, *args):
            return self

        def scalar(self):
            return status

    class FakeDb:
        def query(self, *args):
            return FakeQuery()

    with pytest.raises(service.VectorizationCancelled):
        service._raise_if_vectorization_cancelled(FakeDb(), 37)


def test_cancelled_status_is_not_overwritten_when_background_task_starts(monkeypatch):
    from app.core import database

    kb = SimpleNamespace(
        id=38,
        vectorization_status="cancelled",
        vector_progress=77,
        vector_collection_name=None,
    )
    closed = {"value": False}
    commits = {"count": 0}

    class FakeDb:
        def commit(self):
            commits["count"] += 1

        def close(self):
            closed["value"] = True

    monkeypatch.setattr(database, "SessionLocal", lambda: FakeDb())
    monkeypatch.setattr(service, "get_knowledge_base_active", lambda db, kb_id, space_id=None: kb)

    asyncio.run(service._do_vectorization(38, {"field_vectorization": False}, "incremental"))

    assert kb.vectorization_status == "cancelled"
    assert kb.vector_progress == 77
    assert commits["count"] == 0
    assert closed["value"] is True


def test_milvus_incremental_delete_is_batched(monkeypatch):
    deleted = []

    class FakeCollection:
        def __init__(self, name, using=None):
            self.name = name

        def load(self):
            return None

        def delete(self, expr, timeout=None):
            deleted.append((expr, timeout))

        def flush(self, timeout=None):
            deleted.append(("flush", timeout))

    monkeypatch.setattr(vector_service.connections, '_fetch_handler',
                        lambda _: SimpleNamespace(has_collection=lambda *args, **kwargs: True))
    monkeypatch.setattr(vector_service, "Collection", FakeCollection)

    svc = vector_service.MilvusService({"host": "test-milvus", "port": "19530"})
    svc.connect = lambda: None

    items = [
        {"field_table": "sales", "field_code": "sales&&city"},
        {"field_table": "sales", "field_code": "sales&&amount"},
    ]
    assert svc.delete_items("v_kb1", "table_column", items)
    assert len(deleted) == 2
    assert "sales&&city" in deleted[0][0]
    assert "sales&&amount" in deleted[0][0]
    assert " || " in deleted[0][0]
    assert deleted[0][1] == vector_service.MILVUS_OPERATION_TIMEOUT_SECONDS
    assert deleted[1] == ("flush", vector_service.MILVUS_OPERATION_TIMEOUT_SECONDS)


def test_field_vectorization_batches_vector_store_calls_per_table(monkeypatch):
    calls = {
        "delete": 0,
        "insert": 0,
        "insert_lengths": [],
    }

    class FakeEmbeddingService:
        dimension = 3

        def __init__(self, config):
            self.config = config

        def get_embeddings(self, texts):
            return [[0.1, 0.2, 0.3] for _ in texts]

    class FakeVectorStoreService:
        @staticmethod
        def resolve_active_store(*args, **kwargs):
            return {}

        @staticmethod
        def collection_exists_for_kb(*args, **kwargs):
            return True

        @staticmethod
        def create_collection_for_kb(*args, **kwargs):
            return True

        @staticmethod
        def delete_vectors_by_table_field(*args, **kwargs):
            calls["delete"] += 1
            return True

        @staticmethod
        def delete_vector_items(*args, **kwargs):
            return True

        @staticmethod
        def insert_vectors(db, kb_id, data, space_id):
            calls["insert"] += 1
            calls["insert_lengths"].append(len(data))
            return True

    class FakeDb:
        def commit(self):
            pass

    fields = [
        SimpleNamespace(field_name="city", field_alias="城市", is_enabled=True),
        SimpleNamespace(field_name="amount", field_alias="金额", is_enabled=True),
        SimpleNamespace(field_name="disabled", field_alias="禁用", is_enabled=False),
    ]
    table = SimpleNamespace(
        table_name="sales",
        table_alias="销售",
        kb_table_fields=fields,
    )
    kb = SimpleNamespace(id=7, space_id=1, kb_table_structures=[table], vector_progress=0)

    monkeypatch.setattr(service, "resolve_embedding_config", lambda db, space_id, kb_id=None: {})
    monkeypatch.setattr(service, "EmbeddingService", FakeEmbeddingService)
    monkeypatch.setattr(service, "VectorStoreService", FakeVectorStoreService)
    monkeypatch.setattr(service, "_raise_if_vectorization_cancelled", lambda db, kb_id: None)
    monkeypatch.setattr(service, "_delete_manifest_scope", lambda *args, **kwargs: None)
    monkeypatch.setattr(service, "_invalidate_manifest_scope", lambda *args, **kwargs: None)
    monkeypatch.setattr(service, "_load_manifest_map", lambda *args, **kwargs: {})
    monkeypatch.setattr(service, "_manifest_rows_for_batch", lambda *args, **kwargs: {})
    monkeypatch.setattr(service, "_upsert_manifest", lambda *args, **kwargs: None)

    asyncio.run(
        service._do_field_vectorization(
            FakeDb(),
            kb,
            "v_kb7",
            current_step=1,
            total_steps=1,
            mode=service.VECTORIZATION_MODE_FULL,
        )
    )

    assert calls["delete"] == 1
    assert calls["insert"] == 1
    assert calls["insert_lengths"] == [2]
    assert kb.vector_progress == 100
