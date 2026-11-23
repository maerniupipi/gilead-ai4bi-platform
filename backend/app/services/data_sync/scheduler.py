"""Independent dispatcher and serial worker; safe with multiple API processes."""
import asyncio
import logging
import threading
from uuid import uuid4

from . import service
from .pipeline import run_pipeline
from .settings import SyncConfig

logger = logging.getLogger(__name__)


def execute_claimed(factory, run_id, owner, pipeline=run_pipeline):
    stop = threading.Event()

    def heartbeat():
        while not stop.wait(15):
            try:
                if not service.renew_lease(factory, run_id, owner):
                    return
            except Exception:
                logger.warning("data sync heartbeat failed run=%s", run_id)

    thread = threading.Thread(target=heartbeat, daemon=True, name="data-sync-heartbeat")
    thread.start()
    config = None
    try:
        with factory() as db:
            from ...models.data_sync import DataSyncRun
            run = db.get(DataSyncRun, run_id)
            if not run or run.status != "running" or run.worker_id != owner:
                return
            config = SyncConfig.from_env(run.task_id)
        count = pipeline(config, lambda **values: service.record_progress(factory, run_id, owner, **values), run_id)
        service.finish_run(factory, run_id, owner, "succeeded", count=count)
    except Exception as exc:
        logger.warning("data sync failed run=%s type=%s", run_id, type(exc).__name__)
        service.finish_run(factory, run_id, owner, "failed", error=service.safe_error(exc, config))
    finally:
        stop.set()
        thread.join(timeout=1)


async def dispatcher_loop(factory):
    while True:
        try:
            await asyncio.to_thread(service.expire_runs, factory)
            await asyncio.to_thread(service.enqueue_due, factory)
        except Exception:
            logger.exception("data sync dispatcher iteration failed")
        await asyncio.sleep(10)


async def worker_loop(factory):
    owner = str(uuid4())
    while True:
        try:
            run_id = await asyncio.to_thread(service.claim_next, factory, owner)
            if run_id:
                await asyncio.to_thread(execute_claimed, factory, run_id, owner)
                continue
        except Exception:
            logger.exception("data sync worker iteration failed")
        await asyncio.sleep(3)
