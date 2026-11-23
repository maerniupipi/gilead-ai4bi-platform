from unittest.mock import AsyncMock
import asyncio
import copy
import json

import pytest

from app.services.autobi import lab_pipeline_runner as pipeline


def config(**advanced):
    return {"request": {"advanced_config": advanced}}


def test_disabled_keyword_recall_does_not_call_retriever(monkeypatch):
    async def unexpected(*args, **kwargs):
        pytest.fail("Disabled keyword recall must not call the retriever")

    monkeypatch.setattr(pipeline.AutoBIAtomicService, "es_knowledge_retrieve", unexpected)
    _, result = asyncio.run(pipeline._dispatch_step(
        None, 3, "sales", config(knowledge_es_config={"enable": False}), 1, {}, {},
    ))
    assert result["skipped"] is True
    assert result["results"] == []


def test_disabled_rewrite_preserves_original_question_without_calling_model(monkeypatch):
    async def unexpected(*args, **kwargs):
        pytest.fail("Disabled knowledge rewrite must not call the model")

    monkeypatch.setattr(pipeline, "_call_llm", unexpected)
    acc = {}
    _, result = asyncio.run(pipeline._dispatch_step(
        None, 4, "original question", config(knowledge_rewrite_config={"enable": False}), 1, acc, {},
    ))
    assert result["skipped"] is True
    assert result["rewritten_query"] == acc["rewritten_query"] == "original question"


@pytest.mark.parametrize("enable", [None, True])
def test_enabled_and_legacy_rewrite_still_call_the_model(monkeypatch, enable):
    seen = []

    async def model(*args, **kwargs):
        seen.append(args[2])
        return "rewritten question"

    monkeypatch.setattr(pipeline, "_call_llm", model)
    stage = {"prompt": "Rewrite {{rewrite_query}}"}
    if enable is not None:
        stage["enable"] = enable
    acc = {}
    _, result = asyncio.run(pipeline._dispatch_step(
        None, 4, "question", config(knowledge_rewrite_config=stage), 1, acc, {},
    ))
    assert seen == ["knowledge_rewrite"]
    assert result["rewritten_query"] == "rewritten question"


@pytest.mark.parametrize("enable", [False, True, None])
@pytest.mark.parametrize("bailian_compat", [False, True])
def test_summary_switch_controls_model_execution_and_keeps_pipeline_complete(monkeypatch, enable, bailian_compat):
    original_dispatch = pipeline._dispatch_step
    traces = []
    model_calls = []

    async def dispatch(db, sid, *args, **kwargs):
        if sid == 17:
            return await original_dispatch(db, sid, *args, **kwargs)
        return {}, {"skipped": True}

    async def stream(db, request):
        model_calls.append(request)
        yield "summary text"

    monkeypatch.setattr(pipeline, "_dispatch_step", dispatch)
    monkeypatch.setattr(pipeline, "_persist_trace", AsyncMock(side_effect=lambda *args: traces.append(copy.deepcopy(args[-1]))))
    monkeypatch.setattr(pipeline.ChatService, "stream_chat_text_deltas", stream)
    stage = {} if enable is False else {"prompt": "Summarize {{sql_data}}"}
    if enable is not None:
        stage["enable"] = enable
    lab_config = config(bi_summary_config=stage)
    if enable is not False:
        lab_config["model_bindings"] = {"bi_summary": {"provider_id": 1, "model_name": "test"}}

    async def run():
        return [json.loads(chunk[6:]) async for chunk in pipeline.run_autobi_lab_gateway_sse(
            None, user_message="sales", lab_config=lab_config, kb_id=1, project_id=1,
            project_name="test", trace_id="optional-stage-test", trace_started_at=1000,
            bailian_compat=bailian_compat, emit_step_events=True,
        )]

    events = asyncio.run(run())
    assert events[-1] == {"type": "done"}
    assert not any(event["type"] == "error" for event in events)
    assert all(step["status"] == "done" for step in traces[-1])
    if enable is False:
        assert not model_calls
        assert not any(event["type"] == "summary" for event in events)
        assert traces[-1][16]["response"]["skipped"] is True
    else:
        assert len(model_calls) == 1
        assert traces[-1][16]["response"]["content"] == "summary text"
