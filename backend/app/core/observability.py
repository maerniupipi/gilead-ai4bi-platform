"""Request correlation and credential-only redaction shared by diagnostics/logs."""
from contextvars import ContextVar
from datetime import date, datetime
from decimal import Decimal
import json
import logging
import re
import time
import uuid

log_context = ContextVar('support_log_context', default={})
_SECRET_KEYS = re.compile(r'(^|[_-])(password|passwd|secret|token|(?:api|access)[_-]?key|authorization|cookie|signature|sig)($|[_-])', re.I)


def redact_text(value):
    value = str(value)
    value = re.sub(r'(Bearer\s+)[A-Za-z0-9._~+/=-]+', r'\1***', value, flags=re.I)
    value = re.sub(r'(://[^\s/:]+:)[^@\s]+@', r'\1***@', value)
    return re.sub(r'''((?:["'])?(?:password|passwd|api_key|access_token|token|secret|sig)(?:["'])?\s*[=:]\s*)(?:"[^"]*"|'[^']*'|[^\s&,;]+)''', r'\1***', value, flags=re.I)


def snapshot(value, _seen=None):
    seen = set() if _seen is None else _seen
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (dict, list, tuple, set)):
        if id(value) in seen:
            return '[circular reference]'
        seen.add(id(value))
        try:
            if isinstance(value, dict):
                return {str(key): '***' if _SECRET_KEYS.search(str(key)) and str(key).lower() not in {'token_usage','token_count','token_counts','token_total'} else snapshot(item, seen) for key, item in value.items()}
            return [snapshot(item, seen) for item in value]
        finally:
            seen.remove(id(value))
    return redact_text(value)


def bind_context(**values):
    current = log_context.get()
    updates = {key:value for key,value in values.items() if value is not None}
    if current.get('request_id'):
        # One dictionary is unique to this HTTP request and intentionally shared
        # with Starlette's downstream tasks, including the streaming producer.
        current.update(updates)
    else:
        log_context.set({**current,**updates})


class RequestLogMiddleware:
    """Pure ASGI middleware keeps context alive through streaming responses."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        headers = dict(scope.get('headers') or [])
        supplied = headers.get(b'x-request-id', b'').decode('utf-8', 'replace')
        request_id = supplied if re.fullmatch(r'[\w.-]{1,64}', supplied) else str(uuid.uuid4())
        token = log_context.set({'request_id':request_id, 'path':scope['path'], 'method':scope['method']})
        started = time.perf_counter()
        status = 500
        body_parts = []
        body_size = 0
        body_truncated = False
        async def read():
            nonlocal body_size, body_truncated
            message = await receive()
            if message['type'] == 'http.request':
                chunk = message.get('body', b'')
                remaining = max(0,1048576-body_size)
                body_parts.append(chunk[:remaining])
                body_size += min(remaining,len(chunk))
                body_truncated = body_truncated or len(chunk)>remaining
            return message
        async def write(message):
            nonlocal status
            if message['type'] == 'http.response.start':
                status = message['status']
                message = {**message, 'headers':[*message.get('headers', []), (b'x-request-id',request_id.encode())]}
            await send(message)
        try:
            await self.app(scope, read, write)
        except BaseException:
            logging.getLogger('http.request').exception('请求执行中断')
            raise
        finally:
            if not scope['path'].startswith('/api/system-logs') and scope['path'] not in {'/live','/health'}:
                body = None
                try:
                    body = json.loads(b''.join(body_parts)) if body_parts else None
                except (ValueError, UnicodeDecodeError):
                    body = '[non-JSON body]'
                logging.getLogger('http.request').log(logging.ERROR if status >= 500 else logging.WARNING if status >= 400 else logging.INFO,
                    '%s %s → %s (%d ms)', scope['method'], scope['path'], status, (time.perf_counter()-started)*1000,
                    extra={'support_data':{'status_code':status,'duration_ms':round((time.perf_counter()-started)*1000),'request_body':snapshot(body),'request_body_truncated':body_truncated}})
            log_context.reset(token)
