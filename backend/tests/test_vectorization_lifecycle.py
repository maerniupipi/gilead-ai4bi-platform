"""Exercise job ownership and cancellation with isolated SQLite sessions."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core import database
from app.models import KnowledgeBase
from app.schemas.knowledge_base import VectorizationSteps, VectorizeRequest
from app.services.knowledge.knowledge_base import service


@pytest.fixture
def lifecycle(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'lifecycle.sqlite'}")
    KnowledgeBase.__table__.create(engine)
    sessions = sessionmaker(bind=engine)
    with sessions() as db:
        db.add(KnowledgeBase(id=91, space_id=1, name="local test", knowledge_access_id=1))
        db.commit()
    workers = []

    class Worker:
        def __init__(self, target):
            self.target = target

        def start(self):
            workers.append(self.target)

    monkeypatch.setattr(database, "SessionLocal", sessions)
    monkeypatch.setattr(service, "threading", SimpleNamespace(Thread=Worker))
    request = VectorizeRequest(steps=VectorizationSteps(
        field_vectorization=False, value_vectorization=False, knowledge_term_to_es=True,
    ))

    def status():
        with sessions() as db:
            return db.get(KnowledgeBase, 91).vectorization_status

    yield SimpleNamespace(sessions=sessions, workers=workers, request=request, status=status)
    engine.dispose()


def start(job):
    with job.sessions() as db:
        return service.vectorize_knowledge_base_service(db, 91, job.request, 1)


def test_empty_steps_are_rejected_without_claiming_a_job(lifecycle):
    job = lifecycle
    job.request.steps.knowledge_term_to_es = False
    with pytest.raises(HTTPException) as error:
        start(job)
    assert error.value.status_code == 400
    assert job.status() == "pending"
    assert not job.workers


def test_concurrent_start_requests_claim_only_one_worker(lifecycle, monkeypatch):
    job = lifecycle
    barrier = Barrier(2)
    get_active = service.get_knowledge_base_active

    def both_read_pending(*args, **kwargs):
        kb = get_active(*args, **kwargs)
        assert kb.vectorization_status == "pending"
        barrier.wait(timeout=5)
        return kb

    monkeypatch.setattr(service, "get_knowledge_base_active", both_read_pending)

    def attempt():
        try:
            return start(job)["status"]
        except HTTPException as exc:
            return exc.status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: attempt(), range(2)))
    assert sorted(map(str, results)) == ["409", "processing"]
    assert len(job.workers) == 1
    assert job.status() == "processing"


def test_cancellation_blocks_restart_until_worker_acknowledges(lifecycle):
    job = lifecycle
    start(job)
    with job.sessions() as db:
        assert service.cancel_vectorization_service(db, 91, 1)["status"] == "cancelling"
    with pytest.raises(HTTPException):
        start(job)
    assert len(job.workers) == 1
    # The original worker sees cancellation before doing any external work.
    job.workers[0]()
    assert job.status() == "cancelled"
    assert start(job)["status"] == "processing"
    assert len(job.workers) == 2


@pytest.mark.parametrize("outcome", ["completed", "failed"])
def test_accepted_cancellation_wins_a_terminal_state_race(lifecycle, outcome):
    job = lifecycle
    start(job)
    with job.sessions() as worker_db:
        stale_kb = worker_db.get(KnowledgeBase, 91)
        assert stale_kb.vectorization_status == "processing"
        with job.sessions() as cancel_db:
            service.cancel_vectorization_service(cancel_db, 91, 1)
        service._finish_vectorization(worker_db, 91, outcome)
    assert job.status() == "cancelled"


def test_late_cancel_cannot_overwrite_completed_job(lifecycle, monkeypatch):
    job = lifecycle
    start(job)
    with job.sessions() as stale_db:
        stale_kb = stale_db.get(KnowledgeBase, 91)
        with job.sessions() as worker_db:
            service._finish_vectorization(worker_db, 91, "completed")
        monkeypatch.setattr(service, "get_knowledge_base_active", lambda *args: stale_kb)
        with pytest.raises(HTTPException) as error:
            service.cancel_vectorization_service(stale_db, 91, 1)
        assert error.value.status_code == 400
    assert job.status() == "completed"


def test_worker_start_failure_releases_the_job(lifecycle, monkeypatch):
    job = lifecycle

    class BrokenWorker:
        def __init__(self, target):
            pass

        def start(self):
            raise RuntimeError("cannot start a thread")

    monkeypatch.setattr(service, "threading", SimpleNamespace(Thread=BrokenWorker))
    with pytest.raises(HTTPException) as error:
        start(job)
    assert error.value.status_code == 503
    assert job.status() == "failed"


def test_worker_initialization_failure_releases_the_job(lifecycle, monkeypatch):
    job = lifecycle
    start(job)

    def unavailable(*args):
        raise RuntimeError("initialization failed")

    monkeypatch.setattr(service, "get_knowledge_base_active", unavailable)
    job.workers[0]()
    assert job.status() == "failed"
