from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from .... import schemas
from ....core.database import get_db
from ....core.permissions import RequireSystemPermission
from ....schemas.data_source import DataSourceQueryRequest
from ....services.knowledge.data_source.query import execute_query, query_catalog
from ....repositories.knowledge.data_source.repository import get_knowledge_accesses_by_data_source
from ....services.knowledge.data_source.service import (
    create_data_source_service,
    delete_data_source_service,
    get_data_source_service,
    list_data_source_service,
    reveal_password_service,
    test_data_source_connection,
    update_data_source_service,
)

router = APIRouter(
    prefix="/data_source",
    tags=["data_source"]
)


@router.get("/{data_source_id}/query/catalog")
def data_query_catalog(data_source_id: int, database: Optional[str] = None,
                       space_id: Optional[int] = None, db: Session = Depends(get_db),
                       operator_id: int = Depends(RequireSystemPermission("*"))):
    return query_catalog(db, data_source_id, database=database, space_id=space_id)


@router.post("/{data_source_id}/query")
def data_query(data_source_id: int, body: DataSourceQueryRequest,
               space_id: Optional[int] = None, db: Session = Depends(get_db),
               operator_id: int = Depends(RequireSystemPermission("*"))):
    return execute_query(db, data_source_id, body.sql, database=body.database,
                         schema=body.schema_name, space_id=space_id)


def get_space_id(space_id: Optional[int] = Query(None, description="空间ID")) -> Optional[int]:
    return space_id


# 创建数据源
@router.post("", response_model=schemas.DataSource)
def create_data_source(
    data_source: schemas.DataSourceCreate,
    db: Session = Depends(get_db),
    space_id: Optional[int] = Depends(get_space_id),
    operator_id: int = Depends(RequireSystemPermission("*")),
):
    return create_data_source_service(db, data_source, space_id)


# 获取数据源列表
@router.get("", response_model=List[schemas.DataSource])
def get_data_source_list(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    space_id: Optional[int] = Depends(get_space_id)
):
    return list_data_source_service(db, skip, limit, space_id)


# 获取单个数据源
@router.get("/{data_source_id}", response_model=schemas.DataSource)
def get_data_source(
    data_source_id: int,
    db: Session = Depends(get_db),
    space_id: Optional[int] = Depends(get_space_id)
):
    return get_data_source_service(db, data_source_id, space_id)


# 检查数据源是否被知识接入引用
@router.get("/{data_source_id}/check_ka_refs")
def check_data_source_ka_refs(
    data_source_id: int,
    db: Session = Depends(get_db),
    space_id: Optional[int] = Depends(get_space_id)
):
    """检查数据源是否被知识接入引用"""
    knowledge_accesses = get_knowledge_accesses_by_data_source(db, data_source_id, space_id)
    if knowledge_accesses:
        return {
            "can_delete": False,
            "message": "该数据源被以下知识接入引用，无法删除",
            "knowledge_accesses": [{"id": ka.id, "name": ka.name, "description": ka.description} for ka in knowledge_accesses]
        }
    return {
        "can_delete": True,
        "message": "该数据源未被任何知识接入引用",
        "knowledge_accesses": []
    }


# 测试数据源连接
@router.post("/test", response_model=schemas.DataSourceTestResponse)
def test_data_source(
    data_source: schemas.DataSourceTestRequest,
    operator_id: int = Depends(RequireSystemPermission("*")),
):
    return test_data_source_connection(data_source)


# 更新数据源
@router.put("/{data_source_id}", response_model=schemas.DataSource)
def update_data_source(
    data_source_id: int,
    data_source: schemas.DataSourceUpdate,
    db: Session = Depends(get_db),
    space_id: Optional[int] = Depends(get_space_id),
    operator_id: int = Depends(RequireSystemPermission("*")),
):
    return update_data_source_service(db, data_source_id, data_source, space_id)


# 获取解密后的数据源密码（仅超管）
@router.get("/{data_source_id}/reveal-password")
def reveal_data_source_password(
    data_source_id: int,
    db: Session = Depends(get_db),
    space_id: Optional[int] = Depends(get_space_id),
    operator_id: int = Depends(RequireSystemPermission("*")),
):
    return reveal_password_service(db, data_source_id, space_id)


# 删除数据源（软删除）
@router.delete("/{data_source_id}")
def delete_data_source(
    data_source_id: int,
    db: Session = Depends(get_db),
    space_id: Optional[int] = Depends(get_space_id),
    operator_id: int = Depends(RequireSystemPermission("*")),
):
    return delete_data_source_service(db, data_source_id, space_id)
