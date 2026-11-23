from sqlalchemy.orm import Session

from .... import models


def get_data_source_active_by_name(db: Session, name: str, space_id: int = None):
    query = db.query(models.DataSource).filter(
        models.DataSource.name == name,
        models.DataSource.is_deleted == False
    )
    if space_id is not None:
        query = query.filter(models.DataSource.space_id == space_id)
    return query.first()


def create_data_source(db: Session, data_source_data: dict):
    db_data_source = models.DataSource(**data_source_data)
    db.add(db_data_source)
    return db_data_source


def list_data_sources_active(db: Session, skip: int, limit: int, space_id: int = None):
    query = db.query(models.DataSource).filter(models.DataSource.is_deleted == False)
    if space_id is not None:
        query = query.filter(models.DataSource.space_id == space_id)
    return query.offset(skip).limit(limit).all()


def get_data_source_active_by_id(db: Session, data_source_id: int, space_id: int = None):
    query = db.query(models.DataSource).filter(
        models.DataSource.id == data_source_id,
        models.DataSource.is_deleted == False,
    )
    if space_id is not None:
        query = query.filter(models.DataSource.space_id == space_id)
    return query.first()


def apply_data_source_update(db: Session, db_data_source, update_data: dict):
    for key, value in update_data.items():
        setattr(db_data_source, key, value)
    return db_data_source


def soft_delete_data_source(db: Session, db_data_source):
    db_data_source.is_deleted = True
    return db_data_source


def get_knowledge_accesses_by_data_source(db: Session, data_source_id: int, space_id: int = None):
    """获取引用指定数据源的所有知识接入"""
    query = db.query(models.KnowledgeAccess).filter(
        models.KnowledgeAccess.data_source_id == data_source_id,
        models.KnowledgeAccess.is_deleted == False
    )
    if space_id is not None:
        query = query.filter(models.KnowledgeAccess.space_id == space_id)
    return query.all()

