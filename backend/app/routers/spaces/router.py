"""
空间路由
"""
from typing import List
from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from ...core.database import get_db
from ...core.permissions import RequireSystemPermission, RequireSpacePermission
from ...services.space.service import SpaceService
from ...schemas.space import (
    SpaceCreate, SpaceUpdate, SpaceResponse,
    SpaceWithRole, SpaceListResponse, SpaceMemberAdd, SpaceMemberResponse,
    SpaceDeleteRequest
)

router = APIRouter(prefix="/api/spaces", tags=["空间管理"])


def get_current_user_id(x_user_id: int = Header(default=1, alias="X-User-Id", description="用户ID")) -> int:
    """获取当前用户ID"""
    return x_user_id


@router.get("/all", response_model=List[SpaceResponse])
def list_all_spaces_admin(
    db: Session = Depends(get_db),
    operator_id: int = Depends(RequireSystemPermission("*"))
):
    """管理员获取所有空间（包含成员数量）- 仅超级管理员"""
    return SpaceService.get_all_spaces_admin(db)


@router.get("", response_model=SpaceListResponse)
def list_spaces(
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    """获取用户可访问的所有空间"""
    return SpaceService.get_all_spaces(db, user_id)


@router.post("", response_model=SpaceResponse)
def create_space(
    space_data: SpaceCreate,
    db: Session = Depends(get_db),
    operator_id: int = Depends(RequireSystemPermission("*"))
):
    """创建新空间 - 仅超级管理员"""
    return SpaceService.create_space(db, space_data, operator_id)


@router.get("/current", response_model=SpaceResponse)
def get_current_space(
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    """获取当前工作空间"""
    space = SpaceService.get_current_space(db, user_id)
    if not space:
        raise ValueError("当前用户没有设置工作空间")
    return space


@router.get("/{space_id}", response_model=SpaceResponse)
def get_space(
    space_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    """获取指定空间"""
    return SpaceService.get_space_by_id(db, space_id, user_id)


@router.put("/{space_id}", response_model=SpaceResponse)
def update_space(
    space_id: int,
    space_data: SpaceUpdate,
    db: Session = Depends(get_db),
    operator_id: int = Depends(RequireSystemPermission("*"))
):
    """更新空间 - 仅超级管理员"""
    return SpaceService.update_space(db, space_id, space_data, operator_id)


@router.delete("/{space_id}")
def delete_space(
    space_id: int,
    body: SpaceDeleteRequest,
    db: Session = Depends(get_db),
    operator_id: int = Depends(RequireSystemPermission("*"))
):
    """删除空间 - 首次标记可彻底删除，再次确认后物理删除"""
    return SpaceService.delete_space(db, space_id, body, operator_id)


@router.post("/{space_id}/cancel-delete")
def cancel_delete_space(
    space_id: int,
    db: Session = Depends(get_db),
    operator_id: int = Depends(RequireSystemPermission("*"))
):
    """取消待删除状态"""
    return SpaceService.cancel_delete_space(db, space_id, operator_id)


@router.post("/switch/{space_id}", response_model=SpaceResponse)
def switch_space(
    space_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    """切换当前工作空间"""
    return SpaceService.switch_space(db, space_id, user_id)


@router.get("/{space_id}/members", response_model=List[SpaceMemberResponse])
def list_space_members(
    space_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    """获取空间成员列表"""
    return SpaceService.get_members(db, space_id, user_id)


@router.post("/{space_id}/members", response_model=SpaceMemberResponse)
def add_space_member(
    space_id: int,
    member_data: SpaceMemberAdd,
    db: Session = Depends(get_db),
    operator_info: tuple = Depends(RequireSpacePermission("space_member:add"))
):
    """添加空间成员"""
    operator_id, _ = operator_info
    return SpaceService.add_member(db, space_id, member_data, operator_id)


@router.delete("/{space_id}/members/{target_user_id}")
def remove_space_member(
    space_id: int,
    target_user_id: int,
    db: Session = Depends(get_db),
    operator_info: tuple = Depends(RequireSpacePermission("space_member:remove"))
):
    """移除空间成员"""
    operator_id, _ = operator_info
    SpaceService.remove_member(db, space_id, target_user_id, operator_id)
    return {"message": "移除成功"}
