"""
系统更新日志 Router
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List
from ...core.database import get_db
from ...core.permissions import RequireSystemPermission
from ...schemas.system_update import (
    SystemUpdateCreate,
    SystemUpdateUpdate,
    SystemUpdateResponse,
    SystemUpdateList
)
from ...services.system_update import SystemUpdateService

router = APIRouter()


@router.get("/published", response_model=SystemUpdateList)
def get_published_updates(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """获取已发布的更新日志（公开接口）"""
    updates = SystemUpdateService.get_published_updates(db, skip, limit)
    total = SystemUpdateService.get_update_count(db)
    items = [SystemUpdateResponse.from_orm_with_label(u) for u in updates]
    return SystemUpdateList(items=items, total=total)


@router.get("/{update_id}", response_model=SystemUpdateResponse)
def get_update(
    update_id: int,
    db: Session = Depends(get_db)
):
    """获取更新日志详情"""
    update = SystemUpdateService.get_update_by_id(db, update_id)
    if not update:
        raise HTTPException(status_code=404, detail="更新日志不存在")
    return SystemUpdateResponse.from_orm_with_label(update)


@router.post("/", response_model=SystemUpdateResponse)
def create_update(
    update_data: SystemUpdateCreate,
    db: Session = Depends(get_db),
    operator_id: int = Depends(RequireSystemPermission("*"))
):
    """创建更新日志（管理员）"""
    update = SystemUpdateService.create_update(db, update_data)
    return SystemUpdateResponse.from_orm_with_label(update)


@router.put("/{update_id}", response_model=SystemUpdateResponse)
def update_update(
    update_id: int,
    update_data: SystemUpdateUpdate,
    db: Session = Depends(get_db),
    operator_id: int = Depends(RequireSystemPermission("*"))
):
    """更新更新日志（管理员）"""
    update = SystemUpdateService.update_update(db, update_id, update_data)
    if not update:
        raise HTTPException(status_code=404, detail="更新日志不存在")
    return SystemUpdateResponse.from_orm_with_label(update)


@router.delete("/{update_id}")
def delete_update(
    update_id: int,
    db: Session = Depends(get_db),
    operator_id: int = Depends(RequireSystemPermission("*"))
):
    """删除更新日志（管理员）"""
    success = SystemUpdateService.delete_update(db, update_id)
    if not success:
        raise HTTPException(status_code=404, detail="更新日志不存在")
    return {"message": "删除成功"}
