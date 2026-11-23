"""
模型供应商业务逻辑层
"""
import json
import httpx
from typing import List, Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException

from ...core.llm_policy import model_thinking_payload
from ...core.model_stream import complete_async
from ...repositories.model_provider import ModelProviderRepository
from ...schemas.model_provider import (
    ModelProviderCreate,
    ModelProviderUpdate,
    ModelProviderResponse,
    ModelTestRequest,
    ModelTestResponse,
)


class ModelProviderService:
    """模型供应商Service"""

    @staticmethod
    def get_all_providers(db: Session, skip: int = 0, limit: int = 100) -> List[ModelProviderResponse]:
        """获取所有供应商"""
        providers = ModelProviderRepository.get_all(db, skip, limit)
        return [ModelProviderResponse.model_validate(p) for p in providers]

    @staticmethod
    def get_provider(db: Session, provider_id: int) -> ModelProviderResponse:
        """获取单个供应商"""
        provider = ModelProviderRepository.get_by_id(db, provider_id)
        if not provider:
            raise HTTPException(status_code=404, detail="供应商不存在")
        return ModelProviderResponse.model_validate(provider)

    @staticmethod
    def create_provider(db: Session, provider: ModelProviderCreate) -> ModelProviderResponse:
        """创建供应商"""
        db_provider = ModelProviderRepository.create(db, provider)
        return ModelProviderResponse.model_validate(db_provider)

    @staticmethod
    def update_provider(db: Session, provider_id: int, provider: ModelProviderUpdate) -> ModelProviderResponse:
        """更新供应商"""
        db_provider = ModelProviderRepository.update(db, provider_id, provider)
        if not db_provider:
            raise HTTPException(status_code=404, detail="供应商不存在")
        return ModelProviderResponse.model_validate(db_provider)

    @staticmethod
    def delete_provider(db: Session, provider_id: int) -> bool:
        """删除供应商"""
        success = ModelProviderRepository.delete(db, provider_id)
        if not success:
            raise HTTPException(status_code=404, detail="供应商不存在")
        return True

    @staticmethod
    async def test_model(test_request: ModelTestRequest) -> ModelTestResponse:
        """测试模型连接"""
        try:
            headers = {
                "Content-Type": "application/json",
            }

            if test_request.api_key:
                headers["Authorization"] = f"Bearer {test_request.api_key}"

            # 构建测试请求
            if test_request.protocol == "openai":
                url = f"{test_request.base_url.rstrip('/')}/chat/completions"
                payload = {
                    "model": test_request.model,
                    "messages": [{"role": "user", "content": "Hello"}],
                    "max_tokens": 10,
                }
            else:
                return ModelTestResponse(
                    success=False,
                    message=f"暂不支持 {test_request.protocol} 协议的测试",
                )

            data = await complete_async(url, model_thinking_payload(payload, test_request), headers,
                timeout=30.0, operation='test_model', provider=test_request.protocol)
            return ModelTestResponse(success=True, message='连接测试成功', response_data=data)

        except httpx.TimeoutException:
            return ModelTestResponse(success=False, message="请求超时，请检查网络或URL")
        except Exception as e:
            return ModelTestResponse(success=False, message=f"测试失败: {str(e)}")
