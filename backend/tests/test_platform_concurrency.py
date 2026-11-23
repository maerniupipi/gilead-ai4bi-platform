"""Regressions for event-loop blocking, capacity leaks and trace write ordering."""
import asyncio
import copy
import threading
import time
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.execution import BlockingPool, read_database
from app.core.trace_writer import write_trace, flush_traces
from app.core.http_clients import model_client, close_http_clients
from app.schemas.autobi_atomic import ESValueRetrieverRequest
from app.services.knowledge.autobi_atomic import service as atomic


def test_cancelled_blocking_work_retains_capacity_until_the_call_really_ends():
    pool = BlockingPool("test-bounded", 1, 0)
    entered, release = threading.Event(), threading.Event()

    def slow():
        entered.set()
        release.wait(3)

    async def run():
        task = asyncio.create_task(pool.run(slow))
        while not entered.is_set():
            await asyncio.sleep(0.005)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        with pytest.raises(HTTPException) as caught:
            await pool.run(lambda: 1)
        assert caught.value.status_code == 503
        release.set()
        for _ in range(100):
            await asyncio.sleep(0.005)
            try:
                assert await pool.run(lambda: 7) == 7
                return
            except HTTPException:
                pass
        pytest.fail("capacity was not returned")

    try:
        asyncio.run(run())
    finally:
        release.set()
        pool.shutdown()


def test_database_unit_owns_its_session_and_releases_connection_before_await(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'units.db'}", pool_size=1, max_overflow=0)
    thread = threading.get_ident()
    with Session(engine) as caller:
        def read(worker):
            assert worker is not caller and threading.get_ident() != thread
            return worker.execute(text("SELECT 1")).scalar_one()

        async def run():
            for _ in range(3):
                assert await read_database(caller, read) == 1
                assert engine.pool.checkedout() == 0
                await asyncio.sleep(0.01)
        asyncio.run(run())
    engine.dispose()


def test_five_slow_retrievals_do_not_block_unrelated_requests(monkeypatch):
    monkeypatch.setattr(atomic, "get_knowledge_base_active", lambda *args: SimpleNamespace(space_id=1))
    monkeypatch.setattr(atomic, "_resolve_es_config_safe", lambda *args: {"host": "test"})

    class Search:
        def __init__(self, config):
            pass
        def search_table_values(self, *args, **kwargs):
            time.sleep(0.15)
            return [{"field_value": "same result", "score": 1}]
    monkeypatch.setattr(atomic, "ElasticsearchService", Search)

    async def run():
        tasks = [asyncio.create_task(atomic.AutoBIAtomicService.es_value_retrieve(
            None, 1, ESValueRetrieverRequest(query="query"))) for _ in range(5)]
        started = time.monotonic()
        await asyncio.sleep(0.02)
        assert time.monotonic() - started < 0.2
        results = await asyncio.gather(*tasks)
        assert all(result.results[0].content == "same result" for result in results)
    asyncio.run(run())


def test_progress_is_coalesced_and_every_distinct_final_trace_is_saved():
    saved = []
    def writer(trace_id, payload):
        time.sleep(0.005)
        saved.append((trace_id, copy.deepcopy(payload)))

    async def run_one(trace_id):
        payload = {"status": "running", "steps": []}
        for index in range(36):
            payload["steps"].append({"index": index, "status": "done"})
            await write_trace(writer, trace_id, payload)
        payload["status"] = "done"
        await write_trace(writer, trace_id, payload)

    async def run():
        await asyncio.gather(*(run_one(str(index)) for index in range(5)))
        await flush_traces()
    asyncio.run(run())
    assert len(saved) == 5
    assert {trace for trace, _ in saved} == {str(i) for i in range(5)}
    assert all(payload["status"] == "done" and len(payload["steps"]) == 36 for _, payload in saved)


def test_final_trace_waits_for_an_inflight_progress_write():
    entered, release = threading.Event(), threading.Event()
    states = []
    def writer(trace_id, payload):
        if payload["status"] == "running":
            entered.set()
            release.wait(3)
        states.append(payload["status"])

    async def run():
        await write_trace(writer, "order", {"status": "running", "steps": []})
        async with asyncio.timeout(2):
            while not entered.is_set():
                await asyncio.sleep(0.01)
        final = asyncio.create_task(write_trace(writer, "order", {"status": "error", "steps": []}))
        await asyncio.sleep(0.02)
        assert not final.done()
        release.set()
        await final
    try:
        asyncio.run(run())
    finally:
        release.set()
    assert states == ["running", "error"]


def test_model_http_connections_are_reused_and_headers_remain_request_local(monkeypatch):
    original = httpx.AsyncClient
    created, credentials = [], []
    def respond(request):
        credentials.append(request.headers["Authorization"])
        return httpx.Response(200, json={})
    def create(**kwargs):
        client = original(transport=httpx.MockTransport(respond), **kwargs)
        created.append(client)
        return client
    monkeypatch.setattr(httpx, "AsyncClient", create)

    async def run():
        for key in ("one", "two"):
            async with model_client(httpx.Timeout(30)) as client:
                await client.post("https://example.test", headers={"Authorization": key})
        await close_http_clients()
    asyncio.run(run())
    assert len(created) == 1 and created[0].is_closed
    assert credentials == ["one", "two"]


def test_script_timeout_terminates_the_process_and_releases_capacity(monkeypatch):
    from app.services.agent_app import script_process
    monkeypatch.setenv("WORKFLOW_SCRIPT_TIMEOUT_SECONDS", "0.5")
    original = asyncio.create_subprocess_exec
    processes = []
    async def spawn(*args, **kwargs):
        process = await original(*args, **kwargs)
        processes.append(process)
        return process
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)

    async def run():
        with pytest.raises(ValueError, match="超时"):
            await script_process.run_script("def main():\n    while True:\n        pass", {},
                                            {"_thought_events": [], "_legacy_cache": {}})
        assert processes[0].returncode is not None
        monkeypatch.setenv("WORKFLOW_SCRIPT_TIMEOUT_SECONDS", "10")
        assert await script_process.run_script("def main():\n    return {'result': 42}", {},
            {"_thought_events": [], "_legacy_cache": {}}) == {"result": 42}
    asyncio.run(run())


def test_script_preserves_in_place_legacy_cache_updates():
    from app.services.agent_app.script_process import run_script
    values = {"_thought_events": [], "_legacy_cache": {"items": [1], "untouched": {"x": 2}}}
    code = """def main():
    cache_get('items').append(3)
    cache_set('new', {'ok': True})
    return {'result': cache_get('items')}
"""
    assert asyncio.run(run_script(code, {}, values)) == {"result": [1, 3]}
    assert values["_legacy_cache"] == {"items": [1, 3], "untouched": {"x": 2}, "new": {"ok": True}}


def test_script_capacity_queues_concurrent_work_without_blocking_the_loop(monkeypatch):
    from app.services.agent_app import script_process
    monkeypatch.setattr(script_process, "_slots", threading.BoundedSemaphore(1))
    code = "import time\ndef main():\n    time.sleep(0.1)\n    return {'result': 7}"

    async def run():
        tasks = [asyncio.create_task(script_process.run_script(code, {},
            {"_thought_events": [], "_legacy_cache": {}})) for _ in range(2)]
        started = time.monotonic()
        await asyncio.sleep(0.02)
        assert time.monotonic() - started < 0.2
        assert await asyncio.gather(*tasks) == [{"result": 7}, {"result": 7}]
    asyncio.run(run())


def test_thread_resources_are_reused_and_released_when_a_background_thread_finishes():
    from app.core.resources import thread_resource, close_thread_resources
    created = []

    class Resource:
        def __init__(self, config):
            self.closed = False
            created.append(self)
        def close(self):
            self.closed = True

    def work():
        try:
            first = thread_resource(Resource, {"database": "one"})
            assert thread_resource(Resource, {"database": "one"}) is first
            assert thread_resource(Resource, {"database": "two"}) is not first
        finally:
            close_thread_resources()

    thread = threading.Thread(target=work)
    thread.start()
    thread.join()
    assert len(created) == 2 and all(resource.closed for resource in created)


def test_background_dispatch_uses_one_worker_and_does_not_run_inside_api(monkeypatch):
    from app.services.eval import eval_task_service as service
    monkeypatch.setattr(service, "_running_tasks", {})
    started = []

    async def execute(task_id):
        started.append(task_id)
        await asyncio.sleep(0.01)
    monkeypatch.setattr(service, "execute_task_background", execute)

    async def run():
        monkeypatch.setenv("PLATFORM_BACKGROUND_MODE", "external")
        service.dispatch_task(5)
        assert service._running_tasks == {}
        monkeypatch.setenv("PLATFORM_BACKGROUND_MODE", "worker")
        service.dispatch_task(5)
        service.dispatch_task(5)
        await asyncio.gather(*service._running_tasks.values())
        await asyncio.sleep(0)
    asyncio.run(run())
    assert started == [5] and service._running_tasks == {}


@pytest.mark.parametrize("acquired", [True, False])
def test_worker_releases_its_leader_lock_on_graceful_shutdown(monkeypatch, acquired):
    import signal
    from contextlib import asynccontextmanager
    from app import worker
    statements, handlers, removed = [], {}, []

    class Connection:
        def execute(self, statement):
            statements.append(str(statement))
            return SimpleNamespace(scalar=lambda: acquired)
        def commit(self):
            pass
        def close(self):
            statements.append("close")

    @asynccontextmanager
    async def background():
        handlers[signal.SIGTERM]()
        yield []

    monkeypatch.setenv("PLATFORM_BACKGROUND_MODE", "external")
    monkeypatch.setattr(worker, "engine", SimpleNamespace(connect=Connection, dialect=SimpleNamespace(name="mysql")))
    monkeypatch.setattr(worker, "background_tasks", background)

    async def run():
        loop = asyncio.get_running_loop()
        monkeypatch.setattr(loop, "add_signal_handler", lambda signum, callback: handlers.update({signum: callback}))
        monkeypatch.setattr(loop, "remove_signal_handler", removed.append)
        if acquired:
            await worker.main()
        else:
            with pytest.raises(RuntimeError, match="已有活动进程"):
                await worker.main()
    asyncio.run(run())
    assert statements[-1] == "close"
    assert ("SELECT RELEASE_LOCK('platform_background')" in statements) is acquired
    assert set(removed) == {signal.SIGTERM, signal.SIGINT}


def test_data_replacement_uses_one_transaction_and_rolls_back_on_count_mismatch():
    from contextlib import contextmanager
    from app.services.data_sync.loader import replace_table_from_stage
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE sales (value INTEGER)"))
        connection.execute(text("CREATE TABLE sales_stage (value INTEGER)"))
        connection.execute(text("INSERT INTO sales VALUES (1)"))
        connection.execute(text("INSERT INTO sales_stage VALUES (2), (3)"))
    statements = []

    class Connection:
        def __init__(self, connection):
            self.connection = connection
        def execute(self, statement):
            statements.append(str(statement))
            if str(statement).startswith("SET LOCAL"):
                return None  # PostgreSQL-only lock deadline, checked below.
            return self.connection.execute(statement)

    @contextmanager
    def begin():
        with engine.begin() as connection:
            yield Connection(connection)

    target = SimpleNamespace(begin=begin)
    with pytest.raises(RuntimeError, match="row count mismatch"):
        replace_table_from_stage(target, "main.sales", ["value"], 3)
    with engine.connect() as connection:
        assert connection.execute(text("SELECT value FROM sales")).scalars().all() == [1]
    replace_table_from_stage(target, "main.sales", ["value"], 2)
    with engine.connect() as connection:
        assert connection.execute(text("SELECT value FROM sales")).scalars().all() == [2, 3]
    assert statements[0] == "SET LOCAL lock_timeout = '5s'"
    assert any(sql.startswith("DELETE FROM") for sql in statements)
    assert not any("TRUNCATE" in sql for sql in statements)
    engine.dispose()


@pytest.mark.parametrize("cancel", [True, False])
def test_stream_final_trace_records_cancellation_and_preserves_completed_status(monkeypatch, cancel):
    from app.services.agent_app import workflow_engine as workflow
    saved = []
    nodes = [{"id": kind, "data": {"kind": kind, "label": kind}}
             for kind in ("start", "script", "output")]
    version = SimpleNamespace(workflow_json={"nodes": nodes, "edges": [
        {"source": "start", "target": "script"}, {"source": "script", "target": "output"}]})
    monkeypatch.setattr(workflow, "get_version_for_app", lambda *args: version)
    monkeypatch.setattr(workflow, "save_workflow_trace", lambda trace_id, payload: saved.append(copy.deepcopy(payload)))

    async def run():
        entered = asyncio.Event()
        async def execute(ctx, node):
            entered.set()
            if cancel:
                await asyncio.sleep(30)
            return {"content": "answer"}
        monkeypatch.setitem(workflow._KIND_HANDLERS, "script", execute)
        stream = workflow.run_agent_workflow_stream(None, 1, 1, {})
        async def consume():
            async for _ in stream:
                pass
        task = asyncio.create_task(consume())
        await asyncio.wait_for(entered.wait(), 2)
        if cancel:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            await task
        await stream.aclose()
        await flush_traces()
    asyncio.run(run())
    assert saved[-1]["status"] == ("stopped" if cancel else "done")
    assert all(step["status"] != "running" for step in saved[-1]["steps"])


def test_workflow_capacity_is_returned_after_cancellation(monkeypatch):
    from app.core import execution
    monkeypatch.setattr(execution, "_execution_slots", threading.BoundedSemaphore(1))

    @execution.bounded_execution
    async def wait(entered):
        entered.set()
        await asyncio.sleep(30)

    @execution.bounded_execution
    async def immediate():
        return "ok"

    async def run():
        entered = asyncio.Event()
        task = asyncio.create_task(wait(entered))
        await entered.wait()
        with pytest.raises(HTTPException) as error:
            await immediate()
        assert error.value.status_code == 503
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert await immediate() == "ok"
    asyncio.run(run())


@pytest.mark.parametrize("initialization_result", [0, 3])
def test_runtime_initializes_once_before_starting_api_and_background_worker(monkeypatch, initialization_result):
    import signal
    import urllib.request
    from contextlib import nullcontext
    from app import runtime
    children, handlers = [], {}

    class Child:
        def __init__(self, args, *, env):
            self.args, self.env = args, env
            self.returncode = initialization_result if not children else None
            children.append(self)
        def poll(self):
            return self.returncode
        def terminate(self):
            self.returncode = 0
        def wait(self, timeout=None):
            return self.returncode

    monkeypatch.setattr(runtime.subprocess, "Popen", Child)
    monkeypatch.setattr(runtime.signal, "signal", lambda number, handler: handlers.update({number: handler}))
    monkeypatch.setattr(runtime.time, "sleep", lambda duration: handlers[signal.SIGTERM](None, None))
    monkeypatch.setattr(urllib.request, "urlopen", lambda *args, **kwargs: nullcontext())
    assert runtime.main() == (0 if initialization_result == 0 else 1)
    assert children[0].args[-2:] == ["-c", "import app.main"]
    assert children[0].env["PLATFORM_SCHEMA_INITIALIZED"] == "false"
    if initialization_result == 0:
        assert len(children) == 3
        assert children[1].args[2] == "uvicorn" and children[2].args[-1] == "app.worker"
        assert all(child.env["PLATFORM_SCHEMA_INITIALIZED"] == "true" for child in children[1:])
        assert all(child.returncode == 0 for child in children)
    else:
        assert len(children) == 1
