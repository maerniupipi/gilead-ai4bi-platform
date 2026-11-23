"""Protect batch checkpoints from per-item ORM refreshes and session leakage."""
import pytest
from sqlalchemy import event

from app.services.knowledge.knowledge_base import service
from tests.test_vectorization_sync import DOMAINS, sync_job


@pytest.mark.parametrize("domain", ["table_value", "es_table_value"])
def test_mixed_incremental_batches_keep_manifest_queries_bounded(sync_job, monkeypatch, domain):
    job = sync_job
    job.kb.kb_table_structures = [job.kb.kb_table_structures[0]]
    job.kb.kb_table_structures[0].kb_table_fields = [job.kb.kb_table_structures[0].kb_table_fields[0]]
    job.source.values[("sales", "city")] = [str(i) for i in range(100)]
    monkeypatch.setattr(service, "VALUE_EMBEDDING_BATCH_SIZE", 2)
    monkeypatch.setattr(service, "SOURCE_FETCH_MANY_SIZE", 2)
    job.run(domain, "full")
    job.state.embeddings.clear()

    statements = []

    def record(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("SELECT") and "kb_vector_manifest" in statement:
            statements.append(statement)

    event.listen(job.db.get_bind(), "before_cursor_execute", record)
    expected_values = ["new1", "new2"] + [str(i) for i in range(2, 100)]
    job.source.values[("sales", "city")] = expected_values
    try:
        job.run(domain, "incremental")
    finally:
        event.remove(job.db.get_bind(), "before_cursor_execute", record)

    # The first changed batch commits before 98 unchanged entries are scanned.
    # Expiring the snapshot here previously generated over 100 SELECTs.
    assert len(statements) <= 8
    assert {row["field_value"] for row in job.rows(domain)} == set(expected_values)
    assert len(job.rows(domain)) == 100
    if domain == "table_value":
        assert len(job.state.embeddings) == 2
    assert job.db.expire_on_commit is True


@pytest.mark.parametrize("domain", DOMAINS)
@pytest.mark.parametrize("original_expiration", [True, False])
def test_checkpoint_failure_preserves_pending_rows_and_restores_session(
    sync_job, monkeypatch, domain, original_expiration,
):
    job = sync_job
    job.db.expire_on_commit = original_expiration
    prepare = service._prepare_manifest_writes

    def fail_after_checkpoint(db, manifests):
        assert db.expire_on_commit is False
        prepare(db, manifests)
        raise RuntimeError("interrupted after durable checkpoint")

    monkeypatch.setattr(service, "_prepare_manifest_writes", fail_after_checkpoint)
    with pytest.raises(RuntimeError, match="interrupted after durable checkpoint"):
        job.run(domain)

    assert job.db.expire_on_commit is original_expiration
    job.db.rollback()
    pending = job.manifests(domain)
    assert pending
    assert all(row.embedding_hash is None and row.payload_hash is None for row in pending)
    assert not job.rows(domain)


def test_cancellation_restores_session_expiration(sync_job, monkeypatch):
    job = sync_job

    def cancel(*args):
        raise service.VectorizationCancelled("cancelled at checkpoint")

    monkeypatch.setattr(service, "_raise_if_vectorization_cancelled", cancel)
    with pytest.raises(service.VectorizationCancelled):
        job.run("table_value")
    assert job.db.expire_on_commit is True
