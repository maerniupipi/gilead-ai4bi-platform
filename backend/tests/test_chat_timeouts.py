import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

from app.schemas.chat import ChatRequest, ChatResponse
from app.services.autobi import lab_pipeline_runner
from app.services.chat.service import ChatService


def test_chat_service_uses_request_timeout_seconds(monkeypatch):
    asyncio.run(_assert_chat_service_uses_request_timeout_seconds(monkeypatch))


async def _assert_chat_service_uses_request_timeout_seconds(monkeypatch):
    captured = {}

    class FakeResponse:
        status_code = 200
        text = "{}"

        def json(self):
            return {"choices": [{"message": {"content": "ok"}}]}

        async def aiter_lines(self):
            yield 'data: {"choices":[{"delta":{"content":"ok"}}]}'
            yield 'data: [DONE]'

    class FakeAsyncClient:
        def __init__(self, *, timeout, limits=None):
            captured["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json, headers):
            assert json['stream'] is False
            return FakeResponse()

    monkeypatch.setattr(
        "app.services.chat.service.ModelProviderRepository.get_by_id",
        lambda db, provider_id: SimpleNamespace(
            api_key="test-key",
            is_active=True,
            protocol="openai",
            base_url="https://example.test/v1",
            name="test-provider",
        ),
    )
    monkeypatch.setattr("app.services.chat.service.httpx.AsyncClient", FakeAsyncClient)

    req = ChatRequest(
        provider_id=1,
        model="test-model",
        message="hello",
        timeout_seconds=135,
    )
    res = await ChatService.send_chat(None, req)

    assert res.content == "ok"
    assert captured["timeout"] == 135


def test_lab_llm_call_passes_timeout_seconds_to_chat_service(monkeypatch):
    asyncio.run(_assert_lab_llm_call_passes_timeout_seconds_to_chat_service(monkeypatch))


async def _assert_lab_llm_call_passes_timeout_seconds_to_chat_service(monkeypatch):
    captured = {}

    async def fake_send_chat(db, req):
        captured["timeout_seconds"] = req.timeout_seconds
        return ChatResponse(content="ok", model=req.model, provider="test-provider")

    monkeypatch.setattr(
        "app.services.autobi.lab_pipeline_runner.ChatService.send_chat",
        fake_send_chat,
    )

    text = await lab_pipeline_runner._call_llm(
        None,
        {"model_bindings": {"nl2sql": {"provider_id": 1, "model_name": "test-model"}}},
        "nl2sql",
        "prompt",
        {"timeout_seconds": 180},
    )

    assert text == "ok"
    assert captured["timeout_seconds"] == 180
