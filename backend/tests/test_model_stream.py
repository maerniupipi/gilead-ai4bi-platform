import asyncio
import json
from contextlib import aclosing

import httpx
import pytest
from fastapi import HTTPException

from app.core.model_stream import complete_async, complete_sync, stream_completion
from app.services.chatbi.diagnostics import _capture


def packet(delta=None, **extra):
    return {'id': 'upstream-1', 'choices': [{'index': 0, 'delta': delta or {}, **extra}]}


def sse(*events, done=True):
    data = ''.join('data: ' + json.dumps(event, ensure_ascii=False) + '\n\n' for event in events)
    return (data + ('data: [DONE]\n\n' if done else '')).encode()


@pytest.fixture
def wire(monkeypatch):
    requests = []
    state = {'body': sse(packet({'content': '完整回答'}, finish_reason='stop')), 'status': 200}
    original_async, original_sync = httpx.AsyncClient, httpx.Client
    def respond(request):
        requests.append(json.loads(request.content))
        if state.get('error'):
            raise state['error']
        return httpx.Response(state['status'], content=state['body'],
                              headers={'Content-Type': 'text/event-stream', 'x-request-id': 'provider-request-1'})
    transport = httpx.MockTransport(respond)
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kwargs: original_async(transport=transport, **kwargs))
    monkeypatch.setattr(httpx, 'Client', lambda **kwargs: original_sync(transport=transport, **kwargs))
    return requests, state


def test_aggregates_stream_and_records_provider_id_timing_usage_and_one_request(wire):
    requests, state = wire
    usage = {'prompt_tokens': 10, 'completion_tokens': 3, 'total_tokens': 13}
    state['body'] = sse(packet({'role': 'assistant'}), packet({'reasoning_content': '内部思考'}),
                        packet({'content': '第一段'}), packet({'content': '第二段'}, finish_reason='stop'),
                        {'choices': [], 'usage': usage})
    collector = {'execution': {}, 'invocations': []}
    token = _capture.set(collector)
    try:
        async def run():
            return [event async for event in stream_completion('https://model.test/chat/completions',
                {'model': 'test', 'messages': [], 'stream': True}, {}, provider_id=12, operation='regression')]
        result = asyncio.run(run())
    finally:
        _capture.reset(token)
    assert ''.join((c.get('delta') or {}).get('content') or '' for e in result for c in e.get('choices', [])) == '第一段第二段'
    assert result[-1]['usage'] == usage
    assert len(requests) == len(collector['invocations']) == 1
    assert requests[0]['stream'] is True
    stats = collector['execution']['model_calls']
    assert len(stats) == 1 and stats[0]['status'] == 'succeeded'
    assert stats[0]['call_id'] == collector['invocations'][0]['id']
    assert stats[0]['token_usage'] == usage and stats[0]['chunk_count'] == 5
    assert stats[0]['content_chunks'] == 2 and stats[0]['reasoning_chars'] == 4
    assert stats[0]['provider_request_id'] == 'provider-request-1'
    assert stats[0]['first_chunk_ms'] <= stats[0]['first_content_ms'] <= stats[0]['elapsed_ms']
    assert stats[0]['finished_at'] >= stats[0]['started_at']


def test_nonstream_tool_message_is_preserved_without_thinking_or_first_token_estimates(wire):
    requests, state = wire
    message = {'content': None, 'role': 'assistant', 'tool_calls': [{'id': 'call-1', 'type': 'function',
        'function': {'name': 'lookup', 'arguments': '{"city":"上海"}'}}]}
    state['body'] = json.dumps({'choices': [{'message': message, 'finish_reason': 'tool_calls'}]}).encode()
    collector = {'execution': {}, 'invocations': []}
    token = _capture.set(collector)
    try:
        result = asyncio.run(complete_async('https://model.test/chat/completions', {'model': 'test'}, {}))
    finally:
        _capture.reset(token)
    assert result['choices'][0]['message'] == message
    assert len(requests) == 1 and requests[0]['stream'] is False
    stats = collector['execution']['model_calls'][0]
    assert stats['first_chunk_ms'] is stats['first_content_ms'] is None
    assert stats['response_received_ms'] <= stats['elapsed_ms']
    assert stats['tool_calls_count'] == 1


@pytest.mark.parametrize('failure', ['http', 'timeout', 'network', 'partial', 'malformed', 'error_event'])
def test_failures_never_retry_or_accept_partial_output(wire, failure):
    requests, state = wire
    if failure == 'http': state['status'], state['body'] = 503, b'provider unavailable'
    elif failure == 'timeout': state['error'] = httpx.ReadTimeout('late')
    elif failure == 'network': state['error'] = httpx.ConnectError('offline')
    elif failure == 'partial': state['body'] = sse(packet({'content': 'incomplete SQL'}), done=False)
    elif failure == 'malformed': state['body'] = b'data: not-json\n\n'
    else: state['body'] = sse({'error': {'message': 'provider failed'}})
    collector = {'execution': {}, 'invocations': []}
    token = _capture.set(collector)
    try:
        with pytest.raises((HTTPException, httpx.ConnectError)):
            async def run():
                return [event async for event in stream_completion('https://model.test/chat/completions', {'model': 'test'}, {})]
            asyncio.run(run())
    finally:
        _capture.reset(token)
    assert len(requests) == 1
    stats = collector['execution']['model_calls']
    assert len(stats) == 1 and stats[0]['status'] == 'failed' and stats[0]['attempts'] == 1
    assert stats[0]['error_type'] and stats[0]['error']


def test_stopping_consumer_closes_upstream_and_records_one_stopped_call(wire):
    async def run():
        collector = {'execution': {}, 'invocations': []}
        token = _capture.set(collector)
        try:
            async with aclosing(stream_completion('https://model.test/chat/completions', {'model': 'test'}, {})) as source:
                assert await anext(source)
            return collector['execution']['model_calls']
        finally:
            _capture.reset(token)
    calls = asyncio.run(run())
    assert len(calls) == 1 and calls[0]['status'] == 'stopped'


def test_sync_intermediate_workers_keep_nonstream_contract(wire):
    requests, state = wire
    state['body'] = json.dumps({'choices':[{'message':{'content':'完整回答'}}]}).encode()
    assert complete_sync('https://model.test/chat/completions', {'model': 'test'}, {})['choices'][0]['message']['content'] == '完整回答'
    assert len(requests) == 1 and requests[0]['stream'] is False


def test_sse_multiline_json_and_comments_are_supported(wire):
    _, state = wire
    state['body'] = b': keepalive\n\ndata: {"choices":\ndata: [{"delta":{"content":"ok"},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n'
    async def run():
        return [event async for event in stream_completion('https://model.test/chat/completions', {'model': 'test'}, {})]
    result = asyncio.run(run())
    assert result[0]['choices'][0]['delta']['content'] == 'ok'
