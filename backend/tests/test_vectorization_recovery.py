import asyncio
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy.exc import OperationalError

from app.services.knowledge.knowledge_base import service


class SourceEngine:
    def __init__(self, values, fail_once=False):
        self.values = values
        self.active = False
        self.result_open = False
        self.connections = 0
        self.disposed = False
        self.fail_once = fail_once
        self.fail_reads = 0

    def connect(self):
        self.connections += 1
        engine = self

        class Connection:
            def __enter__(self):
                engine.active = True
                self.position = 0
                return self

            def __exit__(self, *args):
                engine.active = False

            def execution_options(self, **kwargs):
                return self

            def execute(self, query):
                engine.result_open = True
                return self

            def fetchmany(self, size):
                if engine.fail_reads:
                    engine.fail_reads -= 1
                    raise OperationalError(None, None, OSError("connection closed"), connection_invalidated=True)
                if engine.fail_once and self.position:
                    engine.fail_once = False
                    raise OperationalError(None, None, OSError("connection closed"), connection_invalidated=True)
                rows = [(value,) for value in engine.values[self.position:self.position + size]]
                self.position += len(rows)
                return rows

            def close(self):
                engine.result_open = False

        return Connection()

    def dispose(self):
        self.disposed = True


def test_source_connection_is_released_before_consuming_values():
    values = [None, "上海\n医院\"A\"", Decimal("1.20"), date(2026, 10, 19)] + list(range(5001))
    engine = SourceEngine(values)
    iterator = service._iter_distinct_values(engine, SimpleNamespace(database_type="postgresql"), "sales", "hospital")

    assert next(iterator) == "上海\n医院\"A\""
    assert engine.active is False
    assert engine.result_open is False
    assert list(iterator) == ["1.20", "2026-10-19"] + [str(value) for value in range(5001)]


def test_invalidated_source_connection_is_retried_without_duplicate_values():
    engine = SourceEngine(["上海", "北京", "广州"], fail_once=True)

    values = list(service._iter_distinct_values(
        engine, SimpleNamespace(database_type="postgresql"), "sales", "city", fetch_size=2,
    ))

    assert values == ["上海", "北京", "广州"]
    assert engine.connections == 2
    assert engine.active is False
    assert engine.result_open is False


def test_source_retry_exhaustion_releases_connections_and_propagates_error():
    engine = SourceEngine(["上海"])
    engine.fail_reads = 2

    with pytest.raises(OperationalError):
        list(service._iter_distinct_values(engine, SimpleNamespace(database_type="postgresql"), "sales", "city"))

    assert engine.connections == 2
    assert engine.active is False
    assert engine.result_open is False


@pytest.fixture
def value_job(monkeypatch):
    fields = [SimpleNamespace(
        id=i, field_name=name, field_alias=name, is_vectorized=True,
        is_enabled=True, is_value_vectorized=True,
    ) for i, name in enumerate(["city", "hospital", "grade"], 1)]
    kb = SimpleNamespace(
        id=44, space_id=1, vector_progress=100,
        kb_table_structures=[SimpleNamespace(table_name="sales", kb_table_fields=fields)],
        knowledge_access=SimpleNamespace(data_source=SimpleNamespace(
            database_type="postgresql", host="test-db", port=5432, default_database="test",
        )),
    )
    state = SimpleNamespace(rollbacks=0, embeddings=[], inserts=[], fail_field=None, fail_insert=False)
    engine = SourceEngine(["上海", "北京"])

    class Db:
        def commit(self):
            pass

        def rollback(self):
            state.rollbacks += 1

        def query(self, model):
            return self

        def filter_by(self, **kwargs):
            self.field_id = kwargs["id"]
            return self

        def first(self):
            return next(field for field in fields if field.id == self.field_id)

    class Embeddings:
        dimension = 3

        def __init__(self, config):
            pass

        def get_embeddings(self, texts):
            assert engine.active is False, "embedding must run after releasing the source transaction"
            assert engine.result_open is False
            state.embeddings.extend(texts)
            if any(text.startswith(f"{state.fail_field}:") for text in texts):
                raise RuntimeError("embedding unavailable")
            return [[0.1, 0.2, 0.3] for _ in texts]

    def insert(db, kb_id, items, space_id):
        state.inserts.extend(items)
        return not state.fail_insert

    monkeypatch.setattr(service, "EmbeddingService", Embeddings)
    monkeypatch.setattr(service, "resolve_embedding_config", lambda *args, **kwargs: {})
    monkeypatch.setattr(service, "_raise_if_vectorization_cancelled", lambda *args: None)
    monkeypatch.setattr(service, "_create_external_source_engine", lambda source: engine)
    monkeypatch.setattr(service, "_load_manifest_map", lambda *args, **kwargs: {})
    monkeypatch.setattr(service, "_manifest_rows_for_batch", lambda *args, **kwargs: {})
    monkeypatch.setattr(service, "_delete_manifest_scope", lambda *args, **kwargs: None)
    monkeypatch.setattr(service, "_invalidate_manifest_scope", lambda *args, **kwargs: None)
    monkeypatch.setattr(service, "_manifest_field_scopes", lambda *args, **kwargs: set())
    monkeypatch.setattr(service, "_upsert_manifest", lambda *args, **kwargs: None)
    monkeypatch.setattr(service.VectorStoreService, "resolve_active_store", lambda *args, **kwargs: {})
    monkeypatch.setattr(service.VectorStoreService, "collection_exists_for_kb", lambda *args, **kwargs: True)
    monkeypatch.setattr(service.VectorStoreService, "create_collection_for_kb", lambda *args, **kwargs: True)
    monkeypatch.setattr(service.VectorStoreService, "delete_vectors_by_table_field", lambda *args, **kwargs: True)
    monkeypatch.setattr(service.VectorStoreService, "delete_vector_items", lambda *args, **kwargs: True)
    monkeypatch.setattr(service.VectorStoreService, "insert_vectors", insert)
    monkeypatch.setattr(service, "DEFAULT_EMBEDDING_BATCH_SLEEP_SECONDS", 0)

    return SimpleNamespace(kb=kb, fields=fields, db=Db(), engine=engine, state=state)


def test_value_job_completes_all_fields_after_source_connections_close(value_job):
    job = value_job
    asyncio.run(service._do_table_value_vectorization(job.db, job.kb, "v_kb44", 1, 1))

    assert all(field.is_value_vectorized for field in job.fields)
    assert job.kb.vector_progress == 100
    assert len(job.state.inserts) == 6
    assert job.engine.connections == 3
    assert job.engine.disposed is True


def test_value_job_rolls_back_stops_and_clears_previous_completion_on_failure(value_job):
    job = value_job
    job.state.fail_field = "hospital"

    with pytest.raises(RuntimeError, match="hospital"):
        asyncio.run(service._do_table_value_vectorization(job.db, job.kb, "v_kb44", 1, 1))

    assert [field.is_value_vectorized for field in job.fields] == [True, False, False]
    assert job.kb.vector_progress == 33
    assert job.state.rollbacks == 1
    assert not any(text.startswith("grade:") for text in job.state.embeddings)
    assert job.engine.disposed is True


def test_vector_write_failure_is_not_reported_as_complete(value_job):
    job = value_job
    job.state.fail_insert = True

    with pytest.raises(RuntimeError, match="city"):
        asyncio.run(service._do_table_value_vectorization(job.db, job.kb, "v_kb44", 1, 1))

    assert not any(field.is_value_vectorized for field in job.fields)
    assert job.kb.vector_progress == 0
    assert job.state.rollbacks == 1


def test_failed_full_rebuild_does_not_restore_manifests_for_deleted_vectors(value_job, monkeypatch):
    job = value_job
    persisted = {"manifest": True}
    pending = {"delete": False}

    def delete_manifest(*args, **kwargs):
        pending["delete"] = True

    def commit():
        if pending["delete"]:
            persisted["manifest"] = False
        pending["delete"] = False

    job.db.commit = commit
    job.db.rollback = lambda: pending.update(delete=False)
    job.state.fail_field = "city"
    monkeypatch.setattr(service, "_delete_manifest_scope", delete_manifest)

    with pytest.raises(RuntimeError, match="city"):
        asyncio.run(service._do_table_value_vectorization(job.db, job.kb, "v_kb44", 1, 1, "full"))

    assert persisted["manifest"] is False


@pytest.mark.parametrize("fail_write", [False, True])
def test_es_values_release_source_connection_and_propagate_failures(value_job, monkeypatch, fail_write):
    job = value_job

    class Es:
        def __init__(self, config):
            pass

        def index_exists(self, index_name):
            return True

        @staticmethod
        def _doc_id(index, key):
            return key

        def upsert_table_values(self, kb_id, values):
            assert job.engine.active is False
            assert job.engine.result_open is False
            job.state.inserts.extend(values)
            return not fail_write

        def delete_table_values_by_ids(self, *args):
            return True

    monkeypatch.setattr(service, "ElasticsearchService", Es)
    monkeypatch.setattr(service, "resolve_es_config", lambda *args: {})
    if fail_write:
        with pytest.raises(RuntimeError, match="city"):
            asyncio.run(service._do_table_values_to_es(job.db, job.kb, 1, 1))
        assert job.kb.vector_progress == 0
        assert job.state.rollbacks == 1
    else:
        asyncio.run(service._do_table_values_to_es(job.db, job.kb, 1, 1))
        assert job.kb.vector_progress == 100
        assert len(job.state.inserts) == 6
    assert job.engine.disposed is True


def test_failed_value_step_sets_job_failed_instead_of_completed(monkeypatch):
    from app.core import database

    kb = SimpleNamespace(id=44, vectorization_status="processing", vector_progress=0)
    db = SimpleNamespace(commit=lambda: None, close=lambda: None)

    async def fail_step(*args):
        kb.vector_progress = 33
        raise RuntimeError("hospital failed")

    monkeypatch.setattr(database, "SessionLocal", lambda: db)
    monkeypatch.setattr(service, "get_knowledge_base_active", lambda *args: kb)
    monkeypatch.setattr(service, "get_knowledge_base_detail", lambda *args: kb)
    monkeypatch.setattr(service, "_raise_if_vectorization_cancelled", lambda *args: None)
    monkeypatch.setattr(service, "_do_table_value_vectorization", fail_step)
    monkeypatch.setattr(service, "_finish_vectorization", lambda db, kb_id, status: setattr(kb, "vectorization_status", status))

    asyncio.run(service._do_vectorization(44, {"value_vectorization": True}))

    assert kb.vectorization_status == "failed"
    assert kb.vector_progress == 33
    assert kb.current_vectorization_step == "value_vectorization"
