"""平台配置统一向已登录用户开放，角色仅作为账号资料保留。"""
from fastapi import HTTPException, Depends, Request
from sqlalchemy.orm import Session

from .database import get_db
from ..repositories.user.repository import UserRepository


def get_current_user_id(request: Request) -> int:
    """兼容既有非配置接口的用户标识读取方式。"""
    user_id = request.headers.get("X-User-Id")
    if user_id:
        return int(user_id)
    return 1


def require_platform_user(request: Request, db: Session) -> int:
    """复用平台普通登录身份，不要求额外管理会话或管理员角色。"""
    try:
        user_id = int(request.headers.get("X-User-Id", ""))
        if user_id < 1:
            raise ValueError
    except ValueError as exc:
        raise HTTPException(401, "请先登录平台") from exc
    user = UserRepository.get_by_id(db, user_id)
    if user is None or not user.is_active:
        raise HTTPException(403, "当前平台账号不存在或已停用")
    return user_id


def check_system_permission(user_id: int, permission: str, db: Session) -> bool:
    """兼容旧调用；所有启用的平台用户都可配置。"""
    user = UserRepository.get_by_id(db, user_id)
    return bool(user and user.is_active)


def check_space_permission(user_id: int, space_id: int, permission: str, db: Session) -> bool:
    return check_system_permission(user_id, permission, db)


class RequireSystemPermission:
    """兼容既有路由声明，配置访问仅使用平台登录状态。"""
    def __init__(self, permission: str):
        self.permission = permission

    def __call__(self, request: Request, db: Session = Depends(get_db)) -> int:
        with Session(bind=db.get_bind()) as auth_db:
            return require_platform_user(request, auth_db)


def _get_space_id_from_request(request: Request) -> int:
    if "space_id" in request.path_params:
        return int(request.path_params["space_id"])
    if "space_id" in request.query_params:
        return int(request.query_params["space_id"])
    return 0


class RequireSpacePermission:
    """空间配置与其他平台配置使用相同登录入口。"""
    def __init__(self, permission: str):
        self.permission = permission

    def __call__(self, request: Request, db: Session = Depends(get_db)) -> tuple:
        with Session(bind=db.get_bind()) as auth_db:
            return require_platform_user(request, auth_db), _get_space_id_from_request(request) or None


# 保留既有依赖名称，所有名称均采用相同的登录后开放策略。
require_super_admin = RequireSystemPermission("*")
require_admin = RequireSystemPermission("model_config:manage")
require_space_admin = RequireSpacePermission("space_member:add")
