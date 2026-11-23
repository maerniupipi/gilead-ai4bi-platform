from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from .... import schemas
from ....core.database import get_db
from ....core.permissions import RequireSystemPermission
from ....repositories.knowledge.knowledge_access.repository import get_knowledge_bases_by_knowledge_access
from ....services.knowledge.knowledge_access.service import (
    create_knowledge_access_service,
    delete_knowledge_access_service,
    get_knowledge_access_service,
    list_knowledge_access_service,
    update_knowledge_access_service,
)

router = APIRouter(
    prefix="/knowledge_access",
    tags=["knowledge_access"]
)


def get_space_id(space_id: Optional[int] = Query(None, description="空间ID")) -> Optional[int]:
    return space_id


# 创建知识接入
@router.post("", response_model=schemas.KnowledgeAccess)
def create_knowledge_access(
    knowledge_access: schemas.KnowledgeAccessCreate,
    db: Session = Depends(get_db),
    space_id: Optional[int] = Depends(get_space_id),
    operator_id: int = Depends(RequireSystemPermission("*")),
):
    return create_knowledge_access_service(db, knowledge_access, space_id)


# 获取知识接入列表
@router.get("", response_model=List[schemas.KnowledgeAccess])
def get_knowledge_access_list(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    space_id: Optional[int] = Depends(get_space_id)
):
    return list_knowledge_access_service(db, skip, limit, space_id)


# 获取单个知识接入
@router.get("/{knowledge_access_id}", response_model=schemas.KnowledgeAccess)
def get_knowledge_access(
    knowledge_access_id: int,
    db: Session = Depends(get_db),
    space_id: Optional[int] = Depends(get_space_id)
):
    return get_knowledge_access_service(db, knowledge_access_id, space_id)


# 检查知识接入是否被知识库引用
@router.get("/{knowledge_access_id}/check_kb_refs")
def check_knowledge_access_kb_refs(
    knowledge_access_id: int,
    db: Session = Depends(get_db),
    space_id: Optional[int] = Depends(get_space_id)
):
    """检查知识接入是否被知识库引用"""
    knowledge_bases = get_knowledge_bases_by_knowledge_access(db, knowledge_access_id, space_id)
    if knowledge_bases:
        return {
            "can_delete": False,
            "message": "该知识接入被以下知识库引用，无法删除",
            "knowledge_bases": [{"id": kb.id, "name": kb.name, "description": kb.description} for kb in knowledge_bases]
        }
    return {
        "can_delete": True,
        "message": "该知识接入未被任何知识库引用",
        "knowledge_bases": []
    }


# 更新知识接入
@router.put("/{knowledge_access_id}", response_model=schemas.KnowledgeAccess)
def update_knowledge_access(
    knowledge_access_id: int,
    knowledge_access: schemas.KnowledgeAccessUpdate,
    db: Session = Depends(get_db),
    space_id: Optional[int] = Depends(get_space_id),
    operator_id: int = Depends(RequireSystemPermission("*")),
):
    return update_knowledge_access_service(db, knowledge_access_id, knowledge_access, space_id)


# 删除知识接入（软删除）
@router.delete("/{knowledge_access_id}")
def delete_knowledge_access(
    knowledge_access_id: int,
    db: Session = Depends(get_db),
    space_id: Optional[int] = Depends(get_space_id),
    operator_id: int = Depends(RequireSystemPermission("*")),
):
    return delete_knowledge_access_service(db, knowledge_access_id, space_id)
