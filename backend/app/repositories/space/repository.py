"""
空间数据访问层
"""
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import or_
from ...models.space import Space
from ...models.user_space_role import UserSpaceRole
from ...models.user_space_last_access import UserSpaceLastAccess
from ...models.user import User
from ...schemas.space import SpaceCreate, SpaceUpdate


class SpaceRepository:
    """空间数据访问类"""

    @staticmethod
    def get_all(db: Session) -> List[Space]:
        """获取所有空间"""
        return db.query(Space).all()

    @staticmethod
    def get_by_id(db: Session, space_id: int) -> Optional[Space]:
        """根据ID获取空间"""
        return db.query(Space).filter(Space.id == space_id).first()

    @staticmethod
    def get_by_code(db: Session, code: str) -> Optional[Space]:
        """根据编码获取空间"""
        return db.query(Space).filter(Space.code == code).first()

    @staticmethod
    def create(db: Session, space_data: SpaceCreate) -> Space:
        """创建空间"""
        space = Space(**space_data.model_dump())
        db.add(space)
        db.commit()
        db.refresh(space)
        return space

    @staticmethod
    def update(db: Session, space_id: int, space_data: SpaceUpdate) -> Optional[Space]:
        """更新空间"""
        space = SpaceRepository.get_by_id(db, space_id)
        if not space:
            return None
        update_data = space_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(space, field, value)
        db.commit()
        db.refresh(space)
        return space

    @staticmethod
    def update_settings(db: Session, space_id: int, settings: dict) -> Optional[Space]:
        """更新空间 settings"""
        space = SpaceRepository.get_by_id(db, space_id)
        if not space:
            return None
        space.settings = settings
        db.commit()
        db.refresh(space)
        return space

    @staticmethod
    def hard_delete(db: Session, space_id: int) -> bool:
        """物理删除空间及其成员关系"""
        space = SpaceRepository.get_by_id(db, space_id)
        if not space:
            return False

        db.query(UserSpaceLastAccess).filter(
            UserSpaceLastAccess.last_space_id == space_id
        ).update({UserSpaceLastAccess.last_space_id: 1}, synchronize_session=False)

        db.query(UserSpaceRole).filter(UserSpaceRole.space_id == space_id).delete(
            synchronize_session=False
        )
        db.delete(space)
        db.commit()
        return True

    @staticmethod
    def get_user_spaces(db: Session, user_id: int) -> List[dict]:
        """获取用户可访问的所有空间及其角色"""
        roles = db.query(UserSpaceRole).filter(
            UserSpaceRole.user_id == user_id
        ).all()
        space_ids = [r.space_id for r in roles]
        role_map = {r.space_id: r.role for r in roles}

        if not space_ids:
            return []

        spaces = db.query(Space).filter(
            Space.id.in_(space_ids),
            Space.is_active == True
        ).all()

        result = []
        for space in spaces:
            space_dict = {
                "id": space.id,
                "name": space.name,
                "code": space.code,
                "description": space.description,
                "avatar": space.avatar,
                "is_active": space.is_active,
                "settings": space.settings,
                "created_at": space.created_at,
                "updated_at": space.updated_at,
                "role": role_map.get(space.id, "viewer")
            }
            result.append(space_dict)
        return result

    @staticmethod
    def add_user_role(db: Session, user_id: int, space_id: int, role: str = "member") -> UserSpaceRole:
        """添加用户到空间"""
        existing = db.query(UserSpaceRole).filter(
            UserSpaceRole.user_id == user_id,
            UserSpaceRole.space_id == space_id
        ).first()

        if existing:
            existing.role = role
            db.commit()
            db.refresh(existing)
            return existing

        user_role = UserSpaceRole(
            user_id=user_id,
            space_id=space_id,
            role=role
        )
        db.add(user_role)
        db.commit()
        db.refresh(user_role)
        return user_role

    @staticmethod
    def remove_user_role(db: Session, user_id: int, space_id: int) -> bool:
        """从空间移除用户"""
        result = db.query(UserSpaceRole).filter(
            UserSpaceRole.user_id == user_id,
            UserSpaceRole.space_id == space_id
        ).delete()
        db.commit()
        return result > 0

    @staticmethod
    def get_user_role(db: Session, user_id: int, space_id: int) -> Optional[str]:
        """获取用户在空间中的角色"""
        role = db.query(UserSpaceRole).filter(
            UserSpaceRole.user_id == user_id,
            UserSpaceRole.space_id == space_id
        ).first()
        return role.role if role else None

    @staticmethod
    def get_user_last_access(db: Session, user_id: int) -> Optional[int]:
        """获取用户最后访问的空间ID"""
        record = db.query(UserSpaceLastAccess).filter(
            UserSpaceLastAccess.user_id == user_id
        ).first()
        return record.last_space_id if record else None

    @staticmethod
    def set_user_last_access(db: Session, user_id: int, space_id: int) -> UserSpaceLastAccess:
        """设置用户最后访问的空间"""
        record = db.query(UserSpaceLastAccess).filter(
            UserSpaceLastAccess.user_id == user_id
        ).first()

        if record:
            record.last_space_id = space_id
        else:
            record = UserSpaceLastAccess(user_id=user_id, last_space_id=space_id)
            db.add(record)

        db.commit()
        db.refresh(record)
        return record

    @staticmethod
    def get_space_members(db: Session, space_id: int) -> List[dict]:
        """获取空间的所有成员（包含用户显示名称）"""
        results = db.query(UserSpaceRole, User).join(
            User, UserSpaceRole.user_id == User.id
        ).filter(UserSpaceRole.space_id == space_id).all()

        members = []
        for role, user in results:
            members.append({
                "user_id": role.user_id,
                "display_name": user.display_name or user.username,
                "role": role.role,
                "created_at": role.created_at,
            })
        return members

    @staticmethod
    def is_user_in_space(db: Session, user_id: int, space_id: int) -> bool:
        """检查用户是否在空间中"""
        role = db.query(UserSpaceRole).filter(
            UserSpaceRole.user_id == user_id,
            UserSpaceRole.space_id == space_id
        ).first()
        return role is not None
