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


def list_sample_libraries_by_access_active(db: Session, knowledge_access_id: int, skip: int, limit: int, space_id: int = None):
    query = db.query(models.SampleLibrary).filter(
        models.SampleLibrary.knowledge_access_id == knowledge_access_id,
        models.SampleLibrary.is_deleted == False,
    )
    if space_id is not None:
        query = query.filter(models.SampleLibrary.space_id == space_id)
    return query.offset(skip).limit(limit).all()


def count_sample_libraries_by_access_active(db: Session, knowledge_access_id: int, space_id: int = None):
    query = db.query(models.SampleLibrary).filter(
        models.SampleLibrary.knowledge_access_id == knowledge_access_id,
        models.SampleLibrary.is_deleted == False,
    )
    if space_id is not None:
        query = query.filter(models.SampleLibrary.space_id == space_id)
    return query.count()


def get_sample_library_active_by_id(db: Session, sample_library_id: int, space_id: int = None):
    query = db.query(models.SampleLibrary).filter(
        models.SampleLibrary.id == sample_library_id,
        models.SampleLibrary.is_deleted == False,
    )
    if space_id is not None:
        query = query.filter(models.SampleLibrary.space_id == space_id)
    return query.first()


def create_sample_library(db: Session, knowledge_access_id: int, sample_library_data: dict, space_id: int = None):
    if space_id is not None:
        sample_library_data['space_id'] = space_id
    db_sample_library = models.SampleLibrary(**sample_library_data, knowledge_access_id=knowledge_access_id)
    db.add(db_sample_library)
    return db_sample_library


def apply_sample_library_update(db: Session, db_sample_library, update_data: dict):
    for key, value in update_data.items():
        setattr(db_sample_library, key, value)
    return db_sample_library


def soft_delete_sample_library(db: Session, db_sample_library):
    db_sample_library.is_deleted = True
    return db_sample_library


def list_all_sample_libraries_by_access_active(db: Session, knowledge_access_id: int, space_id: int = None):
    query = db.query(models.SampleLibrary).filter(
        models.SampleLibrary.knowledge_access_id == knowledge_access_id,
        models.SampleLibrary.is_deleted == False,
    )
    if space_id is not None:
        query = query.filter(models.SampleLibrary.space_id == space_id)
    return query.all()


def bulk_create_sample_libraries(db: Session, knowledge_access_id: int, rows_data: list, space_id: int = None):
    created = []
    for row in rows_data:
        data = dict(row)
        if space_id is not None:
            data['space_id'] = space_id
        obj = models.SampleLibrary(**data, knowledge_access_id=knowledge_access_id)
        db.add(obj)
        created.append(obj)
    db.flush()
    return created


def soft_delete_all_sample_libraries_by_access(db: Session, knowledge_access_id: int, space_id: int = None):
    query = db.query(models.SampleLibrary).filter(
        models.SampleLibrary.knowledge_access_id == knowledge_access_id,
        models.SampleLibrary.is_deleted == False,
    )
    if space_id is not None:
        query = query.filter(models.SampleLibrary.space_id == space_id)
    query.update({models.SampleLibrary.is_deleted: True})
    db.flush()

