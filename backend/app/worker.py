"""Platform background process. Run alongside the API via app.runtime."""
import asyncio
import logging
import os
import signal
from contextlib import asynccontextmanager

from sqlalchemy import text

from .core.database import SessionLocal, engine

logger = logging.getLogger(__name__)


def background_mode():
    return os.getenv("PLATFORM_BACKGROUND_MODE", "inline").lower()


async def _index_loop():
    from .services.trace_index import backfill_trace_index
    while True:
        try:
            count = await asyncio.to_thread(backfill_trace_index, SessionLocal)
            await asyncio.sleep(1 if count else 30)
        except Exception:
            logger.exception("Trace ID index migration failed")
            await asyncio.sleep(30)


async def _eval_loop():
    from .services.eval.scheduler import recover_running_tasks, run_due_schedules
    from .services.eval.eval_task_service import dispatch_task, _running_tasks, _cancel_events
    from .models.eval import EvalTask
    await recover_running_tasks()
    scheduled_at = 0
    while True:
        with SessionLocal() as db:
            states = dict(db.query(EvalTask.id, EvalTask.status).filter(
                (EvalTask.status == "running") | EvalTask.id.in_(list(_running_tasks))).all())
        for task_id, state in states.items():
            if state == "running" and task_id not in _running_tasks:
                dispatch_task(task_id)
            elif state != "running" and task_id in _running_tasks:
                event = _cancel_events.get(task_id)
                if event:
                    event.set()
                _running_tasks[task_id].cancel()
        now = asyncio.get_running_loop().time()
        if now >= scheduled_at:
            run_due_schedules()
            scheduled_at = now + 60
        await asyncio.sleep(1)


@asynccontextmanager
async def background_tasks():
    from .services.eval import eval_task_service
    eval_task_service._task_loop = asyncio.get_running_loop()
    from .services.data_sync.scheduler import dispatcher_loop, worker_loop
    from .services.data_sync.service import ensure_tasks
    from .services.chatbi.exports import export_worker, export_worker_enabled

    def initialize():
        with SessionLocal() as db:
            ensure_tasks(db)
    await asyncio.to_thread(initialize)
    tasks = [asyncio.create_task(dispatcher_loop(SessionLocal)),
             asyncio.create_task(worker_loop(SessionLocal)),
             asyncio.create_task(_eval_loop()), asyncio.create_task(_index_loop())]
    if export_worker_enabled():
        tasks.append(asyncio.create_task(export_worker()))
    try:
        yield tasks
    finally:
        from .services.eval.eval_task_service import _running_tasks
        tasks.extend(list(_running_tasks.values()))
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def main():
    # Only one background scheduler is active across API workers or overlapping
    # deployments. Database advisory locks are released on connection/process exit.
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(signum, stop.set)
    connection = await asyncio.to_thread(engine.connect)
    acquired = False
    unlock = None
    try:
        dialect = engine.dialect.name
        if dialect == "mysql":
            acquired = await asyncio.to_thread(lambda: connection.execute(text("SELECT GET_LOCK('platform_background', 0)")).scalar())
            unlock = "SELECT RELEASE_LOCK('platform_background')"
        elif dialect == "postgresql":
            acquired = await asyncio.to_thread(lambda: connection.execute(text("SELECT pg_try_advisory_lock(816112026)")).scalar())
            unlock = "SELECT pg_advisory_unlock(816112026)"
        else:
            acquired = True
        if not acquired:
            raise RuntimeError("平台后台任务已有活动进程")
        await asyncio.to_thread(connection.commit)
        os.environ["PLATFORM_BACKGROUND_MODE"] = "worker"
        async with background_tasks() as tasks:
            while not stop.is_set():
                try:
                    await asyncio.wait_for(stop.wait(), timeout=10)
                    break
                except TimeoutError:
                    pass
                for task in tasks:
                    if task.done():
                        raise RuntimeError("平台后台调度任务意外退出") from task.exception()
                await asyncio.to_thread(lambda: connection.execute(text("SELECT 1")).scalar())
                await asyncio.to_thread(connection.commit)
    finally:
        try:
            if acquired and unlock:
                await asyncio.to_thread(lambda: connection.execute(text(unlock)))
                await asyncio.to_thread(connection.commit)
        finally:
            await asyncio.to_thread(connection.close)
            for signum in (signal.SIGTERM, signal.SIGINT):
                loop.remove_signal_handler(signum)


async def run_worker():
    try:
        await main()
    finally:
        from .core.trace_writer import flush_traces
        from .core.http_clients import close_http_clients
        from .core.execution import shutdown_blocking_pools
        from .core.resources import close_resources
        from .core.db_connections import close_connection_pools
        from .core.database import close_query_engines
        await flush_traces()
        await close_http_clients()
        await asyncio.to_thread(shutdown_blocking_pools)
        await asyncio.to_thread(close_resources)
        await asyncio.to_thread(close_connection_pools)
        await asyncio.to_thread(close_query_engines)


if __name__ == "__main__":
    from .core.logging_config import setup_logging
    from .services.system_logs import start_log_writer, stop_log_writer
    setup_logging()
    start_log_writer(SessionLocal)
    try:
        asyncio.run(run_worker())
    finally:
        stop_log_writer()
