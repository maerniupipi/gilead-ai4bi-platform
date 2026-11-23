"""
用户数据访问层
"""
from typing import List, Optional
from sqlalchemy.orm import Session
from ...models.user import User
from ...models.user_space_role import UserSpaceRole
from ...models.user_space_last_access import UserSpaceLastAccess


class UserRepository:
    """用户数据访问类"""

    @staticmethod
    def get_all(db: Session, skip: int = 0, limit: int = 100) -> List[User]:
        """获取所有用户"""
        return db.query(User).offset(skip).limit(limit).all()

    @staticmethod
    def count(db: Session) -> int:
        """统计用户数量"""
        return db.query(User).count()

    @staticmethod
    def count_super_admins(db: Session) -> int:
        """统计超级管理员数量"""
        return db.query(User).filter(User.system_role == "super_admin").count()

    @staticmethod
    def count_active_super_admins(db: Session) -> int:
        """统计启用的超级管理员数量"""
        return db.query(User).filter(
            User.system_role == "super_admin",
            User.is_active == True
        ).count()

    @staticmethod
    def get_by_id(db: Session, user_id: int) -> Optional[User]:
        """根据ID获取用户"""
        return db.query(User).filter(User.id == user_id).first()

    @staticmethod
    def get_by_username(db: Session, username: str) -> Optional[User]:
        """根据用户名获取用户"""
        return db.query(User).filter(User.username == username).first()

    @staticmethod
    def create(db: Session, username: str, display_name: str = None,
               password_hash: str = None, system_role: str = "member") -> User:
        """创建用户"""
        user = User(
            username=username,
            display_name=display_name or username,
            password_hash=password_hash,
            system_role=system_role,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def update(db: Session, user_id: int, **kwargs) -> Optional[User]:
        """更新用户"""
        user = UserRepository.get_by_id(db, user_id)
        if not user:
            return None
        for key, value in kwargs.items():
            if value is not None and hasattr(user, key):
                setattr(user, key, value)
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def delete(db: Session, user_id: int) -> bool:
        """删除用户"""
        user = UserRepository.get_by_id(db, user_id)
        if not user:
            return False
        db.query(UserSpaceRole).filter(UserSpaceRole.user_id == user_id).delete()
        db.query(UserSpaceLastAccess).filter(UserSpaceLastAccess.user_id == user_id).delete()
        db.delete(user)
        db.commit()
        return True

    @staticmethod
    def is_super_admin(db: Session, user_id: int) -> bool:
        """检查用户是否为超级管理员"""
        user = UserRepository.get_by_id(db, user_id)
        return user.system_role == "super_admin" if user else False

    @staticmethod
    def is_active_super_admin(db: Session, user_id: int) -> bool:
        """检查用户是否为启用的超级管理员"""
        user = UserRepository.get_by_id(db, user_id)
        return user and user.system_role == "super_admin" and user.is_active
