"""Resolve deployment-specific knowledge-base bindings without changing space defaults."""
import json
import os
from typing import Optional

from sqlalchemy.orm import Session

from app.models import KnowledgeBase
from app.models.embedding_config import EmbeddingConfig
from app.models.vector_store import VectorStoreConfig


def resolve_knowledge_base_config(
    db: Session, kb_id: Optional[int], space_id: Optional[int], config_name: str
):
    models = {"vector_store_id": VectorStoreConfig, "embedding_config_id": EmbeddingConfig}
    if config_name not in models:
        raise ValueError("不支持的知识库配置类型")
    raw = os.environ.get("KNOWLEDGE_BASE_CONFIG_OVERRIDES", "").strip()
    if kb_id is None or not raw:
        return None
    try:
        bindings = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("知识库独立配置格式错误") from exc
    if not isinstance(bindings, dict):
        raise ValueError("知识库独立配置必须为对象")
    if str(kb_id) not in bindings:
        return None
    binding = bindings[str(kb_id)]
    if not isinstance(binding, dict) or not binding or set(binding) - models.keys():
        raise ValueError("知识库独立配置项必须包含有效的配置类型")
    if any(type(value) is not int or value <= 0 for value in binding.values()):
        raise ValueError("知识库独立配置 ID 必须为正整数")
    if config_name not in binding:
        return None
    config_id = binding[config_name]

    kb = db.get(KnowledgeBase, kb_id)
    if kb is None or kb.is_deleted:
        raise ValueError("独立配置对应的知识库不存在或已删除")
    if space_id is not None and kb.space_id != space_id:
        raise ValueError("知识库独立配置与请求空间不一致")
    config = db.get(models[config_name], config_id)
    if config is None:
        raise ValueError("知识库绑定的配置不存在")
    if config.space_id != kb.space_id:
        raise ValueError("知识库绑定的配置不属于当前空间")
    # Vector-store is_active selects the space default; explicit bindings can
    # reference a non-default store. Embedding is_active means enabled.
    if config_name == "embedding_config_id" and not config.is_active:
        raise ValueError("知识库绑定的向量模型配置已停用")
    return config
