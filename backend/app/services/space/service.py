"""
空间服务层
"""
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import HTTPException
from sqlalchemy.orm import Session

from ...repositories.space.repository import SpaceRepository
from ...repositories.user.repository import UserRepository
from ...schemas.space import (
    SpaceCreate, SpaceUpdate, SpaceResponse,
    SpaceWithRole, SpaceListResponse, SpaceMemberAdd, SpaceMemberResponse,
    SpaceDeleteRequest
)


def _parse_iso_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _space_delete_meta(space) -> dict:
    settings = space.settings if isinstance(space.settings, dict) else {}
    deletion = settings.get("deletion") if isinstance(settings.get("deletion"), dict) else {}
    requested_at = _parse_iso_dt(deletion.get("requested_at"))
    available_at = _parse_iso_dt(deletion.get("available_at"))
    return {
        "delete_requested_at": requested_at,
        "delete_available_at": available_at,
    }


def _space_response_payload(space, member_count: Optional[int] = None) -> dict:
    payload = {
        "id": space.id,
        "name": space.name,
        "code": space.code,
        "description": space.description,
        "avatar": space.avatar,
        "is_active": space.is_active,
        "settings": space.settings,
        "member_count": member_count,
        "created_at": space.created_at,
        "updated_at": space.updated_at,
    }
    payload.update(_space_delete_meta(space))
    return payload


class SpaceService:
    """空间服务类"""

    @staticmethod
    def get_all_spaces_admin(db: Session) -> List[SpaceResponse]:
        """管理员获取所有空间（包含成员数量）"""
        spaces = SpaceRepository.get_all(db)
        result = []
        for space in spaces:
            members = SpaceRepository.get_space_members(db, space.id)
            result.append(SpaceResponse.model_validate(_space_response_payload(space, len(members))))
        return result

    @staticmethod
    def get_all_spaces(db: Session, user_id: int) -> SpaceListResponse:
        """获取用户可访问的所有空间"""
        if UserRepository.is_super_admin(db, user_id):
            spaces = [
                {**_space_response_payload(space), "role": "super_admin"}
                for space in SpaceRepository.get_all(db)
            ]
        else:
            spaces = SpaceRepository.get_user_spaces(db, user_id)
        current_space_id = SpaceRepository.get_user_last_access(db, user_id)

        # 如果用户没有设置过最后访问空间，且有空间，则默认选择第一个
        if not current_space_id and spaces:
            current_space_id = spaces[0].get("id")

        return SpaceListResponse(
            spaces=[SpaceWithRole(**s) for s in spaces],
            current_space_id=current_space_id
        )

    @staticmethod
    def get_space_by_id(db: Session, space_id: int, user_id: int) -> SpaceResponse:
        """获取指定空间"""
        space = SpaceRepository.get_by_id(db, space_id)
        if not space:
            raise HTTPException(status_code=404, detail="空间不存在")
        return SpaceResponse.model_validate(_space_response_payload(space))

    @staticmethod
    def create_space(db: Session, space_data: SpaceCreate, user_id: int) -> SpaceResponse:
        """创建新空间"""
        # 检查编码是否已存在
        existing = SpaceRepository.get_by_code(db, space_data.code)
        if existing:
            raise HTTPException(status_code=400, detail="空间编码已存在")

        space = SpaceRepository.create(db, space_data)

        # 超级管理员天然拥有所有空间权限，不需要额外加入；普通创建者成为空间管理员。
        if not UserRepository.is_super_admin(db, user_id):
            SpaceRepository.add_user_role(db, user_id, space.id, "admin")

        return SpaceResponse.model_validate(_space_response_payload(space))

    @staticmethod
    def update_space(db: Session, space_id: int, space_data: SpaceUpdate, user_id: int) -> SpaceResponse:
        """更新空间"""
        # 默认空间不能禁用
        space = SpaceRepository.get_by_id(db, space_id)
        if not space:
            raise HTTPException(status_code=404, detail="空间不存在")
        if (space.id == 1 or space.code == "default") and space_data.is_active is False:
            raise HTTPException(status_code=400, detail="默认空间不能禁用")

        # 检查编码是否冲突
        if space_data.code:
            existing = SpaceRepository.get_by_code(db, space_data.code)
            if existing and existing.id != space_id:
                raise HTTPException(status_code=400, detail="空间编码已存在")

        space = SpaceRepository.update(db, space_id, space_data)
        if not space:
            raise HTTPException(status_code=404, detail="空间不存在")
        return SpaceResponse.model_validate(_space_response_payload(space))

    @staticmethod
    def delete_space(db: Session, space_id: int, body: SpaceDeleteRequest, user_id: int) -> dict:
        """两阶段删除：首次标记为可彻底删除并禁用，再次确认后物理删除。"""
        space = SpaceRepository.get_by_id(db, space_id)
        if not space:
            raise HTTPException(status_code=404, detail="空间不存在")
        if space_id == 1 or space.code == "default":
            raise HTTPException(status_code=400, detail="默认空间不能删除")

        settings = dict(space.settings) if isinstance(space.settings, dict) else {}
        deletion = settings.get("deletion") if isinstance(settings.get("deletion"), dict) else {}
        available_at = _parse_iso_dt(deletion.get("available_at"))
        now = _utcnow()

        if not available_at:
            requested_at = now
            settings["deletion"] = {
                "requested_at": requested_at.isoformat(),
                "available_at": requested_at.isoformat(),
                "requested_by": user_id,
            }
            SpaceRepository.update_settings(db, space_id, settings)
            SpaceRepository.update(
                db,
                space_id,
                SpaceUpdate(is_active=False),
            )
            return {
                "status": "pending",
                "message": "空间已禁用，请再次确认以彻底删除",
                "delete_requested_at": requested_at,
                "delete_available_at": requested_at,
            }

        if body.confirm_name and body.confirm_name != space.name:
            raise HTTPException(status_code=400, detail="空间名称输入不一致")

        success = SpaceRepository.hard_delete(db, space_id)
        if not success:
            raise HTTPException(status_code=404, detail="空间不存在")
        return {"status": "deleted", "message": "删除成功"}

    @staticmethod
    def cancel_delete_space(db: Session, space_id: int, user_id: int) -> dict:
        """取消待删除状态并恢复启用"""
        space = SpaceRepository.get_by_id(db, space_id)
        if not space:
            raise HTTPException(status_code=404, detail="空间不存在")

        settings = dict(space.settings) if isinstance(space.settings, dict) else {}
        deletion = settings.get("deletion") if isinstance(settings.get("deletion"), dict) else {}
        if not deletion.get("available_at"):
            raise HTTPException(status_code=400, detail="该空间未处于待删除状态")

        settings.pop("deletion", None)
        SpaceRepository.update_settings(db, space_id, settings)
        SpaceRepository.update(db, space_id, SpaceUpdate(is_active=True))
        return {"status": "cancelled", "message": "已取消删除"}

    @staticmethod
    def switch_space(db: Session, space_id: int, user_id: int) -> SpaceResponse:
        """切换当前工作空间"""
        # 检查空间是否存在
        space = SpaceRepository.get_by_id(db, space_id)
        if not space:
            raise HTTPException(status_code=404, detail="空间不存在")

        # 设置最后访问空间
        SpaceRepository.set_user_last_access(db, user_id, space_id)

        return SpaceResponse.model_validate(_space_response_payload(space))

    @staticmethod
    def get_current_space(db: Session, user_id: int) -> Optional[SpaceResponse]:
        """获取当前工作空间"""
        space_id = SpaceRepository.get_user_last_access(db, user_id)
        if not space_id:
            if UserRepository.is_super_admin(db, user_id):
                spaces = SpaceRepository.get_all(db)
                return SpaceResponse.model_validate(_space_response_payload(spaces[0])) if spaces else None
            return None

        space = SpaceRepository.get_by_id(db, space_id)
        if not space:
            return None

        return SpaceResponse.model_validate(_space_response_payload(space))

    @staticmethod
    def add_member(db: Session, space_id: int, member_data: SpaceMemberAdd, user_id: int) -> SpaceMemberResponse:
        """添加空间成员"""
        # 检查空间是否存在
        space = SpaceRepository.get_by_id(db, space_id)
        if not space:
            raise HTTPException(status_code=404, detail="空间不存在")
        user = UserRepository.get_by_id(db, member_data.user_id)
        if not user or not user.is_active:
            raise HTTPException(status_code=404, detail="用户不存在或已禁用")

        user_role = SpaceRepository.add_user_role(db, member_data.user_id, space_id, member_data.role)
        return SpaceMemberResponse.model_validate(user_role)

    @staticmethod
    def remove_member(db: Session, space_id: int, target_user_id: int, user_id: int) -> bool:
        """移除空间成员"""
        # 不能移除owner
        target_role = SpaceRepository.get_user_role(db, target_user_id, space_id)
        if target_role == "owner":
            raise HTTPException(status_code=400, detail="不能移除空间所有者")

        success = SpaceRepository.remove_user_role(db, target_user_id, space_id)
        if not success:
            raise HTTPException(status_code=404, detail="成员不在空间中")
        return True

    @staticmethod
    def get_members(db: Session, space_id: int, user_id: int) -> List[SpaceMemberResponse]:
        """获取空间成员列表"""
        members = SpaceRepository.get_space_members(db, space_id)
        return [SpaceMemberResponse.model_validate(m) for m in members]

    @staticmethod
    def ensure_user_in_default_space(db: Session, user_id: int) -> int:
        """确保用户在默认空间中，不存在则创建并加入"""
        # 获取ID为1的空间
        space = SpaceRepository.get_by_id(db, 1)
        if not space:
            return 0

        # 检查用户是否在空间中
        if not UserRepository.is_super_admin(db, user_id) and not SpaceRepository.is_user_in_space(db, user_id, space.id):
            SpaceRepository.add_user_role(db, user_id, space.id, "owner")

        return space.id
