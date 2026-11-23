"""
XLSX 表格智能问答 · LLM 调用封装

复用「模型中心」已配置的供应商（`model_provider`）进行 OpenAI 兼容调用。
提供两种能力：
  - chat_json(...)     —— 单轮，强约束输出 JSON；会做宽松解析 + 剥离 ```json 代码块
  - chat_text(...)     —— 单轮，返回纯文本（暂未用到，预留）

未来要接其它协议（Anthropic / Gemini / 本地模型）时，只需在此处扩展分支。
"""
from __future__ import annotations

from contextlib import aclosing
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx
from fastapi import HTTPException
from sqlalchemy.orm import Session

from ...repositories.model_provider import ModelProviderRepository
from ...core.llm_policy import model_thinking_payload
from ...core.model_stream import complete_async, stream_completion

logger = logging.getLogger(__name__)


@dataclass
class LlmChoice:
    """选用的模型 + 供应商。"""
    provider_id: int
    provider_name: str
    model: str
    base_url: str
    api_key: str
    protocol: str
    model_settings: dict = field(default_factory=dict)


def resolve_llm(
    db: Session,
    *,
    provider_id: Optional[int],
    model: Optional[str],
) -> LlmChoice:
    """选出一个可用的 (provider, model)。

    优先级：
      1. 显式传入的 provider_id + model
      2. 显式传入的 provider_id（取该 provider 的第一个模型）
      3. 任意 is_active 的 openai 协议 provider + 其第一个模型
    """
    provider = None
    if provider_id is not None:
        provider = ModelProviderRepository.get_by_id(db, provider_id)
        if not provider:
            raise HTTPException(status_code=404, detail=f"模型供应商不存在 (id={provider_id})")
        if not provider.is_active:
            raise HTTPException(status_code=400, detail="模型供应商未启用")
    else:
        candidates = ModelProviderRepository.get_all(db) if hasattr(
            ModelProviderRepository, "get_all"
        ) else []
        for p in candidates or []:
            if getattr(p, "is_active", False) and (getattr(p, "protocol", "openai") == "openai"):
                provider = p
                break
        if provider is None:
            raise HTTPException(
                status_code=400,
                detail="未找到可用的模型供应商，请在「模型中心」先配置一个 openai 协议的供应商。",
            )

    if not provider.api_key:
        raise HTTPException(status_code=400, detail="模型供应商未配置 API Key")
    if provider.protocol != "openai":
        raise HTTPException(
            status_code=400,
            detail=f"XLSX 问答暂只支持 openai 协议，当前供应商协议：{provider.protocol}",
        )

    chosen_model = (model or "").strip()
    if not chosen_model:
        models = _parse_provider_models(provider.models)
        if models:
            chosen_model = models[0]
    if not chosen_model:
        raise HTTPException(status_code=400, detail="未指定模型名称，且该供应商没有可用模型列表")

    return LlmChoice(
        provider_id=provider.id,
        provider_name=provider.name,
        model=chosen_model,
        base_url=provider.base_url,
        api_key=provider.api_key,
        protocol=provider.protocol,
        model_settings=getattr(provider, "model_settings", None) or {},
    )


def _parse_provider_models(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    try:
        obj = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return [s.strip() for s in str(raw).split(",") if s.strip()]
    if isinstance(obj, list):
        return [str(x).strip() for x in obj if str(x).strip()]
    if isinstance(obj, dict):
        vals = obj.get("models") or obj.get("list") or []
        if isinstance(vals, list):
            return [str(x).strip() for x in vals if str(x).strip()]
    return []


# ---------------------------------------------------------------------------
# 调用入口
# ---------------------------------------------------------------------------

async def chat_json(
    choice: LlmChoice,
    *,
    system: str,
    user: str,
    history: Optional[List[Dict[str, str]]] = None,
    temperature: float = 0.2,
    max_tokens: int = 2000,
    timeout: float = 90.0,
) -> Dict[str, Any]:
    """调用 LLM 并把输出解析成 JSON dict（做宽松解析）。"""
    content = await _chat_once(
        choice,
        system=system,
        user=user,
        history=history,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout,
    )
    return _loose_parse_json(content)


async def chat_text(
    choice: LlmChoice,
    *,
    system: str,
    user: str,
    history: Optional[List[Dict[str, str]]] = None,
    temperature: float = 0.3,
    max_tokens: int = 2000,
    timeout: float = 90.0,
) -> str:
    return await _chat_once(
        choice,
        system=system,
        user=user,
        history=history,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout,
    )


async def chat_stream(
    choice: LlmChoice,
    *,
    system: str,
    user: str,
    history: Optional[List[Dict[str, str]]] = None,
    temperature: float = 0.4,
    max_tokens: int = 2000,
    timeout: float = 120.0,
    stream_label: str = "",
) -> AsyncIterator[str]:
    """逐 token 流式输出。每次 yield 一段文本 delta（可能是单个字符或若干 token）。"""
    messages: List[Dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user})

    url = f"{choice.base_url.rstrip('/')}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {choice.api_key}",
    }
    payload = {
        "model": choice.model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True,
    }

    t = max(float(timeout), 5.0)
    cap = min(60.0, t)
    # 流式场景：read 为「相邻两次读到数据」的最大间隔，避免上游长连接无 chunk 时无限挂起
    httpx_timeout = httpx.Timeout(connect=cap, read=t, write=cap, pool=cap)

    label = (stream_label or "").strip() or "-"
    logger.info(
        "xlsx_qa.chat_stream begin label=%s model=%s url=%s user_chars=%d system_chars=%d timeout=%.1f",
        label,
        choice.model,
        url,
        len(user or ""),
        len(system or ""),
        t,
    )

    async with aclosing(stream_completion(
        url, model_thinking_payload(payload, choice), headers, timeout=httpx_timeout,
        operation='xlsx_qa.chat_stream', provider_id=choice.provider_id, provider=choice.provider_name,
    )) as source:
        async for event in source:
            choices = event.get('choices') or []
            if choices:
                piece = (choices[0].get('delta') or {}).get('content')
                if piece:
                    yield piece


async def _chat_once(
    choice: LlmChoice,
    *,
    system: str,
    user: str,
    history: Optional[List[Dict[str, str]]],
    temperature: float,
    max_tokens: int,
    timeout: float,
) -> str:
    messages: List[Dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user})

    url = f"{choice.base_url.rstrip('/')}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {choice.api_key}",
    }
    payload = {
        "model": choice.model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }

    data = await complete_async(url, model_thinking_payload(payload, choice), headers,
        timeout=timeout, operation='xlsx_qa.chat_once', provider_id=choice.provider_id,
        provider=choice.provider_name)
    return data['choices'][0]['message'].get('content') or ''


# ---------------------------------------------------------------------------
# 宽松 JSON 解析
# ---------------------------------------------------------------------------

_CODE_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def _loose_parse_json(content: str) -> Dict[str, Any]:
    """
    LLM 经常会把 JSON 外加 ```json ``` 或前后加一些说明文字。
    这里按优先级兼容：
      1. 直接 json.loads
      2. 剥离 ```json```
      3. 匹配第一个 { ... } 块
    """
    if not content:
        return {}
    text = content.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    m = _CODE_FENCE_RE.search(text)
    if m:
        inner = m.group(1).strip()
        try:
            return json.loads(inner)
        except json.JSONDecodeError:
            text = inner

    # 取第一个大括号到最后一个大括号
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = text[start : end + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError as e:
            logger.warning("xlsx_qa.llm loose_parse_json failed: %s", e)

    raise HTTPException(status_code=502, detail=f"模型未返回合法 JSON：{content[:200]}")


def parse_json_response(content: str) -> Dict[str, Any]:
    """对外暴露的 JSON 解析入口，逻辑与 _loose_parse_json 相同。"""
    return _loose_parse_json(content)


__all__ = ["LlmChoice", "resolve_llm", "chat_json", "chat_text", "chat_stream", "parse_json_response"]
