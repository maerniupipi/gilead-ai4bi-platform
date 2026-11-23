"""
模型供应商数据访问层
"""
from typing import List, Optional
from sqlalchemy.orm import Session
from ...models.model_provider import ModelProvider
from ...schemas.model_provider import ModelProviderCreate, ModelProviderUpdate


class ModelProviderRepository:
    """模型供应商Repository"""

    @staticmethod
    def get_all(db: Session, skip: int = 0, limit: int = 100) -> List[ModelProvider]:
        """获取所有供应商"""
        return db.query(ModelProvider).offset(skip).limit(limit).all()

    @staticmethod
    def get_by_id(db: Session, provider_id: int) -> Optional[ModelProvider]:
        """根据ID获取供应商"""
        return db.query(ModelProvider).filter(ModelProvider.id == provider_id).first()

    @staticmethod
    def create(db: Session, provider: ModelProviderCreate) -> ModelProvider:
        """创建供应商"""
        db_provider = ModelProvider(**provider.model_dump())
        db.add(db_provider)
        db.commit()
        db.refresh(db_provider)
        return db_provider

    @staticmethod
    def update(db: Session, provider_id: int, provider: ModelProviderUpdate) -> Optional[ModelProvider]:
        """更新供应商"""
        db_provider = ModelProviderRepository.get_by_id(db, provider_id)
        if not db_provider:
            return None

        update_data = provider.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_provider, field, value)

        db.commit()
        db.refresh(db_provider)
        return db_provider

    @staticmethod
    def delete(db: Session, provider_id: int) -> bool:
        """删除供应商"""
        db_provider = ModelProviderRepository.get_by_id(db, provider_id)
        if not db_provider:
            return False

        db.delete(db_provider)
        db.commit()
        return True
