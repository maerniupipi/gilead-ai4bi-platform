"""
OSS 配置路由
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ...core.database import get_db
from ...core.permissions import RequireSystemPermission
from ...schemas.oss_config import (
    OssConfigCreate,
    OssConfigResponse,
    OssConfigTestRequest,
    OssConfigTestResponse,
    OssConfigUpdate,
)
from ...services.oss.service import OssConfigService

router = APIRouter(prefix="/api/oss-configs", tags=["OSS配置"])


@router.get("", response_model=List[OssConfigResponse])
def list_oss_configs(
    skip: int = 0,
    limit: int = 100,
    space_id: Optional[int] = Query(None, description="空间ID"),
    db: Session = Depends(get_db)
):
    return OssConfigService.get_all(db, skip, limit, space_id)


@router.post("", response_model=OssConfigResponse)
def create_oss_config(
    config: OssConfigCreate,
    space_id: Optional[int] = Query(1, description="空间ID"),
    db: Session = Depends(get_db),
    operator_id: int = Depends(RequireSystemPermission("*")),
):
    return OssConfigService.create(db, config, space_id)


@router.put("/{config_id}", response_model=OssConfigResponse)
def update_oss_config(
    config_id: int,
    config: OssConfigUpdate,
    space_id: Optional[int] = Query(None, description="空间ID"),
    db: Session = Depends(get_db),
    operator_id: int = Depends(RequireSystemPermission("*")),
):
    return OssConfigService.update(db, config_id, config, space_id)


@router.delete("/{config_id}")
def delete_oss_config(
    config_id: int,
    space_id: Optional[int] = Query(None, description="空间ID"),
    db: Session = Depends(get_db),
    operator_id: int = Depends(RequireSystemPermission("*")),
):
    OssConfigService.delete(db, config_id, space_id)
    return {"message": "删除成功"}


@router.post("/test", response_model=OssConfigTestResponse)
async def test_oss_config(
    config: OssConfigTestRequest,
    operator_id: int = Depends(RequireSystemPermission("*")),
):
    return await OssConfigService.test_connection(config)
