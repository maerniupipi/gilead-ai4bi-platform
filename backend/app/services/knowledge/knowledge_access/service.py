from fastapi import HTTPException
from sqlalchemy.orm import Session

from ....repositories.knowledge.knowledge_access.repository import (
    apply_knowledge_access_update,
    create_knowledge_access,
    get_knowledge_access_active_by_id,
    list_knowledge_accesses_active,
    soft_delete_knowledge_access,
)


def create_knowledge_access_service(db: Session, knowledge_access, space_id: int = None):
    data_dict = knowledge_access.dict()
    if space_id is not None:
        data_dict['space_id'] = space_id
    db_knowledge_access = create_knowledge_access(db, data_dict)
    db.commit()
    db.refresh(db_knowledge_access)
    return db_knowledge_access


def list_knowledge_access_service(db: Session, skip: int, limit: int, space_id: int = None):
    knowledge_accesses = list_knowledge_accesses_active(db, skip, limit, space_id)
    # Add data_source_name to each knowledge access
    for ka in knowledge_accesses:
        ka.data_source_name = ka.data_source.name if ka.data_source else None
    return knowledge_accesses


def get_knowledge_access_service(db: Session, knowledge_access_id: int, space_id: int = None):
    knowledge_access = get_knowledge_access_active_by_id(db, knowledge_access_id, space_id)
    if knowledge_access is None:
        raise HTTPException(status_code=404, detail="Knowledge access not found")
    return knowledge_access


def update_knowledge_access_service(db: Session, knowledge_access_id: int, knowledge_access_update, space_id: int = None):
    db_knowledge_access = get_knowledge_access_active_by_id(db, knowledge_access_id, space_id)
    if db_knowledge_access is None:
        raise HTTPException(status_code=404, detail="Knowledge access not found")

    update_data = knowledge_access_update.dict(exclude_unset=True)
    if space_id is not None and 'space_id' not in update_data:
        update_data['space_id'] = space_id
    apply_knowledge_access_update(db, db_knowledge_access, update_data)
    db.commit()
    db.refresh(db_knowledge_access)
    return db_knowledge_access


def delete_knowledge_access_service(db: Session, knowledge_access_id: int, space_id: int = None):
    db_knowledge_access = get_knowledge_access_active_by_id(db, knowledge_access_id, space_id)
    if db_knowledge_access is None:
        raise HTTPException(status_code=404, detail="Knowledge access not found")

    soft_delete_knowledge_access(db, db_knowledge_access)
    db.commit()
    return {"message": "Knowledge access deleted successfully"}
