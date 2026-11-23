"""
ES配置服务
"""
import logging
from typing import List, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session
from elasticsearch import Elasticsearch

from ..knowledge.azure_search_service import AzureAISearchService, is_azure_search_config
from ...repositories.es_config import EsConfigRepository
from ...schemas.es_config import (
    EsConfigCreate,
    EsConfigResponse,
    EsConfigTestRequest,
    EsConfigTestResponse,
    EsConfigUpdate,
)

logger = logging.getLogger(__name__)


class EsConfigService:
    @staticmethod
    def get_all(db: Session, skip: int = 0, limit: int = 100, space_id: int = None) -> List[EsConfigResponse]:
        return [EsConfigResponse.model_validate(x) for x in EsConfigRepository.get_all(db, skip, limit, space_id)]

    @staticmethod
    def get_default(db: Session, space_id: int = None):
        config = EsConfigRepository.get_default(db, space_id)
        return EsConfigResponse.model_validate(config) if config else None

    @staticmethod
    def get_by_id(db: Session, config_id: int, space_id: int = None) -> Optional[EsConfigResponse]:
        config = EsConfigRepository.get_by_id(db, config_id, space_id)
        return EsConfigResponse.model_validate(config) if config else None

    @staticmethod
    def create(db: Session, config: EsConfigCreate, space_id: int = 1) -> EsConfigResponse:
        return EsConfigResponse.model_validate(EsConfigRepository.create(db, config, space_id))

    @staticmethod
    def update(db: Session, config_id: int, config: EsConfigUpdate, space_id: int = None) -> EsConfigResponse:
        db_config = EsConfigRepository.update(db, config_id, config, space_id)
        if not db_config:
            raise HTTPException(status_code=404, detail="ES配置不存在")
        return EsConfigResponse.model_validate(db_config)

    @staticmethod
    def delete(db: Session, config_id: int, space_id: int = None) -> bool:
        if not EsConfigRepository.delete(db, config_id, space_id):
            raise HTTPException(status_code=404, detail="ES配置不存在")
        return True

    @staticmethod
    async def test_connection(config: EsConfigTestRequest) -> EsConfigTestResponse:
        """测试ES连接"""
        try:
            cfg = config.model_dump()
            if is_azure_search_config(cfg):
                ok = AzureAISearchService(cfg).test_connection()
                return EsConfigTestResponse(
                    success=ok,
                    message="Azure AI Search 连接成功" if ok else "Azure AI Search 连接失败",
                )
            from ..knowledge.es_service import ElasticsearchService
            search = ElasticsearchService(cfg)
            if search.is_opensearch:
                try:
                    info = search.get_client().info()
                    return EsConfigTestResponse(success=True, message="OpenSearch 连接成功",
                        response_data={"version": info["version"]["number"]})
                finally:
                    search.close()
            host = config.host
            if config.port:
                host = f"{host}:{config.port}"
            client = Elasticsearch(
                host,
                basic_auth=(config.username, config.password) if config.username else None
            )
            info = client.info()
            return EsConfigTestResponse(
                success=True,
                message="连接成功",
                response_data={"version": info.get("version", {}).get("number")}
            )
        except Exception as e:
            return EsConfigTestResponse(success=False, message=str(e))

    @staticmethod
    def resolve_active_config(db: Session, space_id: int = None) -> dict:
        """从数据库获取配置"""
        if not db:
            raise ValueError("数据库会话 required")
        config = EsConfigRepository.get_default(db, space_id)
        if not config:
            raise ValueError("ES配置未找到，请在管理中心配置")
        return {
            "host": config.host,
            "port": config.port,
            "username": config.username,
            "password": config.password,
        }
