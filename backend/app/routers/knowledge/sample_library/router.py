from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from .... import schemas
from ....core.database import get_db
from ....core.permissions import RequireSystemPermission
from ....services.knowledge.sample_library.service import (
    create_sample_library_service,
    delete_sample_library_service,
    export_sample_libraries_service,
    get_sample_libraries_service,
    import_sample_libraries_service,
    update_sample_library_service,
)

router = APIRouter(
    prefix="/sample_library",
    tags=["sample_library"]
)


def get_space_id(space_id: Optional[int] = Query(None, description="空间ID")) -> Optional[int]:
    return space_id


# 获取知识接入的样例列表
@router.get("/knowledge_access/{knowledge_access_id}", response_model=schemas.SampleLibraryPage)
def get_sample_libraries(
    knowledge_access_id: int,
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db),
    space_id: Optional[int] = Depends(get_space_id)
):
    return get_sample_libraries_service(db, knowledge_access_id, skip, limit, space_id)


# 创建样例
@router.post("", response_model=schemas.SampleLibrary)
def create_sample_library(
    sample_library: schemas.SampleLibraryCreate,
    knowledge_access_id: int,
    db: Session = Depends(get_db),
    space_id: Optional[int] = Depends(get_space_id),
    operator_id: int = Depends(RequireSystemPermission("*")),
):
    return create_sample_library_service(db, knowledge_access_id, sample_library, space_id)


# 更新样例
@router.put("/{sample_library_id}", response_model=schemas.SampleLibrary)
def update_sample_library(
    sample_library_id: int,
    sample_library: schemas.SampleLibraryUpdate,
    db: Session = Depends(get_db),
    space_id: Optional[int] = Depends(get_space_id),
    operator_id: int = Depends(RequireSystemPermission("*")),
):
    return update_sample_library_service(db, sample_library_id, sample_library, space_id)


# 删除样例（软删除）
@router.delete("/{sample_library_id}")
def delete_sample_library(
    sample_library_id: int,
    db: Session = Depends(get_db),
    space_id: Optional[int] = Depends(get_space_id),
    operator_id: int = Depends(RequireSystemPermission("*")),
):
    return delete_sample_library_service(db, sample_library_id, space_id)


# 导出全部样例
@router.get("/knowledge_access/{knowledge_access_id}/export", response_model=List[schemas.SampleLibrary])
def export_sample_libraries(
    knowledge_access_id: int,
    db: Session = Depends(get_db),
    space_id: Optional[int] = Depends(get_space_id),
):
    return export_sample_libraries_service(db, knowledge_access_id, space_id)


# 导入样例
@router.post("/knowledge_access/{knowledge_access_id}/import", response_model=schemas.SampleLibraryImportResult)
def import_sample_libraries(
    knowledge_access_id: int,
    body: schemas.SampleLibraryImportRequest,
    db: Session = Depends(get_db),
    space_id: Optional[int] = Depends(get_space_id),
    operator_id: int = Depends(RequireSystemPermission("*")),
):
    return import_sample_libraries_service(db, knowledge_access_id, body, space_id)
