import asyncio
from datetime import datetime
from types import SimpleNamespace

import pytest

from app.models import KnowledgeBase
from app.models.embedding_config import EmbeddingConfig
from app.models.vector_store import VectorStoreConfig
from app.repositories.embedding_config import EmbeddingConfigRepository
from app.repositories.vector_store import VectorStoreRepository
from app.services.config_resolver import resolve_embedding_config
from app.services.knowledge.config_overrides import resolve_knowledge_base_config
from app.services.knowledge import vector_service
from app.services.vector_store.service import VectorStoreService
from app.services.knowledge.autobi_atomic import service as retrievers


class FakeDb:
    def __init__(self, records=None):
        self.records = records or {}
        self.lookups = []

    def get(self, model, ident):
        self.lookups.append((model, ident))
        return self.records.get((model, ident))


def store(ident, host, space_id=1):
    return SimpleNamespace(
        id=ident, space_id=space_id, name=host, provider="milvus", host=host,
        port="19530", username=None, password=None, database="default",
        collection_prefix="v_kb", dimension=1024, extra_config=None,
        is_active=False, created_at=datetime.now(), updated_at=datetime.now(),
    )


def test_unbound_knowledge_base_keeps_shared_defaults(monkeypatch):
    monkeypatch.setenv("KNOWLEDGE_BASE_CONFIG_OVERRIDES", '{"43":{"vector_store_id":4}}')
    default = store(1, "existing-milvus")
    monkeypatch.setattr(VectorStoreRepository, "get_active", lambda db, space_id: default)
    db = FakeDb()
    assert VectorStoreService.resolve_active_store(db, 1, kb_id=36)["host"] == "existing-milvus"
    assert db.lookups == []


def test_indexing_and_retrieval_select_the_same_bound_store(monkeypatch):
    monkeypatch.setenv("KNOWLEDGE_BASE_CONFIG_OVERRIDES", '{"43":{"vector_store_id":4}}')
    db = FakeDb({
        (KnowledgeBase, 43): SimpleNamespace(space_id=1, is_deleted=False),
        (VectorStoreConfig, 4): store(4, "milvus-lite"),
    })
    calls = []
    provider = SimpleNamespace(
        create_collection=lambda config, name, dimension: calls.append(("create", config["host"], name)) or True,
        search_vectors=lambda config, name, vector, **kwargs: calls.append(("search", config["host"], name)) or [],
    )
    monkeypatch.setattr("app.services.vector_store.service.get_vector_store_provider", lambda name: provider)
    assert VectorStoreService.create_collection_for_kb(db, 43, 1024, space_id=1)
    VectorStoreService.search_vectors(db, 43, [0.0], space_id=1)
    assert calls == [("create", "milvus-lite", "v_kb43"), ("search", "milvus-lite", "v_kb43")]


@pytest.mark.parametrize("requested_space,kb_space,store_space", [(2, 1, 1), (1, 1, 2)])
def test_cross_space_binding_is_rejected(monkeypatch, requested_space, kb_space, store_space):
    monkeypatch.setenv("KNOWLEDGE_BASE_CONFIG_OVERRIDES", '{"43":{"vector_store_id":4}}')
    db = FakeDb({
        (KnowledgeBase, 43): SimpleNamespace(space_id=kb_space, is_deleted=False),
        (VectorStoreConfig, 4): store(4, "milvus-lite", store_space),
    })
    with pytest.raises(ValueError, match="空间"):
        resolve_knowledge_base_config(db, 43, requested_space, "vector_store_id")


@pytest.mark.parametrize("raw", ['not-json', '[]', '{"43":[]}', '{"43":{}}', '{"43":{"unknown":4}}', '{"43":{"vector_store_id":true}}', '{"43":{"vector_store_id":0}}'])
def test_invalid_explicit_binding_fails_instead_of_using_default(monkeypatch, raw):
    monkeypatch.setenv("KNOWLEDGE_BASE_CONFIG_OVERRIDES", raw)
    with pytest.raises(ValueError, match="配置"):
        VectorStoreService.resolve_active_store(FakeDb(), 1, kb_id=43)


@pytest.mark.parametrize("deleted,missing_store", [(True, False), (False, True)])
def test_missing_or_deleted_binding_fails_closed(monkeypatch, deleted, missing_store):
    monkeypatch.setenv("KNOWLEDGE_BASE_CONFIG_OVERRIDES", '{"43":{"vector_store_id":4}}')
    db = FakeDb({(KnowledgeBase, 43): SimpleNamespace(space_id=1, is_deleted=deleted)})
    if not missing_store:
        db.records[(VectorStoreConfig, 4)] = store(4, "milvus-lite")
    with pytest.raises(ValueError):
        resolve_knowledge_base_config(db, 43, 1, "vector_store_id")


def test_embedding_override_does_not_replace_other_knowledge_bases(monkeypatch):
    monkeypatch.setenv("KNOWLEDGE_BASE_CONFIG_OVERRIDES", '{"43":{"embedding_config_id":6}}')
    default = SimpleNamespace(provider="dashscope", api_key="default-test-key", model="default", dimension=1024, base_url="https://example.test/embeddings")
    selected = SimpleNamespace(**{**vars(default), "model": "selected", "space_id": 1, "is_active": True})
    monkeypatch.setattr(EmbeddingConfigRepository, "get_default", lambda db, space_id: default)
    db = FakeDb({
        (KnowledgeBase, 43): SimpleNamespace(space_id=1, is_deleted=False),
        (EmbeddingConfig, 6): selected,
    })
    assert resolve_embedding_config(db, 1, kb_id=43)["model"] == "selected"
    assert resolve_embedding_config(db, 1, kb_id=36)["model"] == "default"
    selected.is_active = False
    with pytest.raises(ValueError):
        resolve_embedding_config(db, 1, kb_id=43)


def test_table_retrieval_uses_bound_embedding_and_store(monkeypatch):
    monkeypatch.setenv("KNOWLEDGE_BASE_CONFIG_OVERRIDES", '{"43":{"vector_store_id":4,"embedding_config_id":6}}')
    kb = SimpleNamespace(space_id=1, is_deleted=False)
    db = FakeDb({
        (KnowledgeBase, 43): kb,
        (VectorStoreConfig, 4): store(4, "milvus-lite"),
        (EmbeddingConfig, 6): SimpleNamespace(
            space_id=1, is_active=True, provider="openai", api_key="test-key",
            model="selected", dimension=4, base_url="https://example.test/embeddings",
        ),
    })
    monkeypatch.setattr(retrievers, "get_knowledge_base_active", lambda db, kb_id: kb)

    class Embedding:
        def __init__(self, config):
            assert config["model"] == "selected"

        def get_embedding(self, query):
            return [1.0, 0.0, 0.0, 0.0]

    def search(config, name, vector, **kwargs):
        assert config["host"] == "milvus-lite"
        assert name == "v_kb43"
        assert vector == [1.0, 0.0, 0.0, 0.0]
        return [{"distance": 0.9, "field_type": "table_column", "field_code": "sales&&city", "field_value": "城市"}]

    monkeypatch.setattr(retrievers, "EmbeddingService", Embedding)
    monkeypatch.setattr("app.services.vector_store.service.get_vector_store_provider", lambda name: SimpleNamespace(search_vectors=search))
    request = retrievers.TableMetaRetrieverRequest(query="城市", top_k=1)
    response = asyncio.run(retrievers.AutoBIAtomicService.table_meta_retrieve(db, 43, request))
    assert response.results[0].metadata["source"] == "vector_store"


def test_retrieval_does_not_hide_invalid_explicit_store(monkeypatch):
    monkeypatch.setenv("KNOWLEDGE_BASE_CONFIG_OVERRIDES", '{"43":{"vector_store_id":0}}')
    with pytest.raises(ValueError):
        retrievers._resolve_vs_config(FakeDb(), 1, kb_id=43)


def test_milvus_endpoints_and_databases_have_isolated_connections(monkeypatch):
    connections, collections, checks = [], [], []
    monkeypatch.setattr(vector_service.connections, "connect", lambda **kw: connections.append(kw))
    monkeypatch.setattr(vector_service.connections, '_fetch_handler', lambda alias: SimpleNamespace(
        has_collection=lambda name, **kw: checks.append(alias) or False))

    class Collection:
        def __init__(self, name, schema=None, using=None):
            collections.append(using)

        def create_index(self, **kwargs):
            pass

    monkeypatch.setattr(vector_service, "Collection", Collection)
    configs = [
        {"host": "old-milvus", "port": "19530", "database": "default", "password": "test-secret"},
        {"host": "milvus-lite", "port": "19530", "database": "default"},
        {"host": "milvus-lite", "port": "19530", "database": "other"},
    ]
    for config in configs:
        assert vector_service.MilvusService(config).create_collection("same_name", 4)
    aliases = [c["alias"] for c in connections]
    assert len(set(aliases)) == 3
    assert all("test-secret" not in alias for alias in aliases)
    assert [c["db_name"] for c in connections] == ["default", "default", "other"]
    assert collections == checks == aliases
