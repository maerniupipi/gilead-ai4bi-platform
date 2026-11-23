"""Model service: complete intermediate calls and streaming presentation calls, without retries."""
from contextlib import aclosing
import json
from typing import Any, AsyncGenerator, Dict, List, Optional

import httpx
from fastapi import HTTPException
from sqlalchemy.orm import Session

from ...core.execution import read_database
from ...core.llm_policy import model_thinking_payload
from ...core.model_stream import complete_async, stream_completion
from ...repositories.model_provider import ModelProviderRepository
from ...schemas.chat import ChatRequest, ChatResponse


class ChatService:
    @staticmethod
    def _request_timeout(chat_request: ChatRequest, default: float) -> float:
        raw = getattr(chat_request, 'timeout_seconds', None)
        if raw is None:
            return default
        try:
            return max(1.0, float(raw))
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _openai_messages(chat_request: ChatRequest) -> list:
        messages = []
        system = (chat_request.system or '').strip()
        if system:
            messages.append({'role': 'system', 'content': system})
        messages.append({'role': 'user', 'content': chat_request.message})
        return messages

    @staticmethod
    def _provider(db, provider_id):
        provider = ModelProviderRepository.get_by_id(db, provider_id)
        if not provider:
            raise HTTPException(404, '供应商不存在')
        if not provider.api_key:
            raise HTTPException(400, '供应商未配置API Key')
        if not provider.is_active:
            raise HTTPException(400, '供应商未启用')
        if provider.protocol != 'openai':
            raise HTTPException(400, f'暂不支持 {provider.protocol} 协议')
        return provider

    @staticmethod
    def _connection(provider, provider_id, payload, timeout, operation):
        return (f"{provider.base_url.rstrip('/')}/chat/completions",
                model_thinking_payload(payload, provider),
                {'Content-Type': 'application/json', 'Authorization': f'Bearer {provider.api_key}'},
                {'timeout': timeout, 'operation': operation, 'provider_id': provider_id,
                 'provider': provider.name})

    @staticmethod
    def _request_connection(db, request, operation, default_timeout):
        provider = ChatService._provider(db, request.provider_id)
        payload = {'model': request.model, 'messages': ChatService._openai_messages(request),
                   'temperature': request.temperature, 'max_tokens': request.max_tokens,
                   'top_p': request.top_p,
                   **({'stop': request.stop_words} if request.stop_words else {})}
        return provider, ChatService._connection(provider, request.provider_id, payload,
            ChatService._request_timeout(request, default_timeout), operation)

    @staticmethod
    async def send_chat(db: Session, chat_request: ChatRequest) -> ChatResponse:
        """Intermediate model calls return one complete response."""
        provider, (url, payload, headers, options) = await read_database(db, ChatService._request_connection, chat_request, 'send_chat', 60.0)
        result = await complete_async(url, payload, headers, **options)
        return ChatResponse(content=result['choices'][0]['message'].get('content') or '',
                            model=chat_request.model, provider=provider.name, usage=result.get("usage") or {})

    @staticmethod
    async def stream_chat(db: Session, chat_request: ChatRequest) -> AsyncGenerator[str, None]:
        _, (url, payload, headers, options) = await read_database(db, ChatService._request_connection, chat_request, 'stream_chat', 60.0)
        async with aclosing(stream_completion(url, payload, headers, **options)) as source:
            async for event in source:
                yield 'data: ' + json.dumps(event, ensure_ascii=False) + '\n\n'
        yield 'data: [DONE]\n\n'

    @staticmethod
    async def stream_chat_text_deltas(db: Session, chat_request: ChatRequest) -> AsyncGenerator[str, None]:
        _, (url, payload, headers, options) = await read_database(db, ChatService._request_connection, chat_request, 'stream_chat_text_deltas', 120.0)
        async with aclosing(stream_completion(url, payload, headers, **options)) as source:
            async for event in source:
                choices = event.get('choices') or []
                if choices:
                    text = (choices[0].get('delta') or {}).get('content')
                    if text:
                        yield text

    @staticmethod
    async def chat_completion_openai(
        db: Session, *, provider_id: int, model: str, messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None, temperature: float = 0.5,
        max_tokens: int = 4096, top_p: float = 0.9,
    ) -> Dict[str, Any]:
        """Tool-planning calls keep the non-streaming message contract."""
        provider = await read_database(db, ChatService._provider, provider_id)
        payload = {'model': model, 'messages': messages, 'temperature': temperature,
                   'max_tokens': max_tokens, 'top_p': top_p}
        if tools:
            payload.update(tools=tools, tool_choice='auto')
        url, payload, headers, options = ChatService._connection(provider, provider_id, payload, 120.0, 'chat_completion_openai')
        result = await complete_async(url, payload, headers, **options)
        return result['choices'][0]['message']
