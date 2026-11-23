"""
向量模型配置服务
"""
import logging
from typing import List, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ...repositories.embedding_config import EmbeddingConfigRepository
from ...schemas.embedding_config import (
    EmbeddingConfigCreate,
    EmbeddingConfigResponse,
    EmbeddingConfigUpdate,
)

logger = logging.getLogger(__name__)


def _validate_api_key(api_key: Optional[str]) -> Optional[str]:
    if api_key is None:
        return None
    value = api_key.strip()
    if not value:
        return value
    try:
        value.encode("latin-1")
    except UnicodeEncodeError as exc:
        raise HTTPException(
            status_code=400,
            detail="向量模型 API Key 配置错误：不能包含中文或其他非 ASCII 字符，请填写真实密钥",
        ) from exc
    return value


class EmbeddingConfigService:
    @staticmethod
    def get_all(db: Session, skip: int = 0, limit: int = 100, space_id: int = None) -> List[EmbeddingConfigResponse]:
        return [EmbeddingConfigResponse.model_validate(x) for x in EmbeddingConfigRepository.get_all(db, skip, limit, space_id)]

    @staticmethod
    def get_default(db: Session, space_id: int = None):
        config = EmbeddingConfigRepository.get_default(db, space_id)
        return EmbeddingConfigResponse.model_validate(config) if config else None

    @staticmethod
    def get_by_id(db: Session, config_id: int, space_id: int = None) -> Optional[EmbeddingConfigResponse]:
        config = EmbeddingConfigRepository.get_by_id(db, config_id, space_id)
        return EmbeddingConfigResponse.model_validate(config) if config else None

    @staticmethod
    def create(db: Session, config: EmbeddingConfigCreate, space_id: int = 1) -> EmbeddingConfigResponse:
        config.api_key = _validate_api_key(config.api_key)
        return EmbeddingConfigResponse.model_validate(EmbeddingConfigRepository.create(db, config, space_id))

    @staticmethod
    def update(db: Session, config_id: int, config: EmbeddingConfigUpdate, space_id: int = None) -> EmbeddingConfigResponse:
        if config.api_key is not None:
            config.api_key = _validate_api_key(config.api_key)
        db_config = EmbeddingConfigRepository.update(db, config_id, config, space_id)
        if not db_config:
            raise HTTPException(status_code=404, detail="向量模型配置不存在")
        return EmbeddingConfigResponse.model_validate(db_config)

    @staticmethod
    def delete(db: Session, config_id: int, space_id: int = None) -> bool:
        if not EmbeddingConfigRepository.delete(db, config_id, space_id):
            raise HTTPException(status_code=404, detail="向量模型配置不存在")
        return True

    @staticmethod
    def resolve_active_config(db: Session, space_id: int = None) -> dict:
        """从数据库获取配置"""
        if not db:
            raise ValueError("数据库会话 required")
        config = EmbeddingConfigRepository.get_default(db, space_id)
        if not config:
            raise ValueError("向量模型配置未找到，请在管理中心配置")
        return {
            "provider": config.provider,
            "api_key": config.api_key,
            "model": config.model,
            "dimension": config.dimension,
            "base_url": config.base_url,
        }
