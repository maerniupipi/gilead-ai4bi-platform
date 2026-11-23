"""Select an existing language model without duplicating its credentials."""
import json
import os
import time

from ...models.chatbi import ChatBIPPTModelConfig
from ...models.model_provider import ModelProvider
from .config import APIError


def registered_models(provider):
    try:
        values = json.loads(provider.models or "[]")
    except (ValueError, TypeError):
        return []
    if not isinstance(values, list):
        return []
    return list(dict.fromkeys(value.strip() for value in values if isinstance(value, str) and value.strip()))


def validate_selection(db, provider_id, model, *, status=400):
    provider = db.get(ModelProvider, provider_id)
    reason = None
    if not provider:
        reason = "所选语言模型供应商已不存在，请重新配置 AI PPT 模型"
    elif not provider.is_active:
        reason = "所选语言模型供应商已停用，请重新配置 AI PPT 模型"
    elif provider.protocol != "openai":
        reason = "AI PPT 当前仅支持 OpenAI 兼容协议的语言模型"
    elif not provider.api_key or not provider.api_key.strip():
        reason = "请先在语言模型中配置该供应商的 API Key"
    elif model not in registered_models(provider):
        reason = "所选模型不在该供应商的语言模型列表中，请重新选择"
    if reason:
        raise APIError(status, "summary_model_unavailable", reason)
    return provider


def _selection(db):
    saved = db.get(ChatBIPPTModelConfig, 1)
    if saved:
        return saved.provider_id, saved.model, "platform", saved.updated_at
    legacy_id = os.getenv("CHATBI_SUMMARY_PROVIDER_ID", "").strip()
    legacy_model = os.getenv("CHATBI_SUMMARY_MODEL", "").strip()
    if legacy_id.isdigit() and int(legacy_id) > 0 and legacy_model:
        return int(legacy_id), legacy_model, "environment", None
    return None, None, "none", None


def ppt_model_view(db):
    provider_id, model, source, updated_at = _selection(db)
    provider = db.get(ModelProvider, provider_id) if provider_id else None
    reason = None
    if provider_id:
        try:
            validate_selection(db, provider_id, model)
        except APIError as error:
            reason = error.message
    return {"provider_id": provider_id, "provider_name": provider.name if provider else None,
            "model": model, "configured": bool(provider_id), "available": bool(provider_id and not reason),
            "source": source, "reason": reason, "updated_at": updated_at}


def ppt_model_options(db):
    return [{"id": row.id, "name": row.name, "models": registered_models(row)}
            for row in db.query(ModelProvider).filter_by(is_active=True, protocol="openai").order_by(ModelProvider.name, ModelProvider.id)
            if row.api_key and row.api_key.strip() and registered_models(row)]


def save_ppt_model(db, selection, user_id):
    validate_selection(db, selection.provider_id, selection.model)
    row = db.get(ChatBIPPTModelConfig, 1)
    if row is None:
        row = ChatBIPPTModelConfig(id=1)
        db.add(row)
    row.provider_id, row.model = selection.provider_id, selection.model
    row.updated_by, row.updated_at = user_id, int(time.time())
    db.commit()
    return ppt_model_view(db)


def resolve_ppt_model(db, binding=None):
    if binding is None:
        provider_id, model, _, _ = _selection(db)
    else:
        provider_id, model = binding.get("provider_id"), binding.get("model")
    if not provider_id or not model:
        raise APIError(503, "summary_not_configured", "请先在管理 → 多模态模型中配置 AI PPT 生成模型")
    validate_selection(db, provider_id, model, status=503)
    return {"provider_id": provider_id, "model": model}
