"""
ES配置数据访问层
"""
from typing import List, Optional
from sqlalchemy.orm import Session
from ..models.es_config import EsConfig
from ..schemas.es_config import EsConfigCreate, EsConfigUpdate


class EsConfigRepository:
    @staticmethod
    def get_all(db: Session, skip: int = 0, limit: int = 100, space_id: int = None) -> List[EsConfig]:
        query = db.query(EsConfig)
        if space_id is not None:
            query = query.filter(EsConfig.space_id == space_id)
        return query.offset(skip).limit(limit).all()

    @staticmethod
    def get_by_id(db: Session, config_id: int, space_id: int = None) -> Optional[EsConfig]:
        query = db.query(EsConfig).filter(EsConfig.id == config_id)
        if space_id is not None:
            query = query.filter(EsConfig.space_id == space_id)
        return query.first()

    @staticmethod
    def get_default(db: Session, space_id: int = None) -> Optional[EsConfig]:
        query = db.query(EsConfig).filter(
            EsConfig.is_default == True,
            EsConfig.is_active == True
        )
        if space_id is not None:
            query = query.filter(EsConfig.space_id == space_id)
        return query.first()

    @staticmethod
    def create(db: Session, config: EsConfigCreate, space_id: int = 1) -> EsConfig:
        config_data = config.model_dump()
        config_data['space_id'] = space_id

        if config.is_default:
            db.query(EsConfig).filter(EsConfig.space_id == space_id).update({EsConfig.is_default: False})

        db_config = EsConfig(**config_data)
        db.add(db_config)
        db.commit()
        db.refresh(db_config)
        return db_config

    @staticmethod
    def update(db: Session, config_id: int, config: EsConfigUpdate, space_id: int = None) -> Optional[EsConfig]:
        db_config = EsConfigRepository.get_by_id(db, config_id, space_id)
        if not db_config:
            return None
        update_data = config.model_dump(exclude_unset=True)
        if update_data.get("is_default"):
            db.query(EsConfig).filter(
                EsConfig.id != config_id,
                EsConfig.space_id == db_config.space_id
            ).update({EsConfig.is_default: False})
        for field, value in update_data.items():
            setattr(db_config, field, value)
        db.commit()
        db.refresh(db_config)
        return db_config

    @staticmethod
    def delete(db: Session, config_id: int, space_id: int = None) -> bool:
        db_config = EsConfigRepository.get_by_id(db, config_id, space_id)
        if not db_config:
            return False
        db.delete(db_config)
        db.commit()
        return True