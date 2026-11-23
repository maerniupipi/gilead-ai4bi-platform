"""
OSS 配置服务
"""
import logging
from typing import List, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ...repositories.oss_config import OssConfigRepository
from ...schemas.oss_config import (
    OssConfigCreate,
    OssConfigResponse,
    OssConfigTestRequest,
    OssConfigTestResponse,
    OssConfigUpdate,
)
from .providers import get_oss_provider

logger = logging.getLogger(__name__)


class OssConfigService:
    @staticmethod
    def get_all(db: Session, skip: int = 0, limit: int = 100, space_id: int = None) -> List[OssConfigResponse]:
        return [OssConfigResponse.model_validate(x) for x in OssConfigRepository.get_all(db, skip, limit, space_id)]

    @staticmethod
    def get_default(db: Session, space_id: int = None):
        config = OssConfigRepository.get_default(db, space_id)
        return OssConfigResponse.model_validate(config) if config else None

    @staticmethod
    def create(db: Session, config: OssConfigCreate, space_id: int = 1) -> OssConfigResponse:
        return OssConfigResponse.model_validate(OssConfigRepository.create(db, config, space_id))

    @staticmethod
    def update(db: Session, config_id: int, config: OssConfigUpdate, space_id: int = None) -> OssConfigResponse:
        db_config = OssConfigRepository.update(db, config_id, config, space_id)
        if not db_config:
            raise HTTPException(status_code=404, detail="OSS 配置不存在")
        return OssConfigResponse.model_validate(db_config)

    @staticmethod
    def delete(db: Session, config_id: int, space_id: int = None) -> bool:
        if not OssConfigRepository.delete(db, config_id, space_id):
            raise HTTPException(status_code=404, detail="OSS 配置不存在")
        return True

    @staticmethod
    async def test_connection(config: OssConfigTestRequest) -> OssConfigTestResponse:
        provider = get_oss_provider(config.provider)
        try:
            ok = provider.test_connection({
                "endpoint": config.endpoint,
                "bucket": config.bucket,
                "access_key": config.access_key,
                "secret_key": config.secret_key,
                "region": config.region,
            })
            return OssConfigTestResponse(success=ok, message="连接测试成功" if ok else "连接测试失败")
        except Exception as e:
            logger.warning("OSS test_connection error: %s", e)
            return OssConfigTestResponse(success=False, message=str(e))

    @staticmethod
    def resolve_active_config(db: Optional[Session] = None, space_id: int = None):
        if not db:
            raise ValueError("数据库会话 required")
        config = OssConfigRepository.get_default(db, space_id)
        if not config:
            raise ValueError("OSS 配置未找到，请在管理中心配置")
        return OssConfigResponse.model_validate(config).model_dump()
