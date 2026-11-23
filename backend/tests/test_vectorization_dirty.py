"""Dirty flags must survive source edits made during an indexing write."""
import asyncio

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.services.knowledge.knowledge_base import service
from tests.test_vectorization_sync import sync_job


@pytest.fixture
def dirty_job(sync_job, tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'dirty.sqlite'}")
    for model in (
        models.KnowledgeBase, models.KnowledgeTerm, models.SampleLibrary,
        models.KbKnowledgeTerm, models.KbSampleLibrary, models.KbVectorManifest,
    ):
        model.__table__.create(engine)
    sessions = sessionmaker(bind=engine, autoflush=False)
    with sessions() as db:
        kb = models.KnowledgeBase(
            id=71, space_id=3, name="local dirty test", knowledge_access_id=1,
            knowledge_term_dirty=True, sample_library_dirty=True,
            kb_knowledge_terms=[models.KbKnowledgeTerm(
                id=201, knowledge_term_id=10,
                knowledge_term=models.KnowledgeTerm(
                    id=10, knowledge_access_id=1, term_name="销售额", term_value="旧定义",
                ),
            )],
            kb_sample_libraries=[models.KbSampleLibrary(
                id=202, sample_id=20,
                sample_library=models.SampleLibrary(
                    id=20, knowledge_access_id=1, sample_name="查询销售额", sql_content="SELECT 1",
                ),
            )],
        )
        db.add(kb)
        db.commit()

    with sessions() as db:
        kb = db.get(models.KnowledgeBase, 71)

        def run(domain, mode="incremental"):
            if domain == "es_knowledge":
                asyncio.run(service._do_knowledge_term_to_es(db, kb, 1, 1, mode))
            else:
                asyncio.run(service._do_sample_library_vectorization(db, kb, "v_kb71", 1, 1, mode))

        yield sync_job, sessions, db, kb, run
    engine.dispose()


def flag(domain):
    return "knowledge_term_dirty" if domain == "es_knowledge" else "sample_library_dirty"


def edit_source(sessions, domain):
    with sessions() as writer:
        kb = writer.get(models.KnowledgeBase, 71)
        setattr(kb, flag(domain), True)
        if domain == "es_knowledge":
            writer.get(models.KnowledgeTerm, 10).term_value = "新定义"
        else:
            writer.get(models.SampleLibrary, 20).sql_content = "SELECT 2"
        writer.commit()


def assert_latest_payload(job, domain):
    rows = job.rows(domain)
    assert len(rows) == 1
    if domain == "es_knowledge":
        assert rows[0]["term_value"] == "新定义"
    else:
        assert rows[0]["sql_content"] == "SELECT 2"


@pytest.mark.parametrize("domain", ["es_knowledge", "sql_sample"])
@pytest.mark.parametrize("mode", ["full", "incremental"])
def test_source_edit_during_write_remains_dirty_until_next_sync(dirty_job, monkeypatch, domain, mode):
    job, sessions, db, kb, run = dirty_job
    confirm = service._confirm_manifest_writes

    def edit_during_write(db, manifests):
        with sessions() as reader:
            assert getattr(reader.get(models.KnowledgeBase, 71), flag(domain)) is False
        edit_source(sessions, domain)
        confirm(db, manifests)

    monkeypatch.setattr(service, "_confirm_manifest_writes", edit_during_write)
    run(domain, mode)
    with sessions() as reader:
        stored = reader.get(models.KnowledgeBase, 71)
        assert getattr(stored, flag(domain)) is True
        other = "sample_library_dirty" if domain == "es_knowledge" else "knowledge_term_dirty"
        assert getattr(stored, other) is True

    monkeypatch.setattr(service, "_confirm_manifest_writes", confirm)
    run(domain)
    with sessions() as reader:
        assert getattr(reader.get(models.KnowledgeBase, 71), flag(domain)) is False
    assert_latest_payload(job, domain)
    assert db.expire_on_commit is True


@pytest.mark.parametrize("domain", ["es_knowledge", "sql_sample"])
def test_eager_source_loaded_before_step_is_refreshed_after_clear(dirty_job, domain):
    job, sessions, db, kb, run = dirty_job
    # Match the worker's eager detail load before entering the synchronization step.
    if domain == "es_knowledge":
        assert kb.kb_knowledge_terms[0].knowledge_term.term_value == "旧定义"
    else:
        assert kb.kb_sample_libraries[0].sample_content == "SELECT 1"
    db.expire_on_commit = False
    edit_source(sessions, domain)
    run(domain)
    assert_latest_payload(job, domain)
    assert db.expire_on_commit is False


@pytest.mark.parametrize("domain", ["es_knowledge", "sql_sample"])
@pytest.mark.parametrize("error", [RuntimeError, service.VectorizationCancelled])
def test_failed_or_cancelled_write_restores_dirty_and_keeps_pending(dirty_job, monkeypatch, domain, error):
    job, sessions, db, kb, run = dirty_job

    def interrupt(*args):
        raise error("write acknowledgement interrupted")

    monkeypatch.setattr(service, "_confirm_manifest_writes", interrupt)
    with pytest.raises(error, match="write acknowledgement interrupted"):
        run(domain)
    with sessions() as reader:
        assert getattr(reader.get(models.KnowledgeBase, 71), flag(domain)) is True
        pending = reader.query(models.KbVectorManifest).filter_by(kb_id=71, domain=domain).all()
        assert pending
        assert all(row.embedding_hash is None and row.payload_hash is None for row in pending)
    assert db.expire_on_commit is True
