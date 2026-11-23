"""Bounded blocking work, with a separate Session per database work item."""
import asyncio
import contextvars
import functools
import inspect
import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from fastapi import HTTPException
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class BlockingPool:
    def __init__(self, name, workers, queued):
        self.name = name
        self.executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix=name)
        self.slots = threading.BoundedSemaphore(workers + queued)
        self.lock = threading.Lock()
        self.pending = 0
        self.active = 0

    async def run(self, function, *args, **kwargs):
        if not self.slots.acquire(blocking=False):
            raise HTTPException(503, f"{self.name} 执行容量已满，请稍后再试")
        context = contextvars.copy_context()
        submitted = time.monotonic()
        with self.lock:
            self.pending += 1

        def work():
            started = time.monotonic()
            with self.lock:
                self.pending -= 1
                self.active += 1
            try:
                return context.run(function, *args, **kwargs)
            finally:
                with self.lock:
                    self.active -= 1
                self.slots.release()
                elapsed = time.monotonic() - started
                waiting = started - submitted
                if waiting >= 0.1 or elapsed >= 1:
                    logger.info("blocking work pool=%s queue_ms=%.1f elapsed_ms=%.1f",
                                self.name, waiting * 1000, elapsed * 1000)

        try:
            future = asyncio.get_running_loop().run_in_executor(self.executor, work)
        except BaseException:
            with self.lock:
                self.pending -= 1
            self.slots.release()
            raise
        # Cancellation cannot stop a running database/SDK call. Keep its capacity
        # reserved until the underlying call ends, and consume late exceptions.
        future.add_done_callback(lambda done: done.exception() if not done.cancelled() else None)
        return await asyncio.shield(future)

    def shutdown(self):
        self.executor.shutdown(wait=True)

    def stats(self):
        with self.lock:
            return {"active": self.active, "queued": self.pending}


DATABASE_WORK = BlockingPool("platform-db", int(os.getenv("PLATFORM_DB_WORKERS", "8")), 32)
RETRIEVAL_WORK = BlockingPool("platform-retrieval", int(os.getenv("PLATFORM_RETRIEVAL_WORKERS", "16")), 64)
HEALTH_WORK = BlockingPool("platform-health", 1, 0)
TRACE_WORK = BlockingPool("platform-trace", 2, 256)
_execution_slots = threading.BoundedSemaphore(int(os.getenv("PLATFORM_EXECUTION_CONCURRENCY", "32")))


def bounded_execution(function):
    """Bound root workflow requests, including the entire streaming lifetime."""
    def acquire():
        if not _execution_slots.acquire(blocking=False):
            raise HTTPException(503, "平台分析并发已满，请稍后再试")

    if inspect.isasyncgenfunction(function):
        @functools.wraps(function)
        async def stream(*args, **kwargs):
            acquire()
            try:
                from contextlib import aclosing
                deadline = time.monotonic() + float(os.getenv("PLATFORM_EXECUTION_TIMEOUT_SECONDS", "1800"))
                async with aclosing(function(*args, **kwargs)) as source:
                    while True:
                        try:
                            item = await asyncio.wait_for(anext(source), max(0, deadline - time.monotonic()))
                        except StopAsyncIteration:
                            break
                        yield item
            finally:
                _execution_slots.release()
        return stream

    @functools.wraps(function)
    async def call(*args, **kwargs):
        acquire()
        try:
            async with asyncio.timeout(float(os.getenv("PLATFORM_EXECUTION_TIMEOUT_SECONDS", "1800"))):
                return await function(*args, **kwargs)
        finally:
            _execution_slots.release()
    return call


async def read_database(db, function, *args, pool=DATABASE_WORK, **kwargs):
    """Return materialized results. An ORM Session never crosses concurrent tasks."""
    bind = db.get_bind() if isinstance(db, Session) else None

    def work():
        if bind is None:
            return function(db, *args, **kwargs)
        with Session(bind=bind, expire_on_commit=False) as worker_db:
            result = function(worker_db, *args, **kwargs)
            # Preserve loaded scalar attributes on returned configuration rows.
            worker_db.expunge_all()
            return result

    return await pool.run(work)


def isolated_retrieval(function):
    @functools.wraps(function)
    async def call(db, *args, **kwargs):
        return await read_database(db, function, *args, pool=RETRIEVAL_WORK, **kwargs)
    return call


def release_read_connection(db):
    """Release a worker-owned read transaction before external network I/O."""
    if isinstance(db, Session) and not (db.new or db.dirty or db.deleted):
        db.expunge_all()
        db.close()


def shutdown_blocking_pools():
    for pool in (DATABASE_WORK, RETRIEVAL_WORK, TRACE_WORK, HEALTH_WORK):
        pool.shutdown()


async def monitor_event_loop():
    from .database import engine
    from .logging_config import log_buffer_stats
    loop = asyncio.get_running_loop()
    reports_at = loop.time() + 30
    while True:
        started = loop.time()
        await asyncio.sleep(1)
        lag_ms = max(0, (loop.time() - started - 1) * 1000)
        if lag_ms >= 100 or loop.time() >= reports_at:
            logger.log(logging.WARNING if lag_ms >= 100 else logging.INFO,
                       "platform capacity pid=%s event_loop_lag_ms=%.1f db_pool=%s workers=%s log_buffers=%s",
                       os.getpid(), lag_ms, engine.pool.status(),
                       {pool.name: pool.stats() for pool in (DATABASE_WORK, RETRIEVAL_WORK, TRACE_WORK)},
                       log_buffer_stats())
            reports_at = loop.time() + 30
