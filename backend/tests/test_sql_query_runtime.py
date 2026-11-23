import asyncio
import threading
import time
from decimal import Decimal
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.schemas.autobi_atomic import ExecuteSqlRequest
from app.services.knowledge import sql_runtime as runtime
from app.services.knowledge.autobi_atomic import service as atomic
from app.services.knowledge.knowledge_base import service


@pytest.fixture
def source(tmp_path, monkeypatch):
    engine = create_engine(f'sqlite:///{tmp_path / "query.db"}')
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE sample (id INTEGER, payload TEXT)'))
        conn.execute(text('INSERT INTO sample VALUES (:id,:payload)'),
                     [{'id': i, 'payload': 'x' * 2000} for i in range(10)])
    ds = SimpleNamespace(database_type='postgresql', is_deleted=False)
    kb = SimpleNamespace(knowledge_access=SimpleNamespace(data_source=ds))
    monkeypatch.setattr(service, 'get_knowledge_base_detail', lambda *a: kb)
    monkeypatch.setattr(service, '_create_external_source_engine', lambda *a: engine)
    yield engine
    engine.dispose()


def test_normal_sql_retains_values_and_limit(source):
    result = service.execute_knowledge_base_sql_service(None, 1, 'SELECT id FROM sample ORDER BY id LIMIT 2')
    assert result.rows == [{'id': 0}, {'id': 1}] and result.row_count == 2


@pytest.mark.parametrize('value,expected', [
    (Decimal('1234.567890'), '1234.567890'),
    (Decimal('1.2300'), '1.2300'),
    (Decimal('0.0000123456'), '0.0000123456'),
    (9007199254740993, '9007199254740993'),
    (-9007199254740993, '-9007199254740993'),
    (9007199254740991, 9007199254740991),
    (0, 0), (True, True), (None, None), ('001.2300', '001.2300'),
])
def test_sql_cell_serialization_preserves_exact_values(value, expected):
    result = service._serialize_sql_cell(value)
    assert result == expected
    assert type(result) is type(expected)


def test_sql_query_preserves_large_integers_for_browser_clients(source):
    result = service.execute_knowledge_base_sql_service(None, 1, 'SELECT 9007199254740993 AS value')
    assert result.rows == [{'value': '9007199254740993'}]


def test_large_result_is_rejected_and_next_query_still_works(source, monkeypatch):
    monkeypatch.setenv('KNOWLEDGE_SQL_MAX_ROWS', '3')
    with pytest.raises(HTTPException) as err:
        service.execute_knowledge_base_sql_service(None, 1, 'SELECT id FROM sample')
    assert err.value.status_code == 413
    assert service.execute_knowledge_base_sql_service(None, 1, 'SELECT 1 AS value').rows == [{'value': 1}]


def test_large_cells_are_rejected(source, monkeypatch):
    monkeypatch.setenv('KNOWLEDGE_SQL_MAX_BYTES', '1024')
    with pytest.raises(HTTPException) as err:
        service.execute_knowledge_base_sql_service(None, 1, 'SELECT payload FROM sample LIMIT 1')
    assert err.value.status_code == 413


@pytest.mark.parametrize('sql', ['DELETE FROM sample', 'SELECT 1; SELECT 2', 'SELECT 1 INTO leaked',
                                 'SELECT * FROM sample FOR UPDATE', 'WITH x AS (DELETE FROM sample RETURNING *) SELECT * FROM x'])
def test_only_single_read_query_is_executed(source, sql):
    with pytest.raises(HTTPException) as err:
        service.execute_knowledge_base_sql_service(None, 1, sql)
    assert err.value.status_code == 400


def test_database_failure_is_clear_without_returning_connection_secrets(source):
    with pytest.raises(HTTPException) as err:
        service.execute_knowledge_base_sql_service(None, 1, 'SELECT private_password FROM missing')
    assert err.value.status_code == 400 and 'private_password' not in err.value.detail


def test_pymysql_statement_timeout_is_translated_to_504(source, monkeypatch):
    from sqlalchemy.exc import OperationalError
    import pymysql
    def connect():
        raise OperationalError('SELECT 1', {}, pymysql.OperationalError(3024, 'maximum execution time exceeded'))
    disposed = []
    engine = SimpleNamespace(connect=connect, dispose=lambda: disposed.append(True))
    monkeypatch.setattr(service, '_create_external_source_engine', lambda *a: engine)
    with pytest.raises(HTTPException) as err:
        service.execute_knowledge_base_sql_service(None, 1, 'SELECT 1')
    assert err.value.status_code == 504 and disposed == []


def test_atomic_sql_does_not_block_health_or_loop_and_owns_session(source, monkeypatch):
    async def scenario():
        release = threading.Event()
        entered = threading.Event()
        main_thread = threading.get_ident()
        with Session(source) as db:
            def slow(worker_db, kb_id, sql):
                assert worker_db is not db and worker_db.get_bind() is db.get_bind()
                assert threading.get_ident() != main_thread
                entered.set()
                assert release.wait(1), 'SQL blocked the HTTP event loop'
                return SimpleNamespace(columns=['value'], rows=[{'value': 42}], row_count=1)
            monkeypatch.setattr(atomic, 'execute_knowledge_base_sql_service', slow)
            app = FastAPI()
            @app.get('/query')
            async def query():
                return await atomic.AutoBIAtomicService.execute_sql(db, 1, ExecuteSqlRequest(sql='SELECT 42'))
            @app.get('/health')
            async def health():
                return {'ok': True}
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://local') as client:
                pending = asyncio.create_task(client.get('/query'))
                try:
                    for _ in range(100):
                        if entered.is_set():
                            break
                        await asyncio.sleep(.005)
                    assert entered.is_set()
                    began = time.monotonic()
                    assert (await asyncio.wait_for(client.get('/health'), .2)).json() == {'ok': True}
                    assert time.monotonic() - began < .2
                finally:
                    release.set()
                assert (await pending).json()['rows'] == [{'value': 42}]
    asyncio.run(scenario())


def test_concurrency_is_bounded_and_cancellation_does_not_release_running_slot(source):
    async def scenario():
        release = threading.Event()
        started = [threading.Event() for _ in range(4)]
        def slow(db, index, sql):
            started[index].set()
            assert release.wait(2)
            return index
        with Session(source) as db:
            tasks = [asyncio.create_task(runtime.execute_knowledge_sql_async(db, i, 'SELECT 1', execute=slow)) for i in range(4)]
            try:
                for _ in range(100):
                    if all(event.is_set() for event in started):
                        break
                    await asyncio.sleep(.005)
                assert all(event.is_set() for event in started)
                tasks[0].cancel()
                await asyncio.sleep(0)
                with pytest.raises(HTTPException) as err:
                    await runtime.execute_knowledge_sql_async(db, 0, 'SELECT 1', execute=slow)
                assert err.value.status_code == 503
            finally:
                release.set()
                await asyncio.gather(*tasks, return_exceptions=True)
            for _ in range(100):
                if runtime.SQL_SLOTS.acquire(blocking=False):
                    runtime.SQL_SLOTS.release()
                    break
                await asyncio.sleep(.005)
            assert await runtime.execute_knowledge_sql_async(db, 0, 'SELECT 1', execute=lambda *a: 10) == 10
    asyncio.run(scenario())
