"""
配置解析器 - 从数据库获取配置
"""
import logging
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class ConfigNotFoundError(Exception):
    """配置未找到异常"""
    pass


def resolve_embedding_config(db: Session, space_id: int = None, kb_id: int = None) -> Dict[str, Any]:
    """
    从数据库获取 embedding 配置
    """
    from ..repositories.embedding_config import EmbeddingConfigRepository
    from .knowledge.config_overrides import resolve_knowledge_base_config
    config = resolve_knowledge_base_config(db, kb_id, space_id, "embedding_config_id")
    if config is None:
        config = EmbeddingConfigRepository.get_default(db, space_id)
    if not config:
        raise ConfigNotFoundError("向量模型配置未找到，请在管理中心配置")
    return {
        "provider": config.provider,
        "api_key": config.api_key,
        "model": config.model,
        "dimension": config.dimension,
        "base_url": config.base_url,
    }


def resolve_es_config(db: Session, space_id: int = None) -> Dict[str, Any]:
    """
    从数据库获取 ES 配置
    """
    from ..repositories.es_config import EsConfigRepository
    config = EsConfigRepository.get_default(db, space_id)
    if not config:
        raise ConfigNotFoundError("ES配置未找到，请在管理中心配置")
    return {
        "host": config.host,
        "port": config.port,
        "username": config.username,
        "password": config.password,
    }


def resolve_vector_store_config(db: Session, space_id: int = None, kb_id: int = None) -> Dict[str, Any]:
    """
    从数据库获取向量库配置
    """
    from ..repositories.vector_store import VectorStoreRepository
    from ..schemas.vector_store import VectorStoreResponse
    from .knowledge.config_overrides import resolve_knowledge_base_config
    store = resolve_knowledge_base_config(db, kb_id, space_id, "vector_store_id")
    if store is None:
        store = VectorStoreRepository.get_active(db, space_id)
    if not store:
        raise ConfigNotFoundError("向量库配置未找到，请在管理中心配置")
    return VectorStoreResponse.model_validate(store).model_dump()
