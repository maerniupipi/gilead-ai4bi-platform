import asyncio
import copy
import json

import pytest
from fastapi import HTTPException

from app.services.autobi import lab_pipeline_runner as pipeline


def collect_failure(monkeypatch, step_id, *, persistence_fails=False):
    saved = []
    meta = next(m for m in pipeline._pipeline_steps_meta() if m["stepId"] == step_id)
    # Keep the real step indices, while skipping unrelated external calls.
    monkeypatch.setattr(pipeline, "_pipeline_steps_meta", lambda: [
        {**meta, "stepId": i} for i in range(1, step_id + 1)
    ])

    async def persist(*args):
        snapshot = copy.deepcopy(args[-1])
        if persistence_fails and any(s["status"] == "error" for s in snapshot):
            raise RuntimeError("trace database unavailable")
        saved.append(snapshot)

    async def dispatch(db, sid, *args, **kwargs):
        if sid == step_id:
            raise HTTPException(429, "model rate limit")
        return {}, {"skipped": True}

    async def stream(db, request):
        assert request.timeout_seconds == 600
        yield "partial summary"
        raise HTTPException(504, "model read timeout")

    monkeypatch.setattr(pipeline, "_persist_trace", persist)
    monkeypatch.setattr(pipeline, "_dispatch_step", dispatch)
    monkeypatch.setattr(pipeline.ChatService, "stream_chat_text_deltas", stream)
    config = {
        "model_bindings": {"bi_summary": {"provider_id": 1, "model_name": "test-model"}},
        "request": {"advanced_config": {"bi_summary_config": {"prompt": "Summarize {{sql_data}}"}}},
    }

    async def run():
        return [json.loads(chunk[6:]) async for chunk in pipeline.run_autobi_lab_gateway_sse(
            None, user_message="sales", lab_config=config, kb_id=43, project_id=23,
            project_name="test", trace_id="test-trace", trace_started_at=1000,
        )]

    return saved, asyncio.run(run())


@pytest.mark.parametrize("step_id,error", [(14, "429: model rate limit"), (17, "504: model read timeout")])
def test_failed_model_step_is_saved_before_error_event(monkeypatch, step_id, error):
    saved, events = collect_failure(monkeypatch, step_id)
    failed = saved[-1][step_id - 1]
    assert failed["status"] == "error"
    assert error in failed["error"]
    assert failed["duration_ms"] is not None
    assert all(s["status"] == "done" for s in saved[-1][:step_id - 1])
    assert next(e for e in events if e["type"] == "error")["message"] == error


def test_trace_write_failure_does_not_hide_original_model_error(monkeypatch):
    _, events = collect_failure(monkeypatch, 14, persistence_fails=True)
    assert next(e for e in events if e["type"] == "error")["message"] == "429: model rate limit"


def test_cancelled_model_call_does_not_leave_trace_running(monkeypatch):
    saved = []
    monkeypatch.setattr(pipeline, "_pipeline_steps_meta", lambda: [
        {"stepId": 1, "title": "model", "apiKey": "model", "color": "blue"},
    ])
    async def persist(*args):
        saved.append(copy.deepcopy(args[-1]))
    monkeypatch.setattr(pipeline, "_persist_trace", persist)

    async def run():
        started = asyncio.Event()
        async def dispatch(*args, **kwargs):
            started.set()
            await asyncio.Event().wait()
        monkeypatch.setattr(pipeline, "_dispatch_step", dispatch)
        async def consume():
            return [chunk async for chunk in pipeline.run_autobi_lab_gateway_sse(
                None, user_message="sales", lab_config={}, kb_id=43, project_id=23,
                project_name="test", trace_id="cancelled-trace", trace_started_at=1000,
            )]
        task = asyncio.create_task(consume())
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    asyncio.run(run())
    assert saved[-1][0]["status"] == "error"
    assert saved[-1][0]["error"] == "执行已取消或中断"


@pytest.mark.parametrize("binding", ["knowledge_rewrite", "nl2sql", "ner_retrieval", "chart_drawing"])
@pytest.mark.parametrize("configured,expected", [(None, 600), (240, 240)])
def test_model_request_honors_runtime_timeout(monkeypatch, binding, configured, expected):
    from types import SimpleNamespace
    seen = []
    async def send(db, request):
        seen.append(request.timeout_seconds)
        return SimpleNamespace(content="answer")
    monkeypatch.setattr(pipeline.ChatService, "send_chat", send)
    config = {"model_bindings": {binding: {"provider_id": 1, "model_name": "test"}},
              "request": {"advanced_config": {f"{binding}_config": {"timeout_seconds": configured}}}}
    assert asyncio.run(pipeline._call_llm(None, config, binding, "question", {})) == "answer"
    assert seen == [expected]
