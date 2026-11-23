"""
模型供应商路由
"""
from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...core.database import get_db
from ...core.permissions import RequireSystemPermission
from ...schemas.model_provider import (
    ModelProviderCreate,
    ModelProviderUpdate,
    ModelProviderResponse,
    ModelTestRequest,
    ModelTestResponse,
)
from ...services.model_provider import ModelProviderService

router = APIRouter(prefix="/api/model-providers", tags=["模型供应商"])


@router.get("", response_model=List[ModelProviderResponse])
def get_providers(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """获取所有模型供应商"""
    return ModelProviderService.get_all_providers(db, skip, limit)


@router.get("/{provider_id}", response_model=ModelProviderResponse)
def get_provider(provider_id: int, db: Session = Depends(get_db)):
    """获取单个模型供应商"""
    return ModelProviderService.get_provider(db, provider_id)


@router.post("", response_model=ModelProviderResponse)
def create_provider(
    provider: ModelProviderCreate,
    db: Session = Depends(get_db),
    operator_id: int = Depends(RequireSystemPermission("*")),
):
    """创建模型供应商（仅超级管理员）"""
    return ModelProviderService.create_provider(db, provider)


@router.put("/{provider_id}", response_model=ModelProviderResponse)
def update_provider(
    provider_id: int,
    provider: ModelProviderUpdate,
    db: Session = Depends(get_db),
    operator_id: int = Depends(RequireSystemPermission("*")),
):
    """更新模型供应商（仅超级管理员）"""
    return ModelProviderService.update_provider(db, provider_id, provider)


@router.delete("/{provider_id}")
def delete_provider(
    provider_id: int,
    db: Session = Depends(get_db),
    operator_id: int = Depends(RequireSystemPermission("*")),
):
    """删除模型供应商（仅超级管理员）"""
    ModelProviderService.delete_provider(db, provider_id)
    return {"message": "删除成功"}


@router.post("/test", response_model=ModelTestResponse)
async def test_model(
    test_request: ModelTestRequest,
    operator_id: int = Depends(RequireSystemPermission("*")),
):
    """测试模型连接（仅超级管理员）"""
    return await ModelProviderService.test_model(test_request)
