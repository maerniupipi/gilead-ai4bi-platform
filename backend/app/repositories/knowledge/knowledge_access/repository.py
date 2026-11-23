from sqlalchemy.orm import Session, joinedload

from .... import models


def create_knowledge_access(db: Session, knowledge_access_data: dict):
    db_knowledge_access = models.KnowledgeAccess(**knowledge_access_data)
    db.add(db_knowledge_access)
    return db_knowledge_access


def list_knowledge_accesses_active(db: Session, skip: int, limit: int, space_id: int = None):
    query = db.query(models.KnowledgeAccess).options(
        joinedload(models.KnowledgeAccess.data_source)
    ).filter(models.KnowledgeAccess.is_deleted == False)
    if space_id is not None:
        query = query.filter(models.KnowledgeAccess.space_id == space_id)
    return query.offset(skip).limit(limit).all()


def get_knowledge_access_active_by_id(db: Session, knowledge_access_id: int, space_id: int = None):
    query = db.query(models.KnowledgeAccess).filter(
        models.KnowledgeAccess.id == knowledge_access_id,
        models.KnowledgeAccess.is_deleted == False,
    )
    if space_id is not None:
        query = query.filter(models.KnowledgeAccess.space_id == space_id)
    return query.first()


def apply_knowledge_access_update(db: Session, db_knowledge_access, update_data: dict):
    for key, value in update_data.items():
        setattr(db_knowledge_access, key, value)
    return db_knowledge_access


def soft_delete_knowledge_access(db: Session, db_knowledge_access):
    db_knowledge_access.is_deleted = True
    return db_knowledge_access


def get_knowledge_bases_by_knowledge_access(db: Session, knowledge_access_id: int, space_id: int = None):
    """获取引用指定知识接入的所有知识库"""
    query = db.query(models.KnowledgeBase).filter(
        models.KnowledgeBase.knowledge_access_id == knowledge_access_id,
        models.KnowledgeBase.is_deleted == False
    )
    if space_id is not None:
        query = query.filter(models.KnowledgeBase.space_id == space_id)
    return query.all()

