"""
用户管理路由
"""
from typing import List
from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy.orm import Session

from ...core.database import get_db
from ...core.permissions import require_platform_user
from ...services.user.service import UserService
from ...schemas.user import (
    UserCreate, UserUpdate, UserResponse, UserListResponse,
    UserLogin, CurrentUserResponse
)

router = APIRouter(prefix="/api/users", tags=["用户管理"])


def logged_in_operator(request: Request, db: Session = Depends(get_db)) -> int:
    return require_platform_user(request, db)


def get_current_user_id(x_user_id: int = Header(default=1, alias="X-User-Id", description="用户ID")) -> int:
    """获取当前用户ID"""
    return x_user_id


@router.post("/login", response_model=CurrentUserResponse)
def login(login_data: UserLogin, request: Request, db: Session = Depends(get_db)):
    """用户登录"""
    user = UserService.login(db, login_data)
    if "session" in request.scope:
        request.session.clear()
        request.session["user_id"] = user.id
    return user


@router.post("/logout")
def logout(request: Request):
    if "session" in request.scope:
        request.session.clear()
    return {"ok": True}


@router.get("/current", response_model=CurrentUserResponse)
def get_current_user(
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id)
):
    """获取当前登录用户信息"""
    return UserService.get_current_user(db, current_user_id)


@router.get("", response_model=UserListResponse)
def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    operator_id: int = Depends(logged_in_operator),
):
    """获取用户列表，所有启用且已登录的平台用户可访问。"""
    return UserService.list_users(db, skip, limit)


@router.get("/{user_id}", response_model=UserResponse)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    operator_id: int = Depends(logged_in_operator),
):
    """获取用户详情，平台登录后可访问"""
    return UserService.get_user(db, user_id)


@router.post("", response_model=UserResponse)
def create_user(
    user_data: UserCreate,
    db: Session = Depends(get_db),
    operator_id: int = Depends(logged_in_operator)
):
    """创建用户，平台登录后可配置"""
    return UserService.create_user(db, user_data, operator_id)


@router.put("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: int,
    user_data: UserUpdate,
    db: Session = Depends(get_db),
    operator_id: int = Depends(logged_in_operator)
):
    """更新用户，平台登录后可配置"""
    return UserService.update_user(db, user_id, user_data, operator_id)


@router.delete("/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    operator_id: int = Depends(logged_in_operator)
):
    """删除用户，平台登录后可配置"""
    UserService.delete_user(db, user_id, operator_id)
    return {"message": "删除成功"}
