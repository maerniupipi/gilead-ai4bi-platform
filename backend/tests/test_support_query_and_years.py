from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch
import asyncio
from contextlib import asynccontextmanager
import json

from fastapi import HTTPException
import httpx
import pytest

from app.services.knowledge.data_source.query import prepare_query
from app.schemas.chat import ChatRequest
from app.services.chat.service import ChatService


@pytest.mark.parametrize('sql', [
    'SELECT * FROM some_table',
    'WITH a AS (SELECT 1 AS n) SELECT * FROM a',
    'SELECT 1 UNION ALL SELECT 2',
    'SELECT * FROM pg_catalog.pg_tables',
])
def test_default_console_limit(sql):
    prepared, applied = prepare_query(sql, 'postgres')
    assert 'LIMIT 100' in prepared and applied


@pytest.mark.parametrize('sql', ['SELECT 1 LIMIT 5', 'SELECT 1 LIMIT 1000'])
def test_explicit_limit_is_retained(sql):
    prepared, applied = prepare_query(sql, 'postgres')
    assert prepared == sql and not applied


@pytest.mark.parametrize('sql', [
    'DELETE FROM t', 'UPDATE t SET x=1', 'INSERT INTO t VALUES (1)',
    'DROP TABLE t', 'TRUNCATE t', 'CREATE TABLE t (id INT)',
    'WITH x AS (DELETE FROM t RETURNING *) SELECT * FROM x',
    'SELECT 1; DELETE FROM t', "SELECT * INTO t FROM s",
    "COPY t TO '/tmp/data'", 'EXPLAIN (ANALYZE) DELETE FROM t',
])
def test_console_rejects_writes(sql):
    with pytest.raises(HTTPException):
        prepare_query(sql, 'postgres')


@pytest.mark.parametrize('sql,dialect', [('SHOW TABLES','mysql'), ('DESCRIBE t','mysql'), ('EXPLAIN SELECT * FROM t','postgres'), ('SHOW ALL','postgres'), ('SHOW search_path','postgres'), ('VALUES (1), (2)','postgres')])
def test_metadata_queries_allowed(sql, dialect):
    assert prepare_query(sql, dialect)[0]


@pytest.mark.parametrize('prefix', ['-- query plan\n', '/* query plan */ ', '\n-- first\n/* second */\n'])
@pytest.mark.parametrize('options', ['', '(ANALYZE, BUFFERS) ', 'ANALYZE VERBOSE '])
def test_explain_with_leading_comments_is_bounded_and_adds_default_limit(prefix, options):
    prepared, applied = prepare_query(prefix + 'EXPLAIN ' + options + 'SELECT * FROM t', 'postgres')
    assert prepared.startswith(prefix.strip('\n'))
    assert 'LIMIT 100' in prepared and applied


def test_commented_explain_preserves_explicit_limit_and_rejects_writes():
    sql = '/* plan */ EXPLAIN (ANALYZE) SELECT * FROM t LIMIT 5'
    assert prepare_query(sql, 'postgres') == (sql, False)
    with pytest.raises(HTTPException):
        prepare_query('-- plan\nEXPLAIN (ANALYZE) DELETE FROM t', 'postgres')


@pytest.mark.parametrize('sql', [
    'SELECT a.bu, SUM(a.amount) FROM ims a JOIN bp b ON a.bu=b.bu GROUP BY a.bu',
    'SELECT bu FROM ims UNION SELECT bu FROM bp',
    'SELECT table_name FROM information_schema.tables',
    'SELECT bu, SUM(amount) FROM ims GROUP BY ROLLUP (bu)',
    'SELECT bu, SUM(amount) OVER (PARTITION BY city) FROM ims',
    "SELECT 'DELETE INSERT UPDATE' AS ordinary_text",
    'CALL readonly_report()',
])
def test_console_has_no_read_query_whitelist(sql):
    assert prepare_query(sql, 'postgres')[0]


def test_database_dialect_can_accept_read_syntax_unknown_to_sqlglot(monkeypatch):
    import sqlglot
    def unsupported(*args, **kwargs):
        raise sqlglot.errors.ParseError('dialect extension')
    monkeypatch.setattr(sqlglot, 'parse_one', unsupported)
    assert prepare_query('SELECT extension_read_syntax()', 'postgres') == ('SELECT extension_read_syntax()', False)






@pytest.mark.parametrize('operation', ['send','stream','text','tools'])
@pytest.mark.parametrize('failure', ['http','timeout','content'])
def test_model_gateway_is_called_once(monkeypatch, operation, failure):
    calls = []
    provider=SimpleNamespace(api_key='test', is_active=True, protocol='openai', base_url='https://model.test/v1', name='test')
    class Response:
        status_code = 503 if failure == 'http' else 200
        text = 'upstream unavailable'
        def json(self): return {'choices':[{'message':{'content':'function not supported error'}}]}
        async def aread(self): return self.text.encode()
        async def aiter_lines(self):
            yield 'data: ' + json.dumps({'choices':[{'delta':{'content':'function not supported error'}}]})
            yield 'data: [DONE]'
    class Client:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        def response(self):
            calls.append(1)
            if failure == 'timeout': raise httpx.ReadTimeout('timeout')
            return Response()
        async def post(self, *args, **kwargs): return self.response()
        @asynccontextmanager
        async def stream(self, *args, **kwargs): yield self.response()
    monkeypatch.setattr('app.services.chat.service.ModelProviderRepository.get_by_id', lambda *a: provider)
    monkeypatch.setattr('app.services.chat.service.httpx.AsyncClient', Client)
    async def run():
        req=ChatRequest(provider_id=1, model='test', message='hello')
        if operation=='send': return (await ChatService.send_chat(None,req)).content
        if operation=='stream': return ''.join([p async for p in ChatService.stream_chat(None,req)])
        if operation=='text': return ''.join([p async for p in ChatService.stream_chat_text_deltas(None,req)])
        return (await ChatService.chat_completion_openai(None,provider_id=1,model='test',messages=[])).get('content')
    if failure=='content':
        assert 'function not supported error' in asyncio.run(run())
    else:
        with pytest.raises(HTTPException) as error:
            asyncio.run(run())
        assert error.value.status_code == (503 if failure=='http' else 504)
    assert len(calls)==1


def test_console_executes_join_union_aggregate_in_readonly_session(monkeypatch):
    import sqlite3
    from app.services.knowledge.data_source import query
    calls = []
    class Cursor:
        def __init__(self, raw): self.raw = raw
        def __enter__(self): return self
        def __exit__(self, *args): self.raw.close()
        def execute(self, sql, args=None):
            calls.append((sql, args))
            if 'set_config(' not in sql:
                self.raw.execute(sql, args or ())
        @property
        def description(self): return self.raw.description
        def fetchmany(self, n): return self.raw.fetchmany(n)
    class Connection:
        def __init__(self):
            self.raw = sqlite3.connect(':memory:')
            self.raw.executescript('CREATE TABLE ims(bu TEXT,amount INT); CREATE TABLE bp(bu TEXT,target INT); INSERT INTO ims VALUES ("A",12),("A",13),("B",5); INSERT INTO bp VALUES ("A",20),("B",10);')
            self.readonly = False
        def set_session(self, **kwargs):
            assert kwargs == {'readonly': True, 'autocommit': False}
            self.readonly = True
        def cursor(self):
            assert self.readonly
            return Cursor(self.raw.cursor())
        def rollback(self): calls.append(('rollback', None)); self.raw.rollback()
        def close(self): self.raw.close()
    source = SimpleNamespace(database_type='postgresql', default_database='test')
    monkeypatch.setattr(query, 'get_data_source_service', lambda *args: source)
    monkeypatch.setattr(query, '_connect', lambda *args: Connection())
    result = query.execute_query(None,1,
        "SELECT i.bu, SUM(i.amount) AS total FROM ims i JOIN bp b ON i.bu=b.bu GROUP BY i.bu UNION ALL SELECT 'ALL', SUM(amount) FROM ims")
    assert result['rows'] == [{'bu':'A','total':25},{'bu':'B','total':5},{'bu':'ALL','total':30}]
    assert result['default_limit_applied'] is True
    assert 'LIMIT 100' in result['sql'] and calls[-1][0] == 'rollback'
