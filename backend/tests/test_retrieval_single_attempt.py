"""Failure requests must not be repeated by application or provider SDK policy."""
from types import SimpleNamespace

import grpc
import pytest
from pymilvus.decorators import retry_on_rpc_failure

from app.services.knowledge import vector_service
from app.services.knowledge.azure_search_service import AzureAISearchService
from app.services.knowledge.es_service import ElasticsearchService


@pytest.mark.parametrize('failure', [TimeoutError('timeout'), RuntimeError('resource_exhausted')])
def test_milvus_application_does_not_repeat_failed_operations(failure):
    calls = []
    service = vector_service.MilvusService({'host':'offline', 'port':19530})
    def failed(**kwargs):
        calls.append(kwargs)
        raise failure
    with pytest.raises(type(failure)):
        service._call_with_timeout('search', failed)
    assert len(calls) == 1


def test_type_error_is_not_reinvoked_without_timeout():
    calls = []
    service = vector_service.MilvusService({'host':'offline', 'port':19530})
    def failed(timeout=None, **kwargs):
        calls.append(timeout)
        raise TypeError('timeout conversion failed in provider')
    with pytest.raises(TypeError):
        service._call_with_timeout('search', failed)
    assert len(calls) == 1


def test_milvus_sdk_rpc_policy_does_not_repeat_unavailable(monkeypatch):
    calls = []
    class Offline(grpc.RpcError):
        def code(self): return grpc.StatusCode.UNAVAILABLE
        def details(self): return 'offline'
    @retry_on_rpc_failure()
    def failed(service, **kwargs):
        calls.append(kwargs)
        raise Offline()
    service = vector_service.MilvusService({'host':'offline', 'port':19530})
    monkeypatch.setattr('pymilvus.decorators.time.sleep', lambda _: pytest.fail('SDK must not retry'))
    with pytest.raises(Exception) as failure:
        service._call_with_timeout('search', failed, SimpleNamespace())
    assert not isinstance(failure.value, AssertionError)
    assert len(calls) == 1
    assert calls[0]['retry_times'] == 0


def test_milvus_sdk_collection_metadata_gets_single_attempt_options(monkeypatch):
    calls = []
    monkeypatch.setattr(vector_service, 'Collection', lambda *args, **kwargs: calls.append(kwargs) or object())
    service = vector_service.MilvusService({'host':'offline', 'port':19530})
    service._collection('example')
    assert calls[0]['retry_times'] == 0 and calls[0]['retry_on_rate_limit'] is False


def test_azure_sdk_clients_have_no_automatic_retry():
    service = AzureAISearchService({'host':'https://offline.invalid', 'password':'test'})
    for client in (service.get_index_client(), service.get_search_client('example')):
        policy = client._client._config.retry_policy
        assert policy.total_retries == policy.connect_retries == policy.read_retries == policy.status_retries == 0
        client.close()


def test_elasticsearch_transport_has_no_automatic_retry():
    service = ElasticsearchService({'host':'http://offline.invalid:9200'})
    client = service.get_client()
    assert client._max_retries == 0 and client._retry_on_timeout is False
    service.close()
