"""Observe one model operation without changing requests, retries or returned content."""
import asyncio
from contextlib import aclosing
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
import inspect
import logging
import time

model_call_context = ContextVar('model_call_context', default={})
_usage_sink = ContextVar('model_usage_sink', default=None)


@contextmanager
def collect_model_usage(sink):
    token = _usage_sink.set(sink)
    try:
        yield
    finally:
        _usage_sink.reset(token)


@contextmanager
def model_scope(**values):
    token = model_call_context.set({**model_call_context.get(), **values})
    try:
        yield
    finally:
        model_call_context.reset(token)


def _record(values):
    sink = _usage_sink.get()
    if sink is not None and isinstance(values.get("token_usage"), dict):
        sink.append({"model": values.get("model") or "", "usage": values["token_usage"]})
    from .invocation_capture import _capture
    from .observability import snapshot, log_context
    capture=_capture.get()
    record = snapshot({'trace_id': log_context.get().get('trace_id'), **values})
    if capture is not None:
        capture['execution'].setdefault('model_calls',[]).append(record)
    logging.getLogger('model.call').log(
        logging.ERROR if record.get('status') == 'failed' else logging.INFO,
        '模型请求结束 operation=%s model=%s status=%s elapsed_ms=%s first_content_ms=%s',
        record.get('operation'), record.get('model'), record.get('status'),
        record.get('elapsed_ms'), record.get('first_content_ms', record.get('first_chunk_ms')),
        extra={'support_data': record})


def observe_model_call(function):
    def metadata(args,kwargs):
        request=kwargs.get('chat_request') or (args[1] if len(args)>1 else None)
        return {'operation':function.__name__,'model':kwargs.get('model') or getattr(request,'model',None),
                'provider_id':kwargs.get('provider_id') or getattr(request,'provider_id',None),'started_at':int(time.time()*1000)}
    if inspect.isasyncgenfunction(function):
        @wraps(function)
        async def stream(*args,**kwargs):
            started=time.perf_counter(); values=metadata(args,kwargs); first=None
            values['status']='succeeded'
            try:
                async with aclosing(function(*args,**kwargs)) as source:
                    async for part in source:
                        if first is None: first=round((time.perf_counter()-started)*1000)
                        yield part
            except BaseException as error:
                values.update(status='stopped' if isinstance(error,(asyncio.CancelledError,GeneratorExit)) else 'failed',
                              error=str(getattr(error,'detail',error)),status_code=getattr(error,'status_code',None))
                raise
            finally:
                values.update(elapsed_ms=round((time.perf_counter()-started)*1000),first_chunk_ms=first)
                _record(values)
        return stream
    @wraps(function)
    async def call(*args,**kwargs):
        started=time.perf_counter(); values=metadata(args,kwargs); values['status']='succeeded'
        try:
            return await function(*args,**kwargs)
        except BaseException as error:
            values.update(status='stopped' if isinstance(error,asyncio.CancelledError) else 'failed',
                          error=str(getattr(error,'detail',error)),status_code=getattr(error,'status_code',None))
            raise
        finally:
            values['elapsed_ms']=round((time.perf_counter()-started)*1000)
            _record(values)
    return call
