"""
系统更新日志 Service
"""
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import List, Optional
from ..models.system_update import SystemUpdate
from ..schemas.system_update import SystemUpdateCreate, SystemUpdateUpdate


class SystemUpdateService:
    """系统更新日志服务"""

    @staticmethod
    def get_published_updates(
        db: Session,
        skip: int = 0,
        limit: int = 20
    ) -> List[SystemUpdate]:
        """获取已发布的更新日志"""
        return (
            db.query(SystemUpdate)
            .filter(SystemUpdate.is_published == True)
            .order_by(desc(SystemUpdate.release_date))
            .offset(skip)
            .limit(limit)
            .all()
        )

    @staticmethod
    def get_update_by_id(db: Session, update_id: int) -> Optional[SystemUpdate]:
        """根据ID获取更新日志"""
        return db.query(SystemUpdate).filter(SystemUpdate.id == update_id).first()

    @staticmethod
    def create_update(db: Session, update_data: SystemUpdateCreate) -> SystemUpdate:
        """创建更新日志"""
        db_update = SystemUpdate(**update_data.model_dump())
        db.add(db_update)
        db.commit()
        db.refresh(db_update)
        return db_update

    @staticmethod
    def update_update(
        db: Session,
        update_id: int,
        update_data: SystemUpdateUpdate
    ) -> Optional[SystemUpdate]:
        """更新更新日志"""
        db_update = db.query(SystemUpdate).filter(SystemUpdate.id == update_id).first()
        if not db_update:
            return None

        update_dict = update_data.model_dump(exclude_unset=True)
        for key, value in update_dict.items():
            setattr(db_update, key, value)

        db.commit()
        db.refresh(db_update)
        return db_update

    @staticmethod
    def delete_update(db: Session, update_id: int) -> bool:
        """删除更新日志"""
        db_update = db.query(SystemUpdate).filter(SystemUpdate.id == update_id).first()
        if not db_update:
            return False

        db.delete(db_update)
        db.commit()
        return True

    @staticmethod
    def get_update_count(db: Session) -> int:
        """获取已发布更新日志数量"""
        return (
            db.query(SystemUpdate)
            .filter(SystemUpdate.is_published == True)
            .count()
        )
