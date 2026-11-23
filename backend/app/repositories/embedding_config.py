"""
向量模型配置数据访问层
"""
from typing import List, Optional
from sqlalchemy.orm import Session
from ..models.embedding_config import EmbeddingConfig
from ..schemas.embedding_config import EmbeddingConfigCreate, EmbeddingConfigUpdate


class EmbeddingConfigRepository:
    @staticmethod
    def get_all(db: Session, skip: int = 0, limit: int = 100, space_id: int = None) -> List[EmbeddingConfig]:
        query = db.query(EmbeddingConfig)
        if space_id is not None:
            query = query.filter(EmbeddingConfig.space_id == space_id)
        return query.offset(skip).limit(limit).all()

    @staticmethod
    def get_by_id(db: Session, config_id: int, space_id: int = None) -> Optional[EmbeddingConfig]:
        query = db.query(EmbeddingConfig).filter(EmbeddingConfig.id == config_id)
        if space_id is not None:
            query = query.filter(EmbeddingConfig.space_id == space_id)
        return query.first()

    @staticmethod
    def get_default(db: Session, space_id: int = None) -> Optional[EmbeddingConfig]:
        query = db.query(EmbeddingConfig).filter(
            EmbeddingConfig.is_default == True,
            EmbeddingConfig.is_active == True
        )
        if space_id is not None:
            query = query.filter(EmbeddingConfig.space_id == space_id)
        return query.first()

    @staticmethod
    def create(db: Session, config: EmbeddingConfigCreate, space_id: int = 1) -> EmbeddingConfig:
        config_data = config.model_dump()
        config_data['space_id'] = space_id

        if config.is_default:
            db.query(EmbeddingConfig).filter(EmbeddingConfig.space_id == space_id).update(
                {EmbeddingConfig.is_default: False}
            )

        db_config = EmbeddingConfig(**config_data)
        db.add(db_config)
        db.commit()
        db.refresh(db_config)
        return db_config

    @staticmethod
    def update(db: Session, config_id: int, config: EmbeddingConfigUpdate, space_id: int = None) -> Optional[EmbeddingConfig]:
        db_config = EmbeddingConfigRepository.get_by_id(db, config_id, space_id)
        if not db_config:
            return None
        update_data = config.model_dump(exclude_unset=True)
        if update_data.get("is_default"):
            db.query(EmbeddingConfig).filter(
                EmbeddingConfig.id != config_id,
                EmbeddingConfig.space_id == db_config.space_id
            ).update({EmbeddingConfig.is_default: False})
        for field, value in update_data.items():
            setattr(db_config, field, value)
        db.commit()
        db.refresh(db_config)
        return db_config

    @staticmethod
    def delete(db: Session, config_id: int, space_id: int = None) -> bool:
        db_config = EmbeddingConfigRepository.get_by_id(db, config_id, space_id)
        if not db_config:
            return False
        db.delete(db_config)
        db.commit()
        return True