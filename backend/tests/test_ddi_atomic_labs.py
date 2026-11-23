import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.autobi import ddi_labs
from app.services.autobi.ddi_atomic_samples import sample_sql


def test_recall_contains_semantics_only(monkeypatch):
    monkeypatch.setattr(ddi_labs, "glossary", lambda *_: [])
    kinds = []
    def search(*args, expr, **kwargs):
        kind = expr.split('"')[1]
        kinds.append(kind)
        return [{"field_code":"sales_amt", "field_value":"实际金额CNY"}]
    monkeypatch.setattr(ddi_labs, "resolve_embedding_config", lambda *a,**k: {"model":"embed"})
    monkeypatch.setattr(ddi_labs.VectorStoreService,"resolve_active_store",lambda *a,**k: {})
    monkeypatch.setattr(ddi_labs.VectorStoreService,"search_vectors_with_config",search)
    monkeypatch.setattr(ddi_labs,"EmbeddingService",lambda _:SimpleNamespace(get_embedding=lambda _: [1],last_usage={}))
    items, _ = ddi_labs.recall(None, 1, "实际金额")
    assert set(kinds) == {"knowledge_term","table_column","table_value"}
    assert [v["type"] for v in items] == kinds


def test_glossary_can_answer_when_embedding_is_unavailable(monkeypatch):
    terms = [{"type":"knowledge_term","text":"MTD实际进度","content":"当月实际数量除以预估数量"}]
    monkeypatch.setattr(ddi_labs, "glossary", lambda *_: terms)
    def unavailable(*args):
        raise RuntimeError("embedding unavailable")
    monkeypatch.setattr(ddi_labs, "vector_semantics", unavailable)
    assert ddi_labs.recall(None,1,"MTD 实际进度是什么意思") == (terms,None)
    assert ddi_labs.recall(None,1,"本月进度的口径") == (terms,None)


def test_published_sample_and_per_lab_generation_rules(monkeypatch):
    question = "全国销售金额"
    sample = 'SELECT SUM(sales_amt) AS amount FROM sales_target_ai4bi'
    read = AsyncMock(return_value=sample)
    chat = AsyncMock(return_value=SimpleNamespace(model="qwen", usage={}, content='{"metrics":["sales_amount"],"start":202608,"end":202608}'))
    monkeypatch.setattr(ddi_labs, "read_database", read)
    monkeypatch.setattr(ddi_labs.ChatService,"send_chat",chat)
    cfg = {"model_bindings":{"nl2sql":{"provider_id":1,"model_name":"qwen"}},"atomic_sql_rules":"该口径以人民币统计"}
    features = {"data_scope":{"mode":"restricted","organizations":["OrgA"],"regions":["RegionA"]},
                "recall":[{"type":"knowledge_term","text":"销售金额"}]}
    result = asyncio.run(ddi_labs.run_lab(None,"sql",cfg,1,question,features))
    assert result["kind"] == "sql" and "OrgA" in result["sql"] and "RegionA" in result["sql"]
    chat.assert_not_awaited()
    read.return_value = None
    assert asyncio.run(ddi_labs.run_lab(None,"sql",cfg,1,question,features))["kind"] == "sql"
    assert "该口径以人民币统计" in chat.await_args.args[1].system
    read.reset_mock()
    asyncio.run(ddi_labs.run_lab(None,"sql",cfg,1,question,{**features,"context":"另按七月和美元统计"}))
    read.assert_not_awaited()


def test_sample_source_and_single_read_only_select():
    assert "public.sales_target_ai4bi" in sample_sql("SELECT SUM(sales_amt) FROM sales_target_ai4bi", {"mode":"all"})
    for sql in ["SELECT * FROM unrelated", "SELECT * FROM other.sales_target_ai4bi", "SELECT 1; SELECT 2"]:
        with pytest.raises(ValueError):
            sample_sql(sql, {"mode":"all"})
