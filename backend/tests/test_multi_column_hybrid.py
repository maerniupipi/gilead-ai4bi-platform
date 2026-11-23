"""Hybrid recall regression tests use local clients, never deployed indexes."""
import asyncio
import threading
from types import SimpleNamespace

import pytest

from app.schemas.autobi_atomic import MultiGlobalValueMetaRetrieverRequest
from app.services.knowledge.autobi_atomic import service as atomic
from app.services.knowledge.azure_search_service import AzureAISearchService
from app.services.knowledge.es_service import ElasticsearchService

VECTOR_SEARCH_WITH_CONFIG = atomic.VectorStoreService.search_vectors_with_config
ES_SEARCH_TABLE_VALUES = ElasticsearchService.search_table_values


def run(request, **kwargs):
    return asyncio.run(atomic.AutoBIAtomicService.multi_global_value_meta_retrieve(
        None, 1, MultiGlobalValueMetaRetrieverRequest(**request, **kwargs),
    ))

def vector(value, field="sales&&sku", score=0.8):
    return {"field_table": field.split("&&")[0], "field_code": field,
            "field_value": value, "distance": score}

def keyword(value, field="sales&&sku", score=10):
    return {"field_table": field.split("&&")[0], "field_code": field,
            "field_value": value, "score": score}


@pytest.fixture
def clients(monkeypatch):
    main_thread = threading.get_ident()
    calls = {"embedding": [], "vector": [], "keyword": []}

    def on_main(value):
        def resolve(*args, **kwargs):
            assert threading.get_ident() != main_thread, "configuration database work blocked the event loop"
            return value
        return resolve

    monkeypatch.setattr(atomic, "get_knowledge_base_active", on_main(SimpleNamespace(space_id=1)))
    monkeypatch.setattr(atomic, "resolve_embedding_config", on_main({"base_url": "https://offline.invalid", "api_key": "fake", "model_name": "fake"}))
    monkeypatch.setattr(atomic, "_resolve_vs_config", on_main({"provider": "azure_ai_search"}))
    monkeypatch.setattr(atomic, "_resolve_es_config_safe", on_main({"host": "https://offline.invalid"}))

    def embed(query):
        calls["embedding"].append(query)
        return [0.1, 0.2]

    def search_vectors(store, kb_id, query_vector, **kwargs):
        assert threading.get_ident() != main_thread
        calls["vector"].append(kwargs)
        return calls.get("vector_hits", [vector("semantic")])

    def search_keywords(self, kb_id, query, **kwargs):
        assert threading.get_ident() != main_thread
        calls["keyword"].append(kwargs)
        return calls.get("keyword_hits", [keyword("D128211")])

    monkeypatch.setattr(atomic.EmbeddingService, "get_embedding", lambda self, q: embed(q))
    monkeypatch.setattr(atomic.VectorStoreService, "search_vectors_with_config", search_vectors, raising=False)
    monkeypatch.setattr(atomic.ElasticsearchService, "search_table_values", search_keywords)
    return calls


def test_union_keeps_keyword_only_sku_and_shared_hit_without_changing_scores(clients):
    clients["vector_hits"] = [vector("shared"), vector("semantic")]
    clients["keyword_hits"] = [keyword("D128211"), keyword("shared", score=8)]
    result = run({"query": "上海医院型号D128211的销量", "table_name": ["sales.sku"], "top_k": 3})
    assert {r.content for r in result.results} == {"shared", "semantic", "D128211"}
    assert result.results[0].content == "shared"
    assert result.results[0].metadata["sources"] == ["vector", "keyword"]
    assert result.results[0].metadata["score_type"] == "vector"
    assert result.results[0].score == .8
    assert result.results[0].metadata["keyword_score"] == .8
    assert result.total == 3
    assert clients["keyword"][0]["field_code"] == "sales&&sku"


def test_same_value_in_different_columns_survives_and_duplicate_tokens_do_not_repeat(monkeypatch, clients):
    clients["vector_hits"] = []

    def search(self, kb_id, query, **kwargs):
        clients["keyword"].append(kwargs)
        return [keyword("MERSILK", field=kwargs["field_code"])]

    monkeypatch.setattr(atomic.ElasticsearchService, "search_table_values", search)
    result = run({"query": "MERSILK", "table_name": ["sales.l3", "sales&&l3", "sales.l4"]})
    assert {r.metadata["field_code"] for r in result.results} == {"sales&&l3", "sales&&l4"}
    assert result.total == 2
    assert len(clients["keyword"]) == 2
    assert len(clients["embedding"]) == 1


def test_thresholds_are_applied_per_source_without_combining_scores(clients):
    clients["vector_hits"] = [vector("low vector", score=.4), vector("vector", score=.9)]
    clients["keyword_hits"] = [keyword("D128211", score=100), keyword("low keyword", score=1)]
    result = run({"query": "D128211", "table_name": ["sales.sku"], "top_k": 2,
                  "score_threshold": .8, "keyword_score_threshold": .5})
    assert {r.content for r in result.results} == {"vector", "D128211"}
    assert result.total == 2


def test_source_duplicates_do_not_refill_from_beyond_top_k(clients):
    clients["vector_hits"] = [vector("duplicate"), vector("duplicate"), vector("other")]
    clients["keyword_hits"] = []
    result = run({"query": "q", "table_name": ["sales.sku"], "top_k": 2})
    assert [r.content for r in result.results] == ["duplicate"]
    assert result.results[0].score == .8


def test_exact_query_value_is_not_promoted_ahead_of_source_order(clients):
    clients["vector_hits"] = [vector("C2"), vector("C3", score=.7)]
    clients["keyword_hits"] = [keyword("C2"), keyword("C", score=5)]
    result = run({"query": "C", "table_name": ["sales.sku"], "top_k": 2})
    assert [r.content for r in result.results] == ["C2", "C3", "C"]


def test_top_k_six_returns_twelve_disjoint_values_in_original_route_order(clients):
    clients["vector_hits"] = [vector(f"V{i}", score=.1 + i / 10) for i in range(1, 8)]
    clients["keyword_hits"] = [keyword(f"E{i}", score=100 - i) for i in range(1, 8)]
    result = run({"query": "E6", "table_name": ["sales.sku"], "top_k": 6})
    assert [r.content for r in result.results] == [f"V{i}" for i in range(1, 7)] + [f"E{i}" for i in range(1, 7)]
    assert result.total == 12
    assert clients["vector"][0]["top_k"] == clients["keyword"][0]["top_k"] == 6
    assert result.results[0].score == pytest.approx(.2)


def test_cross_route_duplicates_keep_first_position_and_both_original_scores(clients):
    clients["vector_hits"] = [vector("V1"), vector("shared", score=.7), vector("V3")]
    clients["keyword_hits"] = [keyword("shared", score=10), keyword("E2", score=5), keyword("V1", score=1)]
    result = run({"query": "E2", "table_name": ["sales.sku"], "top_k": 3})
    assert [r.content for r in result.results] == ["V1", "shared", "V3", "E2"]
    assert result.results[1].score == .7
    assert result.results[1].metadata["sources"] == ["vector", "keyword"]
    assert result.results[1].metadata["keyword_score"] == 1


def test_overlapping_table_and_column_inputs_cannot_exceed_each_routes_column_budget(monkeypatch, clients):
    def vectors(store, kb_id, query_vector, **kwargs):
        offset = 2 if "field_code" in kwargs["expr"] else 0
        return [vector(f"V{i + offset}") for i in range(2)]

    def keywords(self, kb_id, query, **kwargs):
        offset = 2 if kwargs["field_code"] else 0
        return [keyword(f"E{i + offset}") for i in range(2)]

    monkeypatch.setattr(atomic.VectorStoreService, "search_vectors_with_config", vectors)
    monkeypatch.setattr(ElasticsearchService, "search_table_values", keywords)
    result = run({"query": "q", "table_name": ["sales", "sales.sku"], "top_k": 2})
    assert [r.content for r in result.results] == ["V0", "V1", "E0", "E1"]


@pytest.mark.parametrize("keyword_provider", ["elasticsearch", "azure_cn"])
@pytest.mark.parametrize("vector_provider", ["azure_ai_search", "milvus"])
def test_provider_combinations_filter_before_top_k_and_keep_all_twelve_values(monkeypatch, clients, keyword_provider, vector_provider):
    """Exercise real adapters/provider dispatch while replacing only network clients."""
    azure_calls, es_calls, milvus_calls = [], [], []
    code = "sales&&sku"
    vector_hits = [vector(f"V{i}", score=.9 - i / 100) for i in range(1, 7)]
    keyword_hits = [keyword(f"E{i}", score=100 - i) for i in range(1, 7)]
    host = "https://offline.search.azure.cn"
    monkeypatch.setattr(atomic, "_resolve_vs_config", lambda *a, **kw: {
        "provider": vector_provider, "host": host if vector_provider == "azure_ai_search" else "offline",
        "password": "fake", "port": 19530, "collection_prefix": "v_kb",
    })
    monkeypatch.setattr(atomic, "_resolve_es_config_safe", lambda *a, **kw: {
        "host": host if keyword_provider == "azure_cn" else "http://offline.invalid", "password": "fake",
    })
    monkeypatch.setattr(atomic.VectorStoreService, "search_vectors_with_config", VECTOR_SEARCH_WITH_CONFIG)
    monkeypatch.setattr(ElasticsearchService, "search_table_values", ES_SEARCH_TABLE_VALUES)

    def azure_search(index, **kwargs):
        azure_calls.append((index, kwargs))
        is_vector = "vector_queries" in kwargs
        assert kwargs["top"] == 6
        assert f"field_code eq '{code}'" in kwargs["filter"]
        if is_vector:
            assert kwargs["vector_queries"][0].k_nearest_neighbors == 6
            assert "field_type eq 'table_value'" in kwargs["filter"]
        rows = vector_hits if is_vector else keyword_hits
        return [{**r, "id": str(i), "@search.score": r.get("distance", r.get("score"))} for i, r in enumerate(rows)]

    monkeypatch.setattr(AzureAISearchService, "index_exists", lambda *a: True)
    monkeypatch.setattr(AzureAISearchService, "_imports", staticmethod(lambda: {"VectorizedQuery": SimpleNamespace}))
    monkeypatch.setattr(AzureAISearchService, "get_search_client", lambda self, index: SimpleNamespace(
        search=lambda **kwargs: azure_search(index, **kwargs),
    ))

    def es_search(**kwargs):
        es_calls.append(kwargs)
        assert kwargs["size"] == 6
        assert kwargs["query"]["bool"]["filter"] == [{"term": {"field_code": code}}]
        return {"hits": {"hits": [{"_source": r, "_score": r["score"]} for r in keyword_hits]}}

    monkeypatch.setattr(ElasticsearchService, "get_client", lambda self: SimpleNamespace(
        indices=SimpleNamespace(exists=lambda **kw: True), search=es_search,
    ))
    monkeypatch.setattr("app.services.knowledge.es_service._log_index_doc_count", lambda *a: None)
    monkeypatch.setattr("app.services.knowledge.es_service._log_es_search_trace", lambda *a, **kw: None)

    def milvus_search(self, collection, query_vector, *, top_k, expr):
        milvus_calls.append((collection, top_k, expr))
        assert top_k == 6 and 'field_code == "sales&&sku"' in expr
        return vector_hits

    monkeypatch.setattr("app.services.knowledge.vector_service.MilvusService.search_vectors", milvus_search)
    result = run({"query": "E6", "table_name": ["sales.sku"], "top_k": 6})
    assert [r.content for r in result.results] == [f"V{i}" for i in range(1, 7)] + [f"E{i}" for i in range(1, 7)]
    assert result.total == 12
    assert len(es_calls) == (keyword_provider == "elasticsearch")
    assert len(milvus_calls) == (vector_provider == "milvus")
    assert len(azure_calls) == (keyword_provider == "azure_cn") + (vector_provider == "azure_ai_search")


def test_lab_multi_union_is_written_unchanged_into_the_sql_qs_recall(monkeypatch, clients):
    from app.services.autobi import lab_pipeline_runner as pipeline
    from app.services.autobi.lab_prompt_agg import build_qs_recall

    clients["vector_hits"] = [vector(f"V{i}") for i in range(6)]
    clients["keyword_hits"] = [keyword(f"E{i}") for i in range(6)]
    prompts = []

    async def model(db, config, binding, prompt, extra):
        prompts.append(prompt)
        return "SELECT 1"

    monkeypatch.setattr(pipeline, "_call_llm", model)
    monkeypatch.setattr(pipeline, "_knowledge_base_database_type", lambda *a: "PostgreSQL")
    column = {"score": .8, "content": "Sales&&SKU", "metadata": {
        "field_table": "sales", "field_code": "sales&&sku", "field_value": "Sales&&SKU",
    }}
    by_step = {
        1: {"response": {"results": [{**column, "content": "unrelated", "metadata": {**column["metadata"], "field_value": "unrelated"}}]}},
        6: {"response": {"results": [column]}},
    }
    config = {"request": {"advanced_config": {
        "value_multi_column_embedding_config": {"enable": True, "top_k": 6, "threshold": None},
        "nl2sql_config": {"prompt": "候选值：{{qs_recall}}\n问题：{{query}}"},
    }}}

    async def execute():
        request, response = await pipeline._dispatch_step(None, 12, "E5", config, 1, {}, by_step)
        by_step[12] = {"request": request, "response": response}
        qs_recall = build_qs_recall(by_step, multi_column_enabled=True)
        return await pipeline._dispatch_step(None, 14, "E5", config, 1, {}, by_step, features={"qs_recall": qs_recall})

    request, _ = asyncio.run(execute())
    expected = [f"V{i}" for i in range(6)] + [f"E{i}" for i in range(6)]
    assert repr(expected) in request["full_prompt"]
    assert "unrelated" not in request["full_prompt"]
    assert "{{qs_recall}}" not in request["full_prompt"]
    assert prompts == [request["full_prompt"]]


@pytest.mark.parametrize("failed_source", ["vector", "keyword", "embedding"])
def test_one_source_failure_keeps_the_other_source(monkeypatch, clients, failed_source):
    def fail(*args, **kwargs):
        raise RuntimeError("offline")

    if failed_source == "vector":
        monkeypatch.setattr(atomic.VectorStoreService, "search_vectors_with_config", fail)
    elif failed_source == "keyword":
        monkeypatch.setattr(atomic.ElasticsearchService, "search_table_values", fail)
    else:
        monkeypatch.setattr(atomic.EmbeddingService, "get_embedding", fail)
    result = run({"query": "q", "table_name": ["sales.sku"]})
    expected = "semantic" if failed_source == "keyword" else "D128211"
    assert [r.content for r in result.results] == [expected]


def test_vector_and_keyword_network_calls_overlap(monkeypatch, clients):
    rendezvous = threading.Barrier(2)

    def vectors(*args, **kwargs):
        rendezvous.wait(timeout=3)
        return [vector("semantic")]

    def keywords(*args, **kwargs):
        rendezvous.wait(timeout=3)
        return [keyword("D128211")]

    monkeypatch.setattr(atomic.VectorStoreService, "search_vectors_with_config", vectors)
    monkeypatch.setattr(atomic.ElasticsearchService, "search_table_values", keywords)
    result = run({"query": "q", "table_name": ["sales.sku"]})
    assert {r.content for r in result.results} == {"semantic", "D128211"}


def test_legacy_switch_and_independent_keyword_top_k_cannot_disable_or_expand_a_route(clients):
    result = run({"query": "q", "table_name": ["sales.sku"], "top_k": 2,
                  "keyword_enable": False, "keyword_top_k": 99})
    assert result.results[0].score == .8
    assert len(clients["keyword"]) == 1
    assert clients["keyword"][0]["top_k"] == 2
    assert result.total == 2


def test_foreign_tables_and_columns_do_not_leak_into_requested_field(clients):
    clients["vector_hits"] = [vector("wrong table", "other&&sku"), vector("wrong column", "sales&&grade")]
    clients["keyword_hits"] = [keyword("wrong table", "other&&sku"), keyword("right")]
    result = run({"query": "q", "table_name": ["sales.sku"]})
    assert [r.content for r in result.results] == ["right"]


@pytest.mark.parametrize("missing", ["vector", "keyword"])
def test_missing_configuration_keeps_available_route(monkeypatch, clients, missing):
    if missing == "vector":
        monkeypatch.setattr(atomic, "_resolve_vs_config", lambda *args, **kwargs: None)
    else:
        monkeypatch.setattr(atomic, "_resolve_es_config_safe", lambda *args, **kwargs: None)
    result = run({"query": "q", "table_name": ["sales.sku"]})
    assert [r.content for r in result.results] == ["D128211" if missing == "vector" else "semantic"]


def test_blank_query_does_not_run_wildcard_searches(clients):
    assert run({"query": "  ", "table_name": ["sales.sku"]}).total == 0
    assert clients["embedding"] == clients["vector"] == clients["keyword"] == []


def test_lab_step_12_passes_independent_keyword_parameters(monkeypatch):
    from app.services.autobi import lab_pipeline_runner as pipeline

    captured = []

    async def recall(db, kb_id, request):
        captured.append(request)
        return atomic.GlobalValueMetaRetrieverResponse()

    monkeypatch.setattr(pipeline.AutoBIAtomicService, "multi_global_value_meta_retrieve", recall)
    monkeypatch.setattr(pipeline, "collect_field_codes_for_multi_column", lambda _: ["sales&&sku"])
    cfg = {"request": {"advanced_config": {"value_multi_column_embedding_config": {
        "enable": True, "top_k": 15, "threshold": .3,
        "keyword_enable": False, "keyword_top_k": 8, "keyword_score_threshold": .6,
    }}}}
    request, _ = asyncio.run(pipeline._dispatch_step(None, 12, "question", cfg, 1, {}, {}))
    assert "keyword_enable" not in request
    assert "keyword_top_k" not in request
    assert captured[0].top_k == 15
    assert captured[0].keyword_score_threshold == .6
    assert captured[0].score_threshold == .3


def test_lab_step_7_uses_value_settings_independently_of_column_settings(monkeypatch):
    from app.services.autobi import lab_pipeline_runner as pipeline
    captured = []

    async def recall(db, kb_id, request):
        captured.append(request)
        return atomic.GlobalValueMetaRetrieverResponse()

    monkeypatch.setattr(pipeline.AutoBIAtomicService, "global_value_meta_retrieve", recall)
    cfg = {"request": {"advanced_config": {
        "meta_embedding_config": {"top_k": 90, "threshold": .3},
        "value_embedding_config": {"top_k": 6, "threshold": .55},
    }}}
    asyncio.run(pipeline._dispatch_step(None, 7, "question", cfg, 1, {}, {}))
    assert captured[0].top_k == 6
    assert captured[0].score_threshold == .55


@pytest.mark.parametrize("value", ["", "false"])
def test_workflow_optional_keyword_inputs_use_defaults_and_preserve_false(value):
    from app.services.agent_app.executors.atomic import _build_request_body

    body = _build_request_body(SimpleNamespace(), {"input_vars": [
        {"key": "keyword_enable", "type": "BOOLEAN", "const_value": value},
        {"key": "keyword_top_k", "type": "NUMBER", "const_value": ""},
        {"key": "keyword_score_threshold", "type": "NUMBER", "const_value": ""},
    ]})
    assert body == ({} if value == "" else {"keyword_enable": False})


def test_azure_keyword_filter_is_sent_before_top_k_and_quotes_are_escaped(monkeypatch):
    svc = ElasticsearchService({"host": "https://offline.search.windows.net", "password": "fake"})
    calls = []
    monkeypatch.setattr(svc._azure_client, "index_exists", lambda _: True)
    monkeypatch.setattr(svc._azure_client, "get_search_client", lambda _: SimpleNamespace(
        search=lambda **kwargs: calls.append(kwargs) or [],
    ))
    svc.search_table_values(1, "D128211", top_k=2, field_code="sales&&sku'O")
    assert calls[0]["filter"] == "field_code eq 'sales&&sku''O'"
    assert calls[0]["top"] == 2


def test_native_es_keyword_filter_is_part_of_query_not_post_filter(monkeypatch):
    svc = ElasticsearchService({"host": "https://offline.invalid"})
    calls = []
    fake = SimpleNamespace(indices=SimpleNamespace(exists=lambda **kwargs: True),
                           search=lambda **kwargs: calls.append(kwargs) or {"hits": {"hits": []}})
    monkeypatch.setattr(svc, "get_client", lambda: fake)
    monkeypatch.setattr("app.services.knowledge.es_service._log_index_doc_count", lambda *args: None)
    svc.search_table_values(1, "C", top_k=2, field_code="sales&&grade")
    assert calls[0]["query"]["bool"]["filter"] == [{"term": {"field_code": "sales&&grade"}}]
    assert calls[0]["size"] == 2


def test_azure_legacy_keyword_calls_do_not_gain_a_filter(monkeypatch):
    svc = AzureAISearchService({"host": "https://offline.invalid", "password": "fake"})
    calls = []
    monkeypatch.setattr(svc, "index_exists", lambda _: True)
    monkeypatch.setattr(svc, "get_search_client", lambda _: SimpleNamespace(
        search=lambda **kwargs: calls.append(kwargs) or [],
    ))
    svc.keyword_search("es_kb1_table_value", "上海", ["field_value"], top_k=3)
    assert "filter" not in calls[0]
