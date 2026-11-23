"""Storage failure regression tests; every external client is a local fake."""
from types import SimpleNamespace

import pytest

from app.services.knowledge import vector_service
from app.services.knowledge.azure_search_service import AzureAISearchService
from app.services.knowledge.es_service import ElasticsearchService
from app.services.vector_store.providers import AzureAISearchProvider, MilvusProvider


def test_milvus_does_not_replay_an_insert_after_an_uncertain_timeout(monkeypatch):
    rows = []

    class FakeCollection:
        def __init__(self, *args, **kwargs):
            pass

        def insert(self, data, timeout=None):
            rows.extend(zip(*data))
            raise TimeoutError("server committed the insert; response timed out")

    monkeypatch.setattr(vector_service, "Collection", FakeCollection)
    svc = vector_service.MilvusService({"host": "offline", "port": 19530})
    monkeypatch.setattr(svc, "connect", lambda: None)

    assert not svc.insert_vectors("v_kb1", [{
        "kb_id": 1, "field_type": "table_value", "field_table": "sales",
        "field_code": "sales&&city", "field_value": "上海", "embedding": [1.0, 0.0],
    }])
    assert len(rows) == 1


def test_milvus_failed_flush_is_not_retried_or_reinserted(monkeypatch):
    calls = {"insert": 0, "flush": 0}

    class FakeCollection:
        def __init__(self, *args, **kwargs):
            pass

        def insert(self, data, timeout=None):
            calls["insert"] += 1

        def flush(self, timeout=None):
            calls["flush"] += 1
            if calls["flush"] == 1:
                raise TimeoutError("flush response timed out")

    monkeypatch.setattr(vector_service, "Collection", FakeCollection)
    svc = vector_service.MilvusService({"host": "offline", "port": 19530})
    monkeypatch.setattr(svc, "connect", lambda: None)

    assert not svc.insert_vectors("v_kb1", [{
        "kb_id": 1, "field_type": "table_value", "field_table": "sales",
        "field_code": "sales&&city", "field_value": "上海", "embedding": [1.0, 0.0],
    }])
    assert calls == {"insert": 1, "flush": 1}


@pytest.fixture
def azure(monkeypatch):
    svc = AzureAISearchService({"host": "https://offline.invalid", "password": "fake"})
    monkeypatch.setattr(svc, "index_exists", lambda _: True)
    return svc


@pytest.mark.parametrize("status_code", [403, 429, 503, None])
def test_azure_index_lookup_errors_are_not_treated_as_missing(status_code):
    svc = AzureAISearchService({"host": "https://offline.invalid", "password": "fake"})
    error = RuntimeError("index lookup failed")
    error.status_code = status_code

    def get_index(_):
        raise error

    svc._index_client = SimpleNamespace(get_index=get_index)
    with pytest.raises(RuntimeError, match="index lookup failed"):
        svc.index_exists("v_kb1")

    error.status_code = 404
    assert svc.index_exists("v_kb1") is False


@pytest.mark.parametrize("results", [[], [SimpleNamespace(succeeded=False)], None])
def test_azure_delete_ids_requires_success_for_every_document(azure, monkeypatch, results):
    monkeypatch.setattr(azure, "get_search_client", lambda _: SimpleNamespace(
        delete_documents=lambda **kwargs: results,
    ))
    assert azure.delete_documents("v_kb1", ["id-1"]) is False


def test_azure_delete_ids_batches_large_stale_sets(azure, monkeypatch):
    batches = []

    def delete_documents(documents):
        batches.append(documents)
        return [SimpleNamespace(succeeded=True) for _ in documents]

    monkeypatch.setattr(azure, "get_search_client", lambda _: SimpleNamespace(delete_documents=delete_documents))
    assert azure.delete_documents("v_kb1", [str(i) for i in range(2001)])
    assert [len(batch) for batch in batches] == [1000, 1000, 1]


@pytest.mark.parametrize("filter_expr", [None, "field_type eq 'sql_sample'"])
def test_azure_drains_first_pages_without_skipping_matching_ids(azure, monkeypatch, filter_expr):
    calls = {"search": [], "delete": []}
    remaining = [str(i) for i in range(2001)]
    reading = False

    def search(**kwargs):
        nonlocal reading
        calls["search"].append(kwargs)
        # Emulate Azure's top limit; deletion must drain the first page instead
        # of advancing a skip offset against the shrinking result set.
        page = list(remaining[:kwargs["top"]])
        reading = True
        try:
            for item_id in page:
                yield {"id": item_id}
        finally:
            reading = False

    def delete_documents(documents):
        assert not reading, "finish reading the current page before deleting it"
        calls["delete"].append(documents)
        for document in documents:
            remaining.remove(document["id"])
        return [SimpleNamespace(succeeded=True) for _ in documents]

    monkeypatch.setattr("app.services.knowledge.azure_search_service.time.sleep", lambda _: None)
    monkeypatch.setattr(azure, "get_search_client", lambda _: SimpleNamespace(
        search=search, delete_documents=delete_documents,
    ))
    result = (azure.delete_all_documents("v_kb1") if filter_expr is None
              else azure.delete_by_filter("v_kb1", filter_expr))
    assert result
    assert not remaining
    assert all("skip" not in call and call["top"] <= 1000 for call in calls["search"])
    assert all(call.get("filter") == filter_expr for call in calls["search"])
    assert all(len(batch) <= 1000 for batch in calls["delete"])
    deleted = [document["id"] for batch in calls["delete"] for document in batch]
    assert len(deleted) == len(set(deleted)) == 2001


def test_azure_matching_delete_stops_on_partial_failure(azure, monkeypatch):
    calls = []

    def delete_documents(documents):
        calls.append(documents)
        return [SimpleNamespace(succeeded=False) for _ in documents]

    monkeypatch.setattr(azure, "get_search_client", lambda _: SimpleNamespace(
        search=lambda **kwargs: [{"id": str(i)} for i in range(1001)],
        delete_documents=delete_documents,
    ))
    assert azure.delete_all_documents("v_kb1") is False
    assert len(calls) == 1


def test_azure_table_replace_stops_when_old_documents_cannot_be_deleted(azure, monkeypatch):
    monkeypatch.setattr(azure, "delete_by_filter", lambda *args: False)
    monkeypatch.setattr(azure, "upsert_vectors", lambda *args: pytest.fail("must not insert after delete failure"))
    assert azure.upsert_vectors_by_table("v_kb1", "sales", []) is False


@pytest.mark.parametrize("method", ["delete_knowledge_terms_by_ids", "delete_table_values_by_ids"])
@pytest.mark.parametrize("raises", [False, True])
def test_es_azure_deletions_propagate_failure(azure, monkeypatch, method, raises):
    def delete_documents(index, ids):
        if raises:
            raise RuntimeError("Azure unavailable")
        return False

    monkeypatch.setattr(azure, "delete_documents", delete_documents)
    svc = ElasticsearchService({"host": "https://offline.invalid"})
    svc.is_azure_search = True
    svc._azure_client = azure
    assert getattr(svc, method)(1, ["id-1"]) is False


@pytest.mark.parametrize("method,create_method", [
    ("index_knowledge_terms", "create_knowledge_index"),
    ("index_table_values", "create_table_value_index"),
])
def test_es_azure_replacement_stops_on_delete_failure(azure, monkeypatch, method, create_method):
    monkeypatch.setattr(azure, "delete_all_documents", lambda *args: False)
    monkeypatch.setattr(azure, "upload_documents", lambda *args: pytest.fail("must not upload after delete failure"))
    svc = ElasticsearchService({"host": "https://offline.invalid"})
    svc.is_azure_search = True
    svc._azure_client = azure
    monkeypatch.setattr(svc, create_method, lambda _: True)
    assert getattr(svc, method)(1, []) is False


@pytest.mark.parametrize("exists", [False, True])
def test_milvus_collection_existence_connects_and_checks_the_target(monkeypatch, exists):
    calls = []
    svc = vector_service.MilvusService({"host": "offline", "port": 19530})
    monkeypatch.setattr(svc, "connect", lambda: calls.append("connect"))

    def has_collection(name):
        calls.append(name)
        return exists

    monkeypatch.setattr(svc, "_has_collection", has_collection)
    provider = MilvusProvider()
    monkeypatch.setattr(provider, "_get_service", lambda config: svc)
    assert provider.collection_exists({}, "v_kb17") is exists
    assert calls == ["connect", "v_kb17"]


@pytest.mark.parametrize("provider_type,method", [
    (MilvusProvider, "collection_exists"), (AzureAISearchProvider, "index_exists"),
])
def test_vector_providers_propagate_existence_lookup_errors(monkeypatch, provider_type, method):
    def lookup(name):
        raise RuntimeError("target lookup failed")

    provider = provider_type()
    monkeypatch.setattr(provider, "_get_service", lambda config: SimpleNamespace(**{method: lookup}))
    with pytest.raises(RuntimeError, match="target lookup failed"):
        provider.collection_exists({}, "v_kb17")


def test_milvus_existence_does_not_hide_errors(monkeypatch):
    svc = vector_service.MilvusService({"host": "offline", "port": 19530})
    monkeypatch.setattr(svc, "connect", lambda: None)

    def has_collection(name):
        raise RuntimeError("lookup unavailable")

    monkeypatch.setattr(svc, "_has_collection", has_collection)
    with pytest.raises(RuntimeError, match="lookup unavailable"):
        svc.collection_exists("v_kb17")


@pytest.mark.parametrize("actual_dimension,expected", [(3, True), (2, False), (None, False)])
def test_existing_milvus_collection_validates_embedding_dimension(monkeypatch, actual_dimension, expected):
    fields = ([SimpleNamespace(name="embedding", params={"dim": actual_dimension})]
              if actual_dimension is not None else [])
    monkeypatch.setattr(vector_service, "Collection", lambda *args, **kwargs: SimpleNamespace(
        schema=SimpleNamespace(fields=fields),
    ))
    svc = vector_service.MilvusService({"host": "offline", "port": 19530})
    monkeypatch.setattr(svc, "connect", lambda: None)
    monkeypatch.setattr(svc, "_has_collection", lambda name: True)
    assert svc.create_collection("v_kb17", 3) is expected


@pytest.mark.parametrize("actual_dimension", [3, 2, None])
def test_existing_azure_index_validates_embedding_dimension(azure, monkeypatch, actual_dimension):
    fields = ([SimpleNamespace(name="embedding", vector_search_dimensions=actual_dimension)]
              if actual_dimension is not None else [])
    monkeypatch.setattr(azure, "get_index_client", lambda: SimpleNamespace(
        get_index=lambda name: SimpleNamespace(fields=fields),
    ))
    if actual_dimension == 3:
        assert azure.create_vector_index("v_kb17", 3)
    else:
        with pytest.raises(ValueError, match="configured embedding model requires 3"):
            azure.create_vector_index("v_kb17", 3)


@pytest.mark.parametrize("use_azure", [False, True])
@pytest.mark.parametrize("outcome", [False, True, "error"])
def test_es_index_existence_preserves_missing_and_error_distinction(use_azure, outcome):
    names = []

    def lookup(index):
        names.append(index)
        if outcome == "error":
            raise RuntimeError("index lookup unavailable")
        return outcome

    svc = ElasticsearchService({"host": "https://offline.invalid"})
    svc.is_azure_search = use_azure
    svc._azure_client = SimpleNamespace(index_exists=lookup)
    svc._client = SimpleNamespace(indices=SimpleNamespace(exists=lookup))
    if outcome == "error":
        with pytest.raises(RuntimeError, match="index lookup unavailable"):
            svc.index_exists("es_kb17_knowledge")
    else:
        assert svc.index_exists("es_kb17_knowledge") is outcome
    assert names == ["es_kb17_knowledge"]


@pytest.mark.parametrize("outcome", [False, True, "error"])
def test_vector_store_existence_uses_the_kb_target(monkeypatch, outcome):
    # Importing this facade loads model definitions; suppress env-file loading
    # and use an inert database URL so this test remains entirely isolated.
    from app.core import env_loader
    monkeypatch.setattr(env_loader, "load_app_environment", lambda **kwargs: None)
    monkeypatch.setenv("DATABASE_URL", "mysql+mysqlconnector://fake:fake@127.0.0.1:1/offline")
    from app.services.vector_store import service as store_service

    calls = []
    db = object()
    store = {"provider": "milvus", "collection_prefix": "custom_kb_"}

    def resolve(session, space_id, kb_id):
        assert (session, space_id, kb_id) == (db, 8, 17)
        return store

    def lookup(config, name):
        calls.append((config, name))
        if outcome == "error":
            raise RuntimeError("collection lookup unavailable")
        return outcome

    monkeypatch.setattr(store_service.VectorStoreService, "resolve_active_store", resolve)
    monkeypatch.setattr(store_service, "get_vector_store_provider", lambda provider: SimpleNamespace(collection_exists=lookup))
    if outcome == "error":
        with pytest.raises(RuntimeError, match="collection lookup unavailable"):
            store_service.VectorStoreService.collection_exists_for_kb(db, 17, space_id=8)
    else:
        assert store_service.VectorStoreService.collection_exists_for_kb(db, 17, space_id=8) is outcome
    assert calls == [(store, "custom_kb_17")]


def test_azure_upload_batches_more_than_5000_documents(azure, monkeypatch):
    batches = []

    def upload_documents(documents):
        batches.append(documents)
        return [SimpleNamespace(succeeded=True) for _ in documents]

    monkeypatch.setattr(azure, "get_search_client", lambda _: SimpleNamespace(upload_documents=upload_documents))
    documents = [{"id": str(i), "field_value": f"value-{i}"} for i in range(5001)]
    assert azure.upload_documents("v_kb17", documents)
    assert [len(batch) for batch in batches] == [1000, 1000, 1000, 1000, 1000, 1]
    assert [doc for batch in batches for doc in batch] == documents


@pytest.mark.parametrize("failure", ["partial", "short", "empty", "exception"])
def test_azure_upload_stops_at_the_first_failed_or_incomplete_batch(azure, monkeypatch, failure):
    batches = []

    def upload_documents(documents):
        batches.append(documents)
        results = [SimpleNamespace(succeeded=True) for _ in documents]
        if len(batches) == 2:
            if failure == "exception":
                raise RuntimeError("upload unavailable")
            if failure == "empty":
                return None
            if failure == "short":
                return results[:-1]
            results[-1].succeeded = False
        return results

    monkeypatch.setattr(azure, "get_search_client", lambda _: SimpleNamespace(upload_documents=upload_documents))
    documents = [{"id": str(i)} for i in range(3001)]
    assert azure.upload_documents("v_kb17", documents) is False
    assert [len(batch) for batch in batches] == [1000, 1000]


def test_azure_empty_upload_does_not_create_a_client(azure, monkeypatch):
    monkeypatch.setattr(azure, "get_search_client", lambda _: pytest.fail("empty upload needs no client"))
    assert azure.upload_documents("v_kb17", [])
