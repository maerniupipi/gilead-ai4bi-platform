from fastapi import HTTPException
from sqlalchemy.orm import Session

from ....repositories.knowledge.sample_library.repository import (
    apply_sample_library_update,
    bulk_create_sample_libraries,
    count_sample_libraries_by_access_active,
    create_sample_library,
    get_knowledge_access_active_by_id,
    get_sample_library_active_by_id,
    list_all_sample_libraries_by_access_active,
    list_sample_libraries_by_access_active,
    soft_delete_all_sample_libraries_by_access,
    soft_delete_sample_library,
)
from ....repositories.knowledge.knowledge_base.repository import (
    get_knowledge_bases_by_sample_id,
    delete_kb_sample_library_by_sample_id,
)


def get_sample_libraries_service(db: Session, knowledge_access_id: int, skip: int, limit: int, space_id: int = None):
    from .... import schemas
    knowledge_access = get_knowledge_access_active_by_id(db, knowledge_access_id, space_id)
    if knowledge_access is None:
        raise HTTPException(status_code=404, detail="Knowledge access not found")
    items = list_sample_libraries_by_access_active(db, knowledge_access_id, skip, limit, space_id)
    total = count_sample_libraries_by_access_active(db, knowledge_access_id, space_id)
    return schemas.SampleLibraryPage(total=total, items=items)


def create_sample_library_service(db: Session, knowledge_access_id: int, sample_library, space_id: int = None):
    knowledge_access = get_knowledge_access_active_by_id(db, knowledge_access_id, space_id)
    if knowledge_access is None:
        raise HTTPException(status_code=404, detail="Knowledge access not found")

    db_sample_library = create_sample_library(db, knowledge_access_id, sample_library.dict(), space_id)
    db.commit()
    db.refresh(db_sample_library)
    return db_sample_library


def update_sample_library_service(db: Session, sample_library_id: int, sample_library_update, space_id: int = None):
    db_sample_library = get_sample_library_active_by_id(db, sample_library_id, space_id)
    if db_sample_library is None:
        raise HTTPException(status_code=404, detail="Sample library not found")

    update_data = sample_library_update.dict(exclude_unset=True)

    # 检查名称或内容是否变更
    name_or_content_changed = (
        'sample_name' in update_data and update_data['sample_name'] != db_sample_library.sample_name
    ) or (
        'sql_content' in update_data and update_data['sql_content'] != db_sample_library.sql_content
    )

    apply_sample_library_update(db, db_sample_library, update_data)

    # 如果名称或内容变更，标记引用了该样例的知识库为脏数据
    if name_or_content_changed:
        from ....models.knowledge_base import KnowledgeBase
        kb_refs = get_knowledge_bases_by_sample_id(db, sample_library_id)
        for kb in kb_refs:
            kb.sample_library_dirty = True

    db.commit()
    db.refresh(db_sample_library)
    return db_sample_library


def delete_sample_library_service(db: Session, sample_library_id: int, space_id: int = None):
    db_sample_library = get_sample_library_active_by_id(db, sample_library_id, space_id)
    if db_sample_library is None:
        raise HTTPException(status_code=404, detail="Sample library not found")

    # 标记引用了该样例的知识库为脏数据
    from ....models.knowledge_base import KnowledgeBase
    kb_refs = get_knowledge_bases_by_sample_id(db, sample_library_id)
    for kb in kb_refs:
        kb.sample_library_dirty = True

    # 删除知识库中对该样例的引用
    delete_kb_sample_library_by_sample_id(db, sample_library_id)

    soft_delete_sample_library(db, db_sample_library)
    db.commit()
    return {"message": "Sample library deleted successfully"}


def export_sample_libraries_service(db: Session, knowledge_access_id: int, space_id: int = None):
    knowledge_access = get_knowledge_access_active_by_id(db, knowledge_access_id, space_id)
    if knowledge_access is None:
        raise HTTPException(status_code=404, detail="Knowledge access not found")
    return list_all_sample_libraries_by_access_active(db, knowledge_access_id, space_id)


def import_sample_libraries_service(db: Session, knowledge_access_id: int, body, space_id: int = None):
    from .... import schemas
    knowledge_access = get_knowledge_access_active_by_id(db, knowledge_access_id, space_id)
    if knowledge_access is None:
        raise HTTPException(status_code=404, detail="Knowledge access not found")
    if not body.rows:
        raise HTTPException(status_code=400, detail="导入数据为空")

    rows_data = [item.model_dump() for item in body.rows]

    if body.mode == schemas.SampleLibraryImportMode.replace_all:
        # 标记关联 KB 为脏
        from ....models.knowledge_base import KnowledgeBase
        from ....repositories.knowledge.knowledge_base.repository import (
            delete_kb_sample_library_by_sample_id,
        )
        old_samples = list_all_sample_libraries_by_access_active(db, knowledge_access_id, space_id)
        for s in old_samples:
            kb_refs = get_knowledge_bases_by_sample_id(db, s.id)
            for kb in kb_refs:
                kb.sample_library_dirty = True
            delete_kb_sample_library_by_sample_id(db, s.id)
        soft_delete_all_sample_libraries_by_access(db, knowledge_access_id, space_id)
        bulk_create_sample_libraries(db, knowledge_access_id, rows_data, space_id)
        db.commit()
        return schemas.SampleLibraryImportResult(
            inserted=len(rows_data),
            message=f"已全量覆盖，共写入 {len(rows_data)} 条",
        )

    # append
    # 标记关联 KB 为脏（新增样例也需要标记）
    from ....models.knowledge_base import KnowledgeBase
    existing = list_all_sample_libraries_by_access_active(db, knowledge_access_id, space_id)
    for s in existing:
        kb_refs = get_knowledge_bases_by_sample_id(db, s.id)
        for kb in kb_refs:
            kb.sample_library_dirty = True

    bulk_create_sample_libraries(db, knowledge_access_id, rows_data, space_id)
    db.commit()
    return schemas.SampleLibraryImportResult(
        inserted=len(rows_data),
        message=f"已新增 {len(rows_data)} 条",
    )
