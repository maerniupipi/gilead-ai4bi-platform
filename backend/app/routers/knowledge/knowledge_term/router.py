from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from .... import schemas
from ....core.database import get_db
from ....core.permissions import RequireSystemPermission
from ....services.knowledge.knowledge_term.service import (
    create_knowledge_term_service,
    delete_knowledge_term_service,
    export_knowledge_terms_service,
    get_knowledge_terms_service,
    import_knowledge_terms_service,
    list_all_knowledge_terms_service,
    update_knowledge_term_service,
)

router = APIRouter(
    prefix="/knowledge_term",
    tags=["knowledge_term"]
)


def get_space_id(space_id: Optional[int] = Query(None, description="空间ID")) -> Optional[int]:
    return space_id


# 获取知识接入的词条列表
@router.get("/knowledge_access/{knowledge_access_id}", response_model=schemas.KnowledgeTermPage)
def get_knowledge_terms(
    knowledge_access_id: int,
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db),
    space_id: Optional[int] = Depends(get_space_id)
):
    return get_knowledge_terms_service(db, knowledge_access_id, skip, limit, space_id)


# 获取知识接入的全部词条（无分页，用于知识库选择词条）
@router.get("/knowledge_access/{knowledge_access_id}/all", response_model=List[schemas.KnowledgeTerm])
def list_all_knowledge_terms(
    knowledge_access_id: int,
    db: Session = Depends(get_db),
    space_id: Optional[int] = Depends(get_space_id)
):
    return list_all_knowledge_terms_service(db, knowledge_access_id, space_id)


# 创建词条
@router.post("", response_model=schemas.KnowledgeTerm)
def create_knowledge_term(
    knowledge_term: schemas.KnowledgeTermCreate,
    knowledge_access_id: int,
    db: Session = Depends(get_db),
    space_id: Optional[int] = Depends(get_space_id),
    operator_id: int = Depends(RequireSystemPermission("*")),
):
    return create_knowledge_term_service(db, knowledge_access_id, knowledge_term, space_id)


# 更新词条
@router.put("/{knowledge_term_id}", response_model=schemas.KnowledgeTerm)
def update_knowledge_term(
    knowledge_term_id: int,
    knowledge_term: schemas.KnowledgeTermUpdate,
    db: Session = Depends(get_db),
    space_id: Optional[int] = Depends(get_space_id),
    operator_id: int = Depends(RequireSystemPermission("*")),
):
    return update_knowledge_term_service(db, knowledge_term_id, knowledge_term, space_id)


# 删除词条（软删除）
@router.delete("/{knowledge_term_id}")
def delete_knowledge_term(
    knowledge_term_id: int,
    db: Session = Depends(get_db),
    space_id: Optional[int] = Depends(get_space_id),
    operator_id: int = Depends(RequireSystemPermission("*")),
):
    return delete_knowledge_term_service(db, knowledge_term_id, space_id)


# 导出全部词条
@router.get("/knowledge_access/{knowledge_access_id}/export", response_model=List[schemas.KnowledgeTerm])
def export_knowledge_terms(
    knowledge_access_id: int,
    db: Session = Depends(get_db),
    space_id: Optional[int] = Depends(get_space_id),
):
    return export_knowledge_terms_service(db, knowledge_access_id, space_id)


# 导入词条
@router.post("/knowledge_access/{knowledge_access_id}/import", response_model=schemas.KnowledgeTermImportResult)
def import_knowledge_terms(
    knowledge_access_id: int,
    body: schemas.KnowledgeTermImportRequest,
    db: Session = Depends(get_db),
    space_id: Optional[int] = Depends(get_space_id),
    operator_id: int = Depends(RequireSystemPermission("*")),
):
    return import_knowledge_terms_service(db, knowledge_access_id, body, space_id)
