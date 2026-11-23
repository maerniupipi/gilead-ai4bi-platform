"""
ES配置路由
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ...core.database import get_db
from ...core.permissions import RequireSystemPermission
from ...schemas.es_config import (
    EsConfigCreate,
    EsConfigResponse,
    EsConfigTestRequest,
    EsConfigTestResponse,
    EsConfigUpdate,
)
from ...services.es_config.service import EsConfigService

router = APIRouter(prefix="/api/es-configs", tags=["ES配置"])


@router.get("", response_model=List[EsConfigResponse])
def list_es_configs(
    skip: int = 0,
    limit: int = 100,
    space_id: Optional[int] = Query(None, description="空间ID"),
    db: Session = Depends(get_db)
):
    return EsConfigService.get_all(db, skip, limit, space_id)


@router.get("/default", response_model=EsConfigResponse)
def get_default_es_config(
    space_id: Optional[int] = Query(None, description="空间ID"),
    db: Session = Depends(get_db)
):
    config = EsConfigService.get_default(db, space_id)
    if not config:
        raise HTTPException(status_code=404, detail="未找到默认配置")
    return config


@router.post("", response_model=EsConfigResponse)
def create_es_config(
    config: EsConfigCreate,
    space_id: Optional[int] = Query(1, description="空间ID"),
    db: Session = Depends(get_db),
    operator_id: int = Depends(RequireSystemPermission("*")),
):
    return EsConfigService.create(db, config, space_id)


@router.put("/{config_id}", response_model=EsConfigResponse)
def update_es_config(
    config_id: int,
    config: EsConfigUpdate,
    space_id: Optional[int] = Query(None, description="空间ID"),
    db: Session = Depends(get_db),
    operator_id: int = Depends(RequireSystemPermission("*")),
):
    return EsConfigService.update(db, config_id, config, space_id)


@router.delete("/{config_id}")
def delete_es_config(
    config_id: int,
    space_id: Optional[int] = Query(None, description="空间ID"),
    db: Session = Depends(get_db),
    operator_id: int = Depends(RequireSystemPermission("*")),
):
    EsConfigService.delete(db, config_id, space_id)
    return {"message": "删除成功"}


@router.post("/test", response_model=EsConfigTestResponse)
async def test_es_config(
    config: EsConfigTestRequest,
    operator_id: int = Depends(RequireSystemPermission("*")),
):
    return await EsConfigService.test_connection(config)