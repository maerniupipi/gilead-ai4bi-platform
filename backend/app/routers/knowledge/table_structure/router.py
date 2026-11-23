from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from .... import schemas
from ....core.database import get_db
from ....core.permissions import RequireSystemPermission
from ....services.knowledge.table_structure.service import (
    create_table_field_service,
    create_table_structure_service,
    get_table_fields_service,
    get_enabled_table_fields_service,
    get_table_structures_service,
    update_table_field_service,
    update_table_structure_service,
    get_database_tables_service,
    import_tables_service,
    delete_table_structure_service,
)

router = APIRouter(
    prefix="/table_structure",
    tags=["table_structure"]
)


def get_space_id(space_id: Optional[int] = Query(None, description="空间ID")) -> Optional[int]:
    return space_id


# 获取知识接入的表结构列表
@router.get("/knowledge_access/{knowledge_access_id}", response_model=List[schemas.TableStructure])
def get_table_structures(
    knowledge_access_id: int,
    db: Session = Depends(get_db),
    space_id: Optional[int] = Depends(get_space_id)
):
    return get_table_structures_service(db, knowledge_access_id, space_id)


# 获取表结构的字段列表
@router.get("/{table_structure_id}/fields", response_model=List[schemas.TableField])
def get_table_fields(
    table_structure_id: int,
    enabled_only: bool = Query(False, description="是否只返回生效字段"),
    db: Session = Depends(get_db)
):
    if enabled_only:
        return get_enabled_table_fields_service(db, table_structure_id)
    return get_table_fields_service(db, table_structure_id)


# 创建表结构
@router.post("", response_model=schemas.TableStructure)
def create_table_structure(
    table_structure: schemas.TableStructureCreate,
    knowledge_access_id: int,
    db: Session = Depends(get_db),
    space_id: Optional[int] = Depends(get_space_id),
    operator_id: int = Depends(RequireSystemPermission("*")),
):
    return create_table_structure_service(db, knowledge_access_id, table_structure, space_id)


# 更新表结构
@router.put("/{table_structure_id}", response_model=schemas.TableStructure)
def update_table_structure(
    table_structure_id: int,
    table_structure: schemas.TableStructureUpdate,
    db: Session = Depends(get_db),
    space_id: Optional[int] = Depends(get_space_id),
    operator_id: int = Depends(RequireSystemPermission("*")),
):
    return update_table_structure_service(db, table_structure_id, table_structure, space_id)


# 删除表结构
@router.delete("/{table_structure_id}")
def delete_table_structure(
    table_structure_id: int,
    db: Session = Depends(get_db),
    space_id: Optional[int] = Depends(get_space_id),
    operator_id: int = Depends(RequireSystemPermission("*")),
):
    return delete_table_structure_service(db, table_structure_id, space_id)


# 创建表字段
@router.post("/{table_structure_id}/fields", response_model=schemas.TableField)
def create_table_field(
    table_structure_id: int,
    table_field: schemas.TableFieldCreate,
    db: Session = Depends(get_db)
):
    return create_table_field_service(db, table_structure_id, table_field)


# 更新表字段
@router.put("/fields/{table_field_id}", response_model=schemas.TableField)
def update_table_field(
    table_field_id: int,
    table_field: schemas.TableFieldUpdate,
    db: Session = Depends(get_db)
):
    return update_table_field_service(db, table_field_id, table_field)


# 获取外部数据库的表列表
@router.get("/import/{knowledge_access_id}/tables", response_model=List[schemas.TableInfo])
def get_database_tables(
    knowledge_access_id: int,
    db: Session = Depends(get_db),
    space_id: Optional[int] = Depends(get_space_id)
):
    return get_database_tables_service(db, knowledge_access_id, space_id)


# 导入表结构
@router.post("/import/{knowledge_access_id}", response_model=schemas.ImportTablesResponse)
def import_tables(
    knowledge_access_id: int,
    request: schemas.ImportTablesRequest,
    db: Session = Depends(get_db),
    space_id: Optional[int] = Depends(get_space_id),
    operator_id: int = Depends(RequireSystemPermission("*")),
):
    return import_tables_service(db, knowledge_access_id, request.table_names, space_id)
