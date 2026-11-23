from fastapi import HTTPException
from sqlalchemy.orm import Session

from ....repositories.knowledge.knowledge_term.repository import (
    apply_knowledge_term_update,
    bulk_create_knowledge_terms,
    count_knowledge_terms_by_access_active,
    create_knowledge_term,
    get_knowledge_access_active_by_id,
    get_knowledge_term_active_by_id,
    list_all_knowledge_terms_by_access_active,
    list_knowledge_terms_by_access_active,
    soft_delete_all_knowledge_terms_by_access,
    soft_delete_knowledge_term,
)
from ....repositories.knowledge.knowledge_base.repository import (
    get_knowledge_bases_by_knowledge_term_id,
    delete_kb_knowledge_term_by_term_id,
)


def get_knowledge_terms_service(db: Session, knowledge_access_id: int, skip: int, limit: int, space_id: int = None):
    from .... import schemas
    knowledge_access = get_knowledge_access_active_by_id(db, knowledge_access_id, space_id)
    if knowledge_access is None:
        raise HTTPException(status_code=404, detail="Knowledge access not found")

    items = list_knowledge_terms_by_access_active(db, knowledge_access_id, skip, limit, space_id)
    total = count_knowledge_terms_by_access_active(db, knowledge_access_id, space_id)
    return schemas.KnowledgeTermPage(total=total, items=items)


def list_all_knowledge_terms_service(db: Session, knowledge_access_id: int, space_id: int = None):
    knowledge_access = get_knowledge_access_active_by_id(db, knowledge_access_id, space_id)
    if knowledge_access is None:
        raise HTTPException(status_code=404, detail="Knowledge access not found")

    return list_all_knowledge_terms_by_access_active(db, knowledge_access_id, space_id)


def create_knowledge_term_service(db: Session, knowledge_access_id: int, knowledge_term, space_id: int = None):
    knowledge_access = get_knowledge_access_active_by_id(db, knowledge_access_id, space_id)
    if knowledge_access is None:
        raise HTTPException(status_code=404, detail="Knowledge access not found")

    db_knowledge_term = create_knowledge_term(db, knowledge_access_id, knowledge_term.dict(), space_id)
    db.commit()
    db.refresh(db_knowledge_term)
    return db_knowledge_term


def update_knowledge_term_service(db: Session, knowledge_term_id: int, knowledge_term_update, space_id: int = None):
    db_knowledge_term = get_knowledge_term_active_by_id(db, knowledge_term_id, space_id)
    if db_knowledge_term is None:
        raise HTTPException(status_code=404, detail="Knowledge term not found")

    update_data = knowledge_term_update.dict(exclude_unset=True)

    # 检查名称或值是否变更
    name_or_value_changed = (
        'term_name' in update_data and update_data['term_name'] != db_knowledge_term.term_name
    ) or (
        'term_value' in update_data and update_data['term_value'] != db_knowledge_term.term_value
    )

    apply_knowledge_term_update(db, db_knowledge_term, update_data)

    # 如果名称或值变更，标记引用了该词条的知识库为脏数据
    if name_or_value_changed:
        from ....models.knowledge_base import KnowledgeBase
        kb_refs = get_knowledge_bases_by_knowledge_term_id(db, knowledge_term_id)
        for kb in kb_refs:
            kb.knowledge_term_dirty = True

    db.commit()
    db.refresh(db_knowledge_term)
    return db_knowledge_term


def delete_knowledge_term_service(db: Session, knowledge_term_id: int, space_id: int = None):
    db_knowledge_term = get_knowledge_term_active_by_id(db, knowledge_term_id, space_id)
    if db_knowledge_term is None:
        raise HTTPException(status_code=404, detail="Knowledge term not found")

    # 标记引用了该词条的知识库为脏数据
    from ....models.knowledge_base import KnowledgeBase
    kb_refs = get_knowledge_bases_by_knowledge_term_id(db, knowledge_term_id)
    for kb in kb_refs:
        kb.knowledge_term_dirty = True

    # 删除知识库中对该词条的引用
    delete_kb_knowledge_term_by_term_id(db, knowledge_term_id)

    soft_delete_knowledge_term(db, db_knowledge_term)
    db.commit()
    return {"message": "Knowledge term deleted successfully"}


def export_knowledge_terms_service(db: Session, knowledge_access_id: int, space_id: int = None):
    knowledge_access = get_knowledge_access_active_by_id(db, knowledge_access_id, space_id)
    if knowledge_access is None:
        raise HTTPException(status_code=404, detail="Knowledge access not found")
    return list_all_knowledge_terms_by_access_active(db, knowledge_access_id, space_id)


def import_knowledge_terms_service(db: Session, knowledge_access_id: int, body, space_id: int = None):
    from .... import schemas
    knowledge_access = get_knowledge_access_active_by_id(db, knowledge_access_id, space_id)
    if knowledge_access is None:
        raise HTTPException(status_code=404, detail="Knowledge access not found")
    if not body.rows:
        raise HTTPException(status_code=400, detail="导入数据为空")

    rows_data = [item.model_dump() for item in body.rows]

    if body.mode == schemas.KnowledgeTermImportMode.replace_all:
        # 标记关联 KB 为脏
        from ....models.knowledge_base import KnowledgeBase
        from ....repositories.knowledge.knowledge_base.repository import (
            delete_kb_knowledge_term_by_term_id,
        )
        old_terms = list_all_knowledge_terms_by_access_active(db, knowledge_access_id, space_id)
        for t in old_terms:
            kb_refs = get_knowledge_bases_by_knowledge_term_id(db, t.id)
            for kb in kb_refs:
                kb.knowledge_term_dirty = True
            delete_kb_knowledge_term_by_term_id(db, t.id)
        soft_delete_all_knowledge_terms_by_access(db, knowledge_access_id, space_id)
        bulk_create_knowledge_terms(db, knowledge_access_id, rows_data, space_id)
        db.commit()
        return schemas.KnowledgeTermImportResult(
            inserted=len(rows_data),
            message=f"已全量覆盖，共写入 {len(rows_data)} 条",
        )

    # append
    # 标记关联 KB 为脏（新增词条也需要标记）
    from ....models.knowledge_base import KnowledgeBase
    existing = list_all_knowledge_terms_by_access_active(db, knowledge_access_id, space_id)
    for t in existing:
        kb_refs = get_knowledge_bases_by_knowledge_term_id(db, t.id)
        for kb in kb_refs:
            kb.knowledge_term_dirty = True

    bulk_create_knowledge_terms(db, knowledge_access_id, rows_data, space_id)
    db.commit()
    return schemas.KnowledgeTermImportResult(
        inserted=len(rows_data),
        message=f"已新增 {len(rows_data)} 条",
    )
