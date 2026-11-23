"""
向量库配置数据访问层
"""
from typing import List, Optional
from sqlalchemy.orm import Session
from ..models.vector_store import VectorStoreConfig
from ..schemas.vector_store import VectorStoreCreate, VectorStoreUpdate


class VectorStoreRepository:
    @staticmethod
    def get_all(db: Session, skip: int = 0, limit: int = 100, space_id: int = None) -> List[VectorStoreConfig]:
        query = db.query(VectorStoreConfig)
        if space_id is not None:
            query = query.filter(VectorStoreConfig.space_id == space_id)
        return query.offset(skip).limit(limit).all()

    @staticmethod
    def get_by_id(db: Session, store_id: int, space_id: int = None) -> Optional[VectorStoreConfig]:
        query = db.query(VectorStoreConfig).filter(VectorStoreConfig.id == store_id)
        if space_id is not None:
            query = query.filter(VectorStoreConfig.space_id == space_id)
        return query.first()

    @staticmethod
    def get_active(db: Session, space_id: int = None) -> Optional[VectorStoreConfig]:
        query = db.query(VectorStoreConfig).filter(
            VectorStoreConfig.is_active == True
        )
        if space_id is not None:
            query = query.filter(VectorStoreConfig.space_id == space_id)
        return query.first()

    @staticmethod
    def create(db: Session, store: VectorStoreCreate, space_id: int = 1) -> VectorStoreConfig:
        store_data = store.model_dump()
        store_data['space_id'] = space_id

        # 同一空间仅允许一个启用：新建配置时如果 is_active 为 True，停用同空间其他配置
        if store_data.get("is_active", True):
            db.query(VectorStoreConfig).filter(
                VectorStoreConfig.space_id == space_id,
                VectorStoreConfig.is_active == True
            ).update({VectorStoreConfig.is_active: False})

        db_store = VectorStoreConfig(**store_data)
        db.add(db_store)
        db.commit()
        db.refresh(db_store)
        return db_store

    @staticmethod
    def update(db: Session, store_id: int, store: VectorStoreUpdate, space_id: int = None) -> Optional[VectorStoreConfig]:
        db_store = VectorStoreRepository.get_by_id(db, store_id, space_id)
        if not db_store:
            return None
        update_data = store.model_dump(exclude_unset=True)
        # 同一空间仅允许一个启用：更新时如果设置 is_active=True，停用同空间其他已启用配置
        if update_data.get("is_active"):
            db.query(VectorStoreConfig).filter(
                VectorStoreConfig.id != store_id,
                VectorStoreConfig.space_id == db_store.space_id,
                VectorStoreConfig.is_active == True
            ).update({VectorStoreConfig.is_active: False})
        for field, value in update_data.items():
            setattr(db_store, field, value)
        db.commit()
        db.refresh(db_store)
        return db_store

    @staticmethod
    def delete(db: Session, store_id: int, space_id: int = None) -> bool:
        db_store = VectorStoreRepository.get_by_id(db, store_id, space_id)
        if not db_store:
            return False
        db.delete(db_store)
        db.commit()
        return True
