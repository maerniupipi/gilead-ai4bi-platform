from sqlalchemy.orm import Session

from .... import models


def get_knowledge_access_active_by_id(db: Session, knowledge_access_id: int, space_id: int = None):
    query = db.query(models.KnowledgeAccess).filter(
        models.KnowledgeAccess.id == knowledge_access_id,
        models.KnowledgeAccess.is_deleted == False,
    )
    if space_id is not None:
        query = query.filter(models.KnowledgeAccess.space_id == space_id)
    return query.first()


def list_knowledge_terms_by_access_active(db: Session, knowledge_access_id: int, skip: int, limit: int, space_id: int = None):
    query = db.query(models.KnowledgeTerm).filter(
        models.KnowledgeTerm.knowledge_access_id == knowledge_access_id,
        models.KnowledgeTerm.is_deleted == False,
    )
    if space_id is not None:
        query = query.filter(models.KnowledgeTerm.space_id == space_id)
    return query.offset(skip).limit(limit).all()


def count_knowledge_terms_by_access_active(db: Session, knowledge_access_id: int, space_id: int = None):
    query = db.query(models.KnowledgeTerm).filter(
        models.KnowledgeTerm.knowledge_access_id == knowledge_access_id,
        models.KnowledgeTerm.is_deleted == False,
    )
    if space_id is not None:
        query = query.filter(models.KnowledgeTerm.space_id == space_id)
    return query.count()


def get_knowledge_term_active_by_id(db: Session, knowledge_term_id: int, space_id: int = None):
    query = db.query(models.KnowledgeTerm).filter(
        models.KnowledgeTerm.id == knowledge_term_id,
        models.KnowledgeTerm.is_deleted == False,
    )
    if space_id is not None:
        query = query.filter(models.KnowledgeTerm.space_id == space_id)
    return query.first()


def create_knowledge_term(db: Session, knowledge_access_id: int, knowledge_term_data: dict, space_id: int = None):
    if space_id is not None:
        knowledge_term_data['space_id'] = space_id
    db_knowledge_term = models.KnowledgeTerm(**knowledge_term_data, knowledge_access_id=knowledge_access_id)
    db.add(db_knowledge_term)
    return db_knowledge_term


def apply_knowledge_term_update(db: Session, db_knowledge_term, update_data: dict):
    for key, value in update_data.items():
        setattr(db_knowledge_term, key, value)
    return db_knowledge_term


def soft_delete_knowledge_term(db: Session, db_knowledge_term):
    db_knowledge_term.is_deleted = True
    return db_knowledge_term


def list_all_knowledge_terms_by_access_active(db: Session, knowledge_access_id: int, space_id: int = None):
    query = db.query(models.KnowledgeTerm).filter(
        models.KnowledgeTerm.knowledge_access_id == knowledge_access_id,
        models.KnowledgeTerm.is_deleted == False,
    )
    if space_id is not None:
        query = query.filter(models.KnowledgeTerm.space_id == space_id)
    return query.all()


def bulk_create_knowledge_terms(db: Session, knowledge_access_id: int, rows_data: list, space_id: int = None):
    created = []
    for row in rows_data:
        data = dict(row)
        if space_id is not None:
            data['space_id'] = space_id
        obj = models.KnowledgeTerm(**data, knowledge_access_id=knowledge_access_id)
        db.add(obj)
        created.append(obj)
    db.flush()
    return created


def soft_delete_all_knowledge_terms_by_access(db: Session, knowledge_access_id: int, space_id: int = None):
    query = db.query(models.KnowledgeTerm).filter(
        models.KnowledgeTerm.knowledge_access_id == knowledge_access_id,
        models.KnowledgeTerm.is_deleted == False,
    )
    if space_id is not None:
        query = query.filter(models.KnowledgeTerm.space_id == space_id)
    query.update({models.KnowledgeTerm.is_deleted: True})
    db.flush()

