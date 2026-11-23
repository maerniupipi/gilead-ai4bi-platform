import asyncio
import json
import logging
import time
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.observability import log_context, snapshot
from app.models.system_log import SystemLog
from app.models.chatbi import ChatBIMessageDiagnostic
from app.services.system_logs import DatabaseLogHandler, cleanup_logs, list_logs, RETENTION_MS
from app.services.knowledge.data_source import query as data_query
from tests.service_test_helpers import service_api, api, post_chat, events


@pytest.fixture
def log_db():
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    SystemLog.__table__.create(engine)
    factory=sessionmaker(engine)
    yield factory
    engine.dispose()


def row(at, **values):
    return SystemLog(created_at=at,level='INFO',service='test',instance='local',logger='test',message='sales 1234.567890',data={},**values)


def test_retention_boundary_and_batching(log_db):
    now=int(time.time()*1000)
    with log_db() as db:
        db.add_all([row(now-RETENTION_MS-1),row(now-RETENTION_MS-2),row(now-RETENTION_MS),row(now)])
        db.commit()
        assert cleanup_logs(db,now_ms=now,batch_size=1)==1
        assert cleanup_logs(db,now_ms=now,batch_size=1)==1
        assert cleanup_logs(db,now_ms=now,batch_size=1)==0
        assert db.query(SystemLog).count()==2


def test_credentials_are_redacted_but_business_values_are_preserved():
    assert snapshot({'authorization':'Bearer secret','password':'password','api_key':'secret','rows':[{'value':'1234.567890','user_id':'1234','year':2026}]})=={
        'authorization':'***','password':'***','api_key':'***','rows':[{'value':'1234.567890','user_id':'1234','year':2026}]}
    assert snapshot({'token_usage':123,'total_tokens':456})['total_tokens']==456
    assert 'password@' not in snapshot('postgres://user:password@host/db')


def test_async_writer_preserves_request_context_and_exception(log_db):
    handler=DatabaseLogHandler(log_db)
    token=log_context.set({'request_id':'request-123','conversation_id':'session-123','user_id':'U1'})
    try:
        try: raise RuntimeError('SQL failed for amount 1234.567890')
        except RuntimeError:
            import sys
            record=logging.LogRecord('test.worker',logging.ERROR,__file__,1,'failed amount %s',('1234.567890',),sys.exc_info())
            handler.handle(record)
        handler.flush()
        with log_db() as db:
            result=list_logs(db,user_id='U1',request_id='request-123',keyword='1234.567890')
            assert result['total']==1
            saved=result['items'][0]
            assert saved['conversation_id']=='session-123'
            assert 'RuntimeError' in saved['exception']
            assert '1234.567890' in saved['message']
    finally:
        log_context.reset(token)
        handler.close()


def test_original_body_actual_inputs_trace_and_failure_are_saved_per_turn(service_api, monkeypatch):
    from app.services.agent_app import workflow_engine
    from app.routers.chatbi.conversations import router as conversation_router
    service_api.api.client.app.include_router(conversation_router)
    trace=str(uuid4())
    async def fail(*args,**kwargs):
        yield {'type':'trace_id','trace_id':trace}
        raise RuntimeError('failed SQL amount 1234.567890')
    monkeypatch.setattr(workflow_engine,'run_agent_workflow_stream',fail)
    response=post_chat(service_api,inputs={'business_month':'2026-11','metadata':{'region':'configured'}})
    assert response.status_code==200
    first=events(response)[0]
    with service_api.api.factory() as db:
        saved=db.get(ChatBIMessageDiagnostic,first['message_id'])
        assert saved.request['body']['inputs']['metadata']['region']=='configured'
        actual=saved.invocations[0]['inputs']
        assert actual['metadata']=={'region':'configured'}
        assert actual['user_id']=='admin123'
        assert saved.execution['status']=='failed'
        assert '1234.567890' in saved.execution['original_error']
        assert trace in [item['trace_id'] for item in saved.traces]
        assert '***'==saved.request['headers']['authorization']
    detail=service_api.api.client.get('/api/chatbi/conversations/'+first['conversation_id'],headers={'X-User-Id':'1'})
    assert detail.status_code==200
    assert detail.json()['data']['messages'][0]['diagnostics']['execution']['status']=='failed'


def test_console_uses_readonly_transaction_and_preserves_duplicate_columns(monkeypatch):
    source=SimpleNamespace(database_type='postgresql',default_database='db',password='encrypted')
    calls=[]
    class Cursor:
        description=[('value',),('value',),('date',)]
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def execute(self,*args): calls.append(args)
        def fetchmany(self,count): return [(Decimal('1234.567890'),None,date(2026,11,13))]
    class Connection:
        def cursor(self): return Cursor()
        def set_session(self,**kwargs): calls.append(kwargs)
        def rollback(self): calls.append('rollback')
        def close(self): pass
    monkeypatch.setattr(data_query,'get_data_source_service',lambda *args:source)
    monkeypatch.setattr(data_query,'_connect',lambda *args:Connection())
    result=data_query.execute_query(None,1,'SELECT 1',schema='odd"schema')
    assert calls[0]=={'readonly':True,'autocommit':False}
    assert calls[-1]=='rollback'
    assert result['rows']==[{'value':'1234.567890','value_2':None,'date':'2026-11-13'}]
    assert result['sql']=='SELECT 1 LIMIT 100'
    assert any(len(call)==2 and call[1]==('"odd""schema"',) for call in calls if isinstance(call,tuple))



def test_request_log_context_is_shared_with_downstream_tasks_without_cross_request_leak(monkeypatch):
    from app.core.observability import RequestLogMiddleware, bind_context
    observed=[]
    class Capture(logging.Handler):
        def emit(self,record): observed.append(dict(log_context.get()))
    logger=logging.getLogger('http.request')
    monkeypatch.setattr(logger,'level',logging.INFO)
    handler=Capture();logger.addHandler(handler)
    async def app(scope,receive,send):
        async def downstream():
            bind_context(message_id=scope['path'].strip('/'),user_id=scope['path'].strip('/'))
            await asyncio.sleep(0)
            await send({'type':'http.response.start','status':200,'headers':[]})
            await send({'type':'http.response.body','body':b'ok'})
        await asyncio.create_task(downstream())
    middleware=RequestLogMiddleware(app)
    async def request(name):
        async def receive(): return {'type':'http.request','body':b''}
        async def send(message): pass
        await middleware({'type':'http','path':'/'+name,'method':'POST','headers':[(b'x-request-id',name.encode())]},receive,send)
    async def run(): await asyncio.gather(request('first'),request('second'))
    try: asyncio.run(run())
    finally: logger.removeHandler(handler)
    assert {row['request_id']:row['message_id'] for row in observed}=={'first':'first','second':'second'}


def test_model_observation_closes_cancelled_stream_and_records_once():
    import asyncio
    from app.core.model_observation import observe_model_call
    from app.services.chatbi.diagnostics import _capture
    closed = []
    @observe_model_call
    async def source():
        try:
            yield 'first'
            yield 'second'
        finally:
            closed.append(True)
    async def scenario():
        collector = {'execution': {}}
        token = _capture.set(collector)
        try:
            stream = source()
            assert await anext(stream) == 'first'
            await stream.aclose()
            assert closed == [True]
            calls = collector['execution']['model_calls']
            assert len(calls) == 1
            assert calls[0]['status'] == 'stopped'
            assert calls[0]['first_chunk_ms'] is not None
        finally:
            _capture.reset(token)
    asyncio.run(scenario())
