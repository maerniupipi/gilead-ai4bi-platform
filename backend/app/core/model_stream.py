"""Single-attempt model requests with streaming or complete-response diagnostics.

Transport stays independent of platform client, workflows and laboratory business logic.
An interrupted stream is an error; partial SQL/JSON must never become a result.
"""
import asyncio
from contextlib import aclosing
import json
import logging
import time
from uuid import uuid4

import httpx
from fastapi import HTTPException

from .http_clients import model_client
from .model_observation import _record, model_call_context

logger = logging.getLogger('model.call')


class ModelCall:
    def __init__(self, payload, *, operation, provider_id=None, provider=None):
        self.started = time.perf_counter()
        self.data = {**model_call_context.get(), 'call_id': str(uuid4()), 'operation': operation,
                     'model': payload.get('model'), 'provider_id': provider_id,
                     'provider': provider, 'stream': bool(payload.get('stream')), 'attempts': 1,
                     'reasoning_effort': payload.get('reasoning_effort'),
                     'enable_thinking': payload.get('enable_thinking'),
                     'started_at': int(time.time() * 1000), 'status': 'running',
                     'first_chunk_ms': None, 'first_content_ms': None,
                     'first_reasoning_ms': None, 'chunk_count': 0, 'content_chunks': 0,
                     'content_chars': 0, 'reasoning_chars': 0, 'token_usage': None}
        self.buffer = []
        self.terminal = False
        self.done = False
        self.message = {'role': 'assistant', 'content': ''}
        self.tool_calls = {}
        self.function_call = {}
        self.response = {}
        # Store the actual provider payload once and link timing records by ID.
        from .invocation_capture import capture_invocation
        capture_invocation('model', payload, id=self.data['call_id'], operation=operation,
                           provider_id=provider_id, provider=provider, **model_call_context.get())
        logger.info('模型请求开始 operation=%s model=%s', operation, payload.get('model'),
                    extra={'support_data': dict(self.data)})

    def elapsed(self):
        return round((time.perf_counter() - self.started) * 1000)

    def line(self, line):
        """Accept SSE comments/multiline events; tolerate single-line gateways."""
        if line.startswith('data:'):
            self.buffer.append(line[5:].lstrip())
            value = '\n'.join(self.buffer)
            if value == '[DONE]':
                self.buffer.clear()
                self.terminal = True
                self.done = True
                return None
            try:
                event = json.loads(value)
            except ValueError:
                return None  # The remainder can arrive in another data line.
            self.buffer.clear()
            return self.event(event)
        if not line and self.buffer:
            raise HTTPException(502, '模型流式响应包含无效 JSON')
        return None

    def event(self, event):
        if not isinstance(event, dict):
            raise HTTPException(502, '模型流式响应格式错误')
        if event.get('error'):
            error = event['error']
            message = error.get('message') if isinstance(error, dict) else str(error)
            raise HTTPException(502, f'模型流式调用失败: {message}')
        self.data['chunk_count'] += 1
        if self.data['first_chunk_ms'] is None:
            self.data['first_chunk_ms'] = self.elapsed()
        for key in ('id', 'model', 'created', 'system_fingerprint'):
            if key in event:
                self.response[key] = event[key]
        if isinstance(event.get('usage'), dict):
            self.data['token_usage'] = event['usage']
        for choice in event.get('choices') or []:
            if choice.get('index', 0) != 0:
                continue
            delta = choice.get('delta')
            if not isinstance(delta, dict):
                raise HTTPException(502, '模型未返回流式 delta 数据')
            if delta.get('role'):
                self.message['role'] = delta['role']
            content = delta.get('content') or ''
            if not isinstance(content, str):
                raise HTTPException(502, '模型流式文本格式错误')
            if content:
                if self.data['first_content_ms'] is None:
                    self.data['first_content_ms'] = self.elapsed()
                    logger.info('模型首段内容返回 model=%s elapsed_ms=%s',
                                self.data['model'], self.data['first_content_ms'],
                                extra={'support_data': dict(self.data)})
                self.data['content_chunks'] += 1
                self.data['content_chars'] += len(content)
                self.message['content'] += content
            reasoning = delta.get('reasoning_content') or delta.get('reasoning') or ''
            if isinstance(reasoning, str) and reasoning:
                if self.data['first_reasoning_ms'] is None:
                    self.data['first_reasoning_ms'] = self.elapsed()
                self.data['reasoning_chars'] += len(reasoning)
            if delta.get('refusal'):
                self.message['refusal'] = self.message.get('refusal', '') + delta['refusal']
            for tool in delta.get('tool_calls') or []:
                index = tool.get('index', 0)
                target = self.tool_calls.setdefault(index, {'id': '', 'type': 'function',
                                                           'function': {'name': '', 'arguments': ''}})
                if tool.get('id'):
                    target['id'] = tool['id']
                if tool.get('type'):
                    target['type'] = tool['type']
                for key in ('name', 'arguments'):
                    target['function'][key] += (tool.get('function') or {}).get(key) or ''
            for key, value in (delta.get('function_call') or {}).items():
                self.function_call[key] = self.function_call.get(key, '') + (value or '')
            if choice.get('finish_reason') is not None:
                self.data['finish_reason'] = choice['finish_reason']
                self.terminal = True
        return event

    def complete(self):
        if self.buffer or not self.terminal:
            raise HTTPException(502, '模型流式连接提前结束，未收到完成标记')
        self.data['status'] = 'succeeded'

    def finish(self, error=None):
        if error is not None:
            self.data.update(status='stopped' if isinstance(error, (asyncio.CancelledError, GeneratorExit)) else 'failed',
                             error=str(getattr(error, 'detail', error)),
                             status_code=getattr(error, 'status_code', None),
                             error_type=type(error).__name__)
        self.data.update(finished_at=int(time.time() * 1000), elapsed_ms=self.elapsed())
        preview = self.message.get('content') or ''
        self.data.setdefault('response_preview', str(preview)[:2000])
        self.data['tool_calls_count'] = len(self.tool_calls)
        _record(self.data)


def streaming_payload(payload):
    # Keep the provider's existing streaming contract. Usage is recorded when
    # returned; asking for extra options is not required for timing evidence.
    return {**payload, 'stream': True}


async def stream_completion(url, payload, headers, *, timeout=120.0, operation='chat',
                            provider_id=None, provider=None):
    """Yield decoded chunks. Never reconnect, retry, or fall back to non-streaming."""
    payload = streaming_payload(payload)
    state = ModelCall(payload, operation=operation, provider_id=provider_id, provider=provider)
    error = None
    try:
        async with model_client(timeout) as client:
            async with client.stream('POST', url, json=payload, headers=headers) as response:
                state.data['http_status'] = response.status_code
                state.data['provider_request_id'] = getattr(response, 'headers', {}).get('x-request-id')
                state.data['response_headers_ms'] = state.elapsed()
                if response.status_code != 200:
                    body = await response.aread()
                    raise HTTPException(response.status_code, '模型API调用失败: ' + body.decode('utf-8', 'replace'))
                async for line in response.aiter_lines():
                    event = state.line(line)
                    if event is not None:
                        yield event
                    if state.done:
                        break
                state.complete()
    except httpx.TimeoutException as exc:
        error = HTTPException(504, '请求超时')
        raise error from exc
    except BaseException as exc:
        error = exc
        raise
    finally:
        state.finish(error)


def _complete_result(state, response):
    try:
        data = response.json()
    except ValueError as exc:
        state.data['response_preview'] = getattr(response, 'text', '')[:2000]
        raise HTTPException(502, '模型响应不是有效 JSON') from exc
    choices = data.get('choices') if isinstance(data, dict) else None
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict) or not isinstance(choices[0].get('message'), dict):
        state.data['response_preview'] = getattr(response, 'text', '')[:2000]
        raise HTTPException(502, '模型响应缺少完整 message')
    state.message = data['choices'][0]['message']
    if state.message.get('content') is not None and not isinstance(state.message['content'], str):
        raise HTTPException(502, '模型响应正文不是文本')
    state.data.update(status='succeeded', response_received_ms=state.elapsed(),
                      content_chars=len(state.message.get('content') or ''),
                      token_usage=data.get('usage'), finish_reason=data['choices'][0].get('finish_reason'))
    state.tool_calls = {i: tool for i, tool in enumerate(state.message.get('tool_calls') or [])}
    return data


def complete_payload(payload):
    result = {**payload, 'stream': False}
    result.pop('stream_options', None)
    return result


async def complete_async(url, payload, headers, *, timeout=120.0, operation='chat', provider_id=None, provider=None):
    """Intermediate calls keep their non-streaming provider contract."""
    payload = complete_payload(payload)
    state = ModelCall(payload, operation=operation, provider_id=provider_id, provider=provider)
    error = None
    try:
        async with model_client(timeout) as client:
            response = await client.post(url, json=payload, headers=headers)
            state.data['http_status'] = response.status_code
            state.data['provider_request_id'] = getattr(response, 'headers', {}).get('x-request-id')
            if response.status_code != 200:
                raise HTTPException(response.status_code, '模型API调用失败: ' + response.text)
            return _complete_result(state, response)
    except httpx.TimeoutException as exc:
        error = HTTPException(504, '请求超时')
        raise error from exc
    except BaseException as exc:
        error = exc
        raise
    finally:
        state.finish(error)


def complete_sync(url, payload, headers, *, timeout=120.0, operation='chat', provider_id=None, provider=None):
    """Synchronous intermediate calls also execute once without streaming."""
    payload = complete_payload(payload)
    state = ModelCall(payload, operation=operation, provider_id=provider_id, provider=provider)
    error = None
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(url, json=payload, headers=headers)
            state.data['http_status'] = response.status_code
            state.data['provider_request_id'] = getattr(response, 'headers', {}).get('x-request-id')
            if response.status_code != 200:
                raise HTTPException(response.status_code, '模型API调用失败: ' + response.text)
            return _complete_result(state, response)
    except httpx.TimeoutException as exc:
        error = HTTPException(504, '请求超时')
        raise error from exc
    except BaseException as exc:
        error = exc
        raise
    finally:
        state.finish(error)
