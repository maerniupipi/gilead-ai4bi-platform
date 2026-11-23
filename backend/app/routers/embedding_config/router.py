"""
向量模型配置路由
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ...core.database import get_db
from ...core.permissions import RequireSystemPermission
from ...schemas.embedding_config import (
    EmbeddingConfigCreate,
    EmbeddingConfigResponse,
    EmbeddingConfigUpdate,
)
from ...services.embedding_config.service import EmbeddingConfigService

router = APIRouter(prefix="/api/embedding-configs", tags=["向量模型配置"])


@router.get("", response_model=List[EmbeddingConfigResponse])
def list_embedding_configs(
    skip: int = 0,
    limit: int = 100,
    space_id: Optional[int] = Query(None, description="空间ID"),
    db: Session = Depends(get_db)
):
    return EmbeddingConfigService.get_all(db, skip, limit, space_id)


@router.get("/default", response_model=EmbeddingConfigResponse)
def get_default_embedding_config(
    space_id: Optional[int] = Query(None, description="空间ID"),
    db: Session = Depends(get_db)
):
    config = EmbeddingConfigService.get_default(db, space_id)
    if not config:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="未找到默认配置")
    return config


@router.post("", response_model=EmbeddingConfigResponse)
def create_embedding_config(
    config: EmbeddingConfigCreate,
    space_id: Optional[int] = Query(1, description="空间ID"),
    db: Session = Depends(get_db),
    operator_id: int = Depends(RequireSystemPermission("*")),
):
    return EmbeddingConfigService.create(db, config, space_id)


@router.put("/{config_id}", response_model=EmbeddingConfigResponse)
def update_embedding_config(
    config_id: int,
    config: EmbeddingConfigUpdate,
    space_id: Optional[int] = Query(None, description="空间ID"),
    db: Session = Depends(get_db),
    operator_id: int = Depends(RequireSystemPermission("*")),
):
    return EmbeddingConfigService.update(db, config_id, config, space_id)


@router.delete("/{config_id}")
def delete_embedding_config(
    config_id: int,
    space_id: Optional[int] = Query(None, description="空间ID"),
    db: Session = Depends(get_db),
    operator_id: int = Depends(RequireSystemPermission("*")),
):
    EmbeddingConfigService.delete(db, config_id, space_id)
    return {"message": "删除成功"}