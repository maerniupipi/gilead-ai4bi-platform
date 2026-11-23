import pytest
import requests
from app.services.knowledge.embedding_service import EmbeddingService
from app.services.chatbi.diagnostics import _capture


@pytest.mark.parametrize('failure', ['network', 'timeout', 'http', None])
def test_embedding_model_is_called_once_and_records_timing_even_with_old_retry_settings(monkeypatch, failure):
    service = EmbeddingService({'provider': 'dashscope', 'api_key': 'test-key',
        'model': 'text-embedding-v4', 'dimension': 3, 'base_url': 'https://model.test/embeddings',
        'retry_attempts': 3, 'retry_backoff_seconds': 1})
    calls = []
    class Response:
        status_code = 503 if failure == 'http' else 200
        def json(self):
            return {'data': [{'index': 0, 'embedding': [0.1, 0.2, 0.3]}], 'usage': {'total_tokens': 2}}
    def post(*args, **kwargs):
        calls.append(kwargs['json'])
        if failure == 'network': raise requests.exceptions.ConnectionError('offline')
        if failure == 'timeout': raise requests.exceptions.Timeout('late')
        return Response()
    monkeypatch.setattr('requests.Session.post', lambda self, *args, **kwargs: post(*args, **kwargs))
    collector = {'execution': {}, 'invocations': []}
    token = _capture.set(collector)
    try:
        if failure:
            with pytest.raises((requests.exceptions.RequestException, RuntimeError)):
                service.get_embeddings(['hello'])
        else:
            assert service.get_embeddings(['hello']) == [[0.1, 0.2, 0.3]]
    finally:
        _capture.reset(token)
    assert len(calls) == 1 and 'stream' not in calls[0]
    record = collector['execution']['model_calls'][0]
    assert record['operation'] == 'embedding' and record['input_count'] == 1
    assert record['status'] == ('failed' if failure else 'succeeded')
    assert record['elapsed_ms'] >= 0 and record['attempts'] == 1
