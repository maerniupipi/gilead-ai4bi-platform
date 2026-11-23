"""Wire-level checks for persisted model thinking settings and historical defaults."""
import asyncio
import json
from contextlib import asynccontextmanager, contextmanager
from types import SimpleNamespace

import httpx
import pytest

from app.schemas.chat import ChatRequest
from app.schemas.model_provider import ModelTestRequest
from app.services.chat.service import ChatService
from app.services.model_provider.service import ModelProviderService
from app.services.xlsx_qa import llm_client
from app.core.llm_policy import non_thinking_payload


def test_caller_cannot_enable_thinking_or_mutate_original_payload():
    original = {"model": "qwen", "enable_thinking": True, "stream": True}
    applied = non_thinking_payload(original)
    assert applied["reasoning_effort"] == "none" and applied["stream"] is True
    assert "enable_thinking" not in applied
    assert original["enable_thinking"] is True


@pytest.fixture
def wire(monkeypatch):
    captured = []

    class StreamResponse:
        status_code = 200

        async def aiter_lines(self):
            yield 'data: {"choices":[{"delta":{"reasoning_content":"must not be an answer"}}]}'
            yield 'data: {"choices":[{"delta":{"reasoning":"also not an answer"}}]}'
            yield 'data: {"choices":[{"delta":{"content":"ok"}}]}'
            yield 'data: [DONE]'

    class Client:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, *, json, headers):
            captured.append(json)
            return httpx.Response(200, json={"choices": [{"message": {"content": "ok", "tool_calls": []}}]})

        @asynccontextmanager
        async def stream(self, method, url, *, json, headers):
            captured.append(json)
            yield StreamResponse()

    provider = SimpleNamespace(api_key="test-key", is_active=True, protocol="openai",
        base_url="https://example.test/v1", name="test", models='["qwen3.6-35b-a3b"]')
    monkeypatch.setattr("app.services.chat.service.ModelProviderRepository.get_by_id", lambda *args: provider)
    monkeypatch.setattr(httpx, "AsyncClient", Client)
    return captured


@pytest.mark.parametrize("operation", ["send", "stream", "text_stream", "tools", "model_test", "xlsx_text", "xlsx_stream"])
@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("parameter", ["enable_thinking", "reasoning_effort", "thinking_budget"])
def test_every_model_entry_uses_model_thinking_settings(wire, operation, enabled, parameter):
    from app.services.chat.service import ModelProviderRepository
    settings = {"qwen3.6-35b-a3b": {"enabled": enabled, "parameter": parameter, "effort": "high", "budget": 2048}}
    ModelProviderRepository.get_by_id(None, 1).model_settings = settings
    async def run():
        request = ChatRequest(provider_id=1, model="qwen3.6-35b-a3b", message="hello")
        if operation == "send":
            assert (await ChatService.send_chat(None, request)).content == "ok"
        elif operation == "stream":
            assert [chunk async for chunk in ChatService.stream_chat(None, request)]
        elif operation == "text_stream":
            assert [chunk async for chunk in ChatService.stream_chat_text_deltas(None, request)] == ["ok"]
        elif operation == "tools":
            tool = {"type": "function", "function": {"name": "lookup", "parameters": {"type": "object"}}}
            await ChatService.chat_completion_openai(None, provider_id=1, model=request.model,
                messages=[{"role": "user", "content": "hello"}], tools=[tool])
            assert wire[-1]["tools"] == [tool] and wire[-1]["tool_choice"] == "auto"
        elif operation == "model_test":
            assert (await ModelProviderService.test_model(ModelTestRequest(
                base_url="https://example.test/v1", model=request.model, model_settings=settings))).success
        else:
            choice = llm_client.LlmChoice(1, "test", request.model, "https://example.test/v1", "test-key", "openai", model_settings=settings)
            if operation == "xlsx_text":
                assert await llm_client.chat_text(choice, system="", user="hello") == "ok"
            else:
                assert [part async for part in llm_client.chat_stream(choice, system="", user="hello")] == ["ok"]
        assert wire
        for body in wire:
            if parameter == "reasoning_effort":
                assert body["reasoning_effort"] == "none"
                assert "enable_thinking" not in body and "thinking_budget" not in body
            else:
                assert body["enable_thinking"] is False
                assert body["chat_template_kwargs"]["enable_thinking"] is False
                assert "reasoning_effort" not in body
                assert "thinking_budget" not in body
        assert wire[-1]['stream'] is (operation in {'stream', 'text_stream', 'xlsx_stream'})
        assert wire[-1]["model"] == request.model
    asyncio.run(run())


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("failure", [False, True])
def test_judge_nonstream_disables_thinking_and_never_retries(monkeypatch, enabled, failure):
    from app.services.eval import eval_comparison_service
    captured = []
    provider = SimpleNamespace(api_key="test-key", is_active=True, protocol="openai",
        base_url="https://example.test/v1", models='["qwen3.6-35b-a3b"]',
        model_settings={"qwen3.6-35b-a3b": {"enabled": enabled}})
    monkeypatch.setattr("app.core.database.SessionLocal", lambda: SimpleNamespace(close=lambda: None))
    monkeypatch.setattr("app.repositories.model_provider.ModelProviderRepository.get_by_id", lambda *args: provider)

    class Client:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def post(self, url, *, json, headers):
            captured.append(json)
            if failure:
                raise httpx.ConnectError('connection failure')
            return httpx.Response(200, request=httpx.Request('POST',url), json={'choices':[{'message':{'content':'{"result":"pass","score":1,"reason":"same result"}'}}]})


    monkeypatch.setattr(httpx, "Client", Client)
    result = eval_comparison_service._llm_judge_call_sync("query", "expected", "SELECT 1", provider_id=1, retry_count=1)
    assert result['is_correct'] is (None if failure else True)
    assert len(captured) == 1
    assert captured[0]['stream'] is False and captured[0]['reasoning_effort'] == 'none'
    if failure:
        assert result['detail']['attempts'] == 1


def test_saved_enabled_settings_and_unconfigured_models_cannot_enable_thinking():
    from app.core.llm_policy import model_thinking_payload
    provider = SimpleNamespace(model_settings={"enabled-model": {"enabled": True}})
    original = {"model": "other-model", "chat_template_kwargs": {"keep": 1}, "reasoning_effort": "high"}
    result = model_thinking_payload(original, provider)
    assert result["reasoning_effort"] == "none"
    assert result["chat_template_kwargs"] == {"keep": 1}
    assert result is not original
    assert original["chat_template_kwargs"] == {"keep": 1}


def test_model_settings_persist_through_provider_create_update():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from app.models.model_provider import ModelProvider
    from app.schemas.model_provider import ModelProviderCreate, ModelProviderUpdate, ModelProviderResponse
    from app.repositories.model_provider.repository import ModelProviderRepository
    engine = create_engine("sqlite://")
    ModelProvider.__table__.create(engine)
    with Session(engine) as db:
        provider = ModelProviderRepository.create(db, ModelProviderCreate(name="test", base_url="https://example.test/v1",
            models='["qwen"]', model_settings={"qwen": {"enabled": True, "parameter": "thinking_budget", "budget": 1024}}))
        assert ModelProviderResponse.model_validate(provider).model_settings["qwen"].budget == 1024
        provider = ModelProviderRepository.update(db, provider.id, ModelProviderUpdate(description="keep settings"))
        assert provider.model_settings["qwen"]["enabled"] is True
        provider = ModelProviderRepository.update(db, provider.id, ModelProviderUpdate(model_settings={"qwen": {"enabled": False}}))
        assert provider.model_settings["qwen"]["enabled"] is False
