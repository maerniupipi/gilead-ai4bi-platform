"""
用户服务层
"""
import hashlib
from typing import List, Optional
from fastapi import HTTPException
from sqlalchemy.orm import Session

from ...repositories.user.repository import UserRepository
from ...schemas.user import (
    UserCreate, UserUpdate, UserResponse, UserListResponse, UserLogin, CurrentUserResponse
)


# 有效的系统角色
VALID_SYSTEM_ROLES = ["super_admin", "admin", "member", "visitor"]


def _hash_password(password: str) -> str:
    """简单密码哈希（生产环境应使用bcrypt）"""
    return hashlib.sha256(password.encode()).hexdigest()


def _require_active_operator(db: Session, operator_id: int):
    operator = UserRepository.get_by_id(db, operator_id)
    if not operator or not operator.is_active:
        raise HTTPException(status_code=403, detail="当前用户不存在或已停用")
    return operator


class UserService:
    """用户服务类"""

    @staticmethod
    def list_users(db: Session, skip: int = 0, limit: int = 100) -> UserListResponse:
        """获取用户列表"""
        users = UserRepository.get_all(db, skip, limit)
        total = UserRepository.count(db)
        return UserListResponse(
            users=[UserResponse.model_validate(u) for u in users],
            total=total
        )

    @staticmethod
    def get_user(db: Session, user_id: int) -> UserResponse:
        """获取用户"""
        user = UserRepository.get_by_id(db, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在")
        return UserResponse.model_validate(user)

    @staticmethod
    def get_current_user(db: Session, user_id: int) -> CurrentUserResponse:
        """获取当前用户信息"""
        user = UserRepository.get_by_id(db, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在")
        if not user.is_active:
            raise HTTPException(status_code=403, detail="用户已被禁用")
        return CurrentUserResponse.model_validate(user)

    @staticmethod
    def login(db: Session, login_data: UserLogin) -> CurrentUserResponse:
        """用户登录"""
        user = UserRepository.get_by_username(db, login_data.username)
        if not user:
            raise HTTPException(status_code=401, detail="用户名或密码错误")
        if not user.is_active:
            raise HTTPException(status_code=403, detail="用户已被禁用")
        # 验证密码
        password_hash = _hash_password(login_data.password)
        if user.password_hash != password_hash:
            raise HTTPException(status_code=401, detail="用户名或密码错误")
        return CurrentUserResponse.model_validate(user)

    @staticmethod
    def create_user(db: Session, user_data: UserCreate, operator_id: int) -> UserResponse:
        """已登录用户创建账号。"""
        _require_active_operator(db, operator_id)

        # 检查用户名是否已存在
        existing = UserRepository.get_by_username(db, user_data.username)
        if existing:
            raise HTTPException(status_code=400, detail="用户名已存在")

        # 验证角色
        if user_data.system_role not in VALID_SYSTEM_ROLES:
            raise HTTPException(status_code=400, detail=f"无效的角色，有效值: {', '.join(VALID_SYSTEM_ROLES)}")

        # 至少保留一名超级管理员
        if user_data.system_role == "super_admin":
            super_admin_count = UserRepository.count_super_admins(db)
            if super_admin_count == 0:
                pass  # 允许创建第一个超级管理员
            else:
                raise HTTPException(status_code=400, detail="系统已有超级管理员，无法创建更多")

        password_hash = _hash_password(user_data.password) if user_data.password else _hash_password("123456")

        user = UserRepository.create(
            db,
            username=user_data.username,
            display_name=user_data.display_name,
            password_hash=password_hash,
            system_role=user_data.system_role,
        )

        return UserResponse.model_validate(user)

    @staticmethod
    def update_user(db: Session, user_id: int, user_data: UserUpdate, operator_id: int) -> UserResponse:
        """已登录用户更新账号配置。"""
        _require_active_operator(db, operator_id)

        user = UserRepository.get_by_id(db, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在")

        update_fields = {}
        if user_data.display_name is not None:
            update_fields["display_name"] = user_data.display_name
        if user_data.password is not None:
            update_fields["password_hash"] = _hash_password(user_data.password)
        if user_data.system_role is not None:
            if user_data.system_role not in VALID_SYSTEM_ROLES:
                raise HTTPException(status_code=400, detail=f"无效的角色")
            # 如果要把唯一超级管理员改成非超级管理员，不允许
            if user.system_role == "super_admin" and user_data.system_role != "super_admin":
                super_admin_count = UserRepository.count_super_admins(db)
                if super_admin_count <= 1:
                    raise HTTPException(status_code=400, detail="至少保留一名超级管理员")
            update_fields["system_role"] = user_data.system_role
        if user_data.is_active is not None:
            # 不能禁用唯一超级管理员
            if user.system_role == "super_admin" and not user_data.is_active:
                super_admin_count = UserRepository.count_active_super_admins(db)
                if super_admin_count <= 1:
                    raise HTTPException(status_code=400, detail="至少保留一名启用的超级管理员")
            update_fields["is_active"] = user_data.is_active

        updated = UserRepository.update(db, user_id, **update_fields)
        return UserResponse.model_validate(updated)

    @staticmethod
    def delete_user(db: Session, user_id: int, operator_id: int) -> bool:
        """已登录用户删除普通账号。"""
        _require_active_operator(db, operator_id)

        user = UserRepository.get_by_id(db, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在")

        if user.system_role == "super_admin":
            raise HTTPException(status_code=403, detail="不能删除超级管理员")

        # 不能删除自己
        if user.id == operator_id:
            raise HTTPException(status_code=403, detail="不能删除自己")

        return UserRepository.delete(db, user_id)
