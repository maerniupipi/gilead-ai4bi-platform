from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional, Union
from .... import schemas
from ....core.database import get_db
from ....core.permissions import RequireSystemPermission
from ....repositories.autobi.repository import get_autobi_projects_by_knowledge_base
from ....services.knowledge.knowledge_base.service import (
    batch_select_table_structures_service,
    batch_select_knowledge_terms_service,
    batch_select_sample_libraries_service,
    get_knowledge_base_detail_service,
    create_knowledge_base_service,
    list_knowledge_base_service,
    get_kb_table_structure_service,
    clone_knowledge_base_service,
    update_knowledge_base_service,
    delete_knowledge_base_service,
    execute_knowledge_base_sql_service,
    vectorize_knowledge_base_service,
    cancel_vectorization_service,
    update_kb_table_structure_service,
    delete_kb_table_structure_service,
    update_kb_table_field_service,
    delete_kb_table_field_service,
    delete_kb_knowledge_term_service,
    delete_kb_sample_library_service,
)
from ....services.knowledge.kb_ner_service import (
    list_ner_sheets_service,
    list_ner_rows_page_service,
    create_ner_row_service,
    update_ner_row_service,
    delete_ner_row_service,
    delete_ner_sheet_service,
    export_all_ner_rows_service,
    import_ner_rows_service,
)

router = APIRouter(
    prefix="/knowledge_base",
    tags=["knowledge_base"]
)


def get_space_id(space_id: Optional[int] = Query(None, description="空间ID")) -> Optional[int]:
    return space_id


# 创建知识库
@router.post("", response_model=schemas.KnowledgeBase)
def create_knowledge_base(
    knowledge_base: schemas.KnowledgeBaseCreate,
    db: Session = Depends(get_db),
    space_id: Optional[int] = Depends(get_space_id),
    operator_id: int = Depends(RequireSystemPermission("*")),
):
    return create_knowledge_base_service(db, knowledge_base, space_id)


# 获取知识库列表
@router.get("", response_model=List[schemas.KnowledgeBase])
def get_knowledge_base_list(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    space_id: Optional[int] = Depends(get_space_id)
):
    return list_knowledge_base_service(db, skip, limit, space_id)

# 获取单个知识库表结构及其字段
@router.get("/table_structures/{kb_table_structure_id}", response_model=schemas.KbTableStructure)
def get_kb_table_structure(
    kb_table_structure_id: int,
    db: Session = Depends(get_db),
    space_id: Optional[int] = Depends(get_space_id)
):
    return get_kb_table_structure_service(db, kb_table_structure_id, space_id)


# 删除知识库表结构
@router.delete("/table_structures/{kb_table_structure_id}")
def delete_kb_table_structure(
    kb_table_structure_id: int,
    db: Session = Depends(get_db),
    space_id: Optional[int] = Depends(get_space_id)
):
    return delete_kb_table_structure_service(db, kb_table_structure_id, space_id)


# 更新知识库表结构（向量化设置）
@router.put("/table_structures/{kb_table_structure_id}", response_model=schemas.KbTableStructure)
def update_kb_table_structure(
    kb_table_structure_id: int,
    kb_table_structure: schemas.KbTableStructureUpdate,
    db: Session = Depends(get_db),
    space_id: Optional[int] = Depends(get_space_id)
):
    return update_kb_table_structure_service(db, kb_table_structure_id, kb_table_structure, space_id)


# 获取单个知识库
@router.get("/{knowledge_base_id}", response_model=schemas.KnowledgeBaseDetail)
def get_knowledge_base(
    knowledge_base_id: int,
    db: Session = Depends(get_db),
    space_id: Optional[int] = Depends(get_space_id)
):
    return get_knowledge_base_detail_service(db, knowledge_base_id, space_id)


# 更新知识库
@router.put("/{knowledge_base_id}", response_model=schemas.KnowledgeBase)
def update_knowledge_base(
    knowledge_base_id: int,
    knowledge_base: schemas.KnowledgeBaseUpdate,
    db: Session = Depends(get_db),
    space_id: Optional[int] = Depends(get_space_id),
    operator_id: int = Depends(RequireSystemPermission("*")),
):
    return update_knowledge_base_service(db, knowledge_base_id, knowledge_base, space_id)


# 检查知识库是否被AutoBI引用
@router.get("/{knowledge_base_id}/check_autobi_refs")
def check_knowledge_base_autobi_refs(
    knowledge_base_id: int,
    db: Session = Depends(get_db),
    space_id: Optional[int] = Depends(get_space_id)
):
    """检查知识库是否被AutoBI项目引用"""
    autobi_projects = get_autobi_projects_by_knowledge_base(db, knowledge_base_id, space_id)
    if autobi_projects:
        return {
            "can_delete": False,
            "message": "该知识库被以下AutoBI项目引用，无法删除",
            "autobi_projects": [{"id": p.id, "name": p.name} for p in autobi_projects]
        }
    return {
        "can_delete": True,
        "message": "该知识库未被任何AutoBI项目引用",
        "autobi_projects": []
    }


# ---------- NER 映射（按 Sheet 分组，单库最多 1000 条）----------

@router.get("/{knowledge_base_id}/ner/sheets", response_model=List[schemas.KbNerSheetSummary])
def ner_list_sheets(knowledge_base_id: int, db: Session = Depends(get_db), space_id: Optional[int] = Depends(get_space_id)):
    return list_ner_sheets_service(db, knowledge_base_id, space_id)


@router.get("/{knowledge_base_id}/ner/rows", response_model=schemas.KbNerRowPage)
def ner_list_rows(
    knowledge_base_id: int,
    sheet_name: str = Query(..., description="工作表名"),
    q: Optional[str] = Query(None, description="关键词"),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
    space_id: Optional[int] = Depends(get_space_id),
):
    return list_ner_rows_page_service(
        db, knowledge_base_id, sheet_name, q, page, page_size, space_id
    )


@router.post("/{knowledge_base_id}/ner/rows", response_model=schemas.KbNerRowOut)
def ner_create_row(
    knowledge_base_id: int,
    body: schemas.KbNerRowCreate,
    db: Session = Depends(get_db),
    space_id: Optional[int] = Depends(get_space_id),
):
    return create_ner_row_service(db, knowledge_base_id, body, space_id)


@router.put("/{knowledge_base_id}/ner/rows/{row_id}", response_model=schemas.KbNerRowOut)
def ner_update_row(
    knowledge_base_id: int,
    row_id: int,
    body: schemas.KbNerRowUpdate,
    db: Session = Depends(get_db),
    space_id: Optional[int] = Depends(get_space_id),
):
    return update_ner_row_service(db, knowledge_base_id, row_id, body, space_id)


@router.delete("/{knowledge_base_id}/ner/rows/{row_id}")
def ner_delete_row(
    knowledge_base_id: int,
    row_id: int,
    db: Session = Depends(get_db),
    space_id: Optional[int] = Depends(get_space_id),
):
    return delete_ner_row_service(db, knowledge_base_id, row_id, space_id)


@router.delete("/{knowledge_base_id}/ner/sheet")
def ner_delete_sheet(
    knowledge_base_id: int,
    sheet_name: str = Query(..., description="要清空的工作表名"),
    db: Session = Depends(get_db),
    space_id: Optional[int] = Depends(get_space_id),
):
    return delete_ner_sheet_service(db, knowledge_base_id, sheet_name, space_id)


@router.get("/{knowledge_base_id}/ner/export_rows", response_model=List[schemas.KbNerRowOut])
def ner_export_rows(knowledge_base_id: int, db: Session = Depends(get_db), space_id: Optional[int] = Depends(get_space_id)):
    return export_all_ner_rows_service(db, knowledge_base_id, space_id)


@router.post("/{knowledge_base_id}/ner/import", response_model=schemas.KbNerImportResult)
def ner_import_rows(
    knowledge_base_id: int,
    body: schemas.KbNerImportRequest,
    db: Session = Depends(get_db),
    space_id: Optional[int] = Depends(get_space_id),
):
    return import_ner_rows_service(db, knowledge_base_id, body, space_id)


# 删除知识库（软删除）
@router.delete("/{knowledge_base_id}")
def delete_knowledge_base(
    knowledge_base_id: int,
    db: Session = Depends(get_db),
    space_id: Optional[int] = Depends(get_space_id),
    operator_id: int = Depends(RequireSystemPermission("*")),
):
    return delete_knowledge_base_service(db, knowledge_base_id, space_id)


# 更新知识库表结构（批量选择）
@router.post("/{knowledge_base_id}/table_structures/batch_select", response_model=schemas.KnowledgeBaseDetail)
def batch_select_table_structures(
    knowledge_base_id: int,
    request: Union[schemas.BatchSelectRequest, schemas.BatchSelectFieldsRequest],
    db: Session = Depends(get_db),
    space_id: Optional[int] = Depends(get_space_id)
):
    return batch_select_table_structures_service(db, knowledge_base_id, request, space_id)


# 更新知识库表字段
@router.put("/table_fields/{kb_table_field_id}", response_model=schemas.KbTableField)
def update_kb_table_field(
    kb_table_field_id: int,
    kb_table_field: schemas.KbTableFieldUpdate,
    db: Session = Depends(get_db)
):
    return update_kb_table_field_service(db, kb_table_field_id, kb_table_field)


# 删除知识库表字段
@router.delete("/table_fields/{kb_table_field_id}")
def delete_kb_table_field(
    kb_table_field_id: int,
    db: Session = Depends(get_db)
):
    return delete_kb_table_field_service(db, kb_table_field_id)


# 更新知识库知识词条（批量选择）
@router.post("/{knowledge_base_id}/knowledge_terms/batch_select", response_model=schemas.KnowledgeBaseDetail)
def batch_select_knowledge_terms(
    knowledge_base_id: int,
    request: schemas.BatchSelectRequest,
    db: Session = Depends(get_db),
    space_id: Optional[int] = Depends(get_space_id)
):
    return batch_select_knowledge_terms_service(db, knowledge_base_id, request, space_id)


# 删除知识库知识词条
@router.delete("/knowledge_terms/{kb_knowledge_term_id}")
def delete_kb_knowledge_term(
    kb_knowledge_term_id: int,
    db: Session = Depends(get_db)
):
    return delete_kb_knowledge_term_service(db, kb_knowledge_term_id)


# 更新知识库样例库（批量选择）
@router.post("/{knowledge_base_id}/sample_libraries/batch_select", response_model=schemas.KnowledgeBaseDetail)
def batch_select_sample_libraries(
    knowledge_base_id: int,
    request: schemas.BatchSelectRequest,
    db: Session = Depends(get_db),
    space_id: Optional[int] = Depends(get_space_id)
):
    return batch_select_sample_libraries_service(db, knowledge_base_id, request, space_id)


# 删除知识库样例库
@router.delete("/sample_libraries/{kb_sample_library_id}")
def delete_kb_sample_library(
    kb_sample_library_id: int,
    db: Session = Depends(get_db)
):
    return delete_kb_sample_library_service(db, kb_sample_library_id)


# 按知识库关联数据源执行只读 SQL
@router.post(
    "/{knowledge_base_id}/execute_sql",
    response_model=schemas.KnowledgeBaseExecuteSqlResponse,
)
def execute_knowledge_base_sql(
    knowledge_base_id: int,
    body: schemas.KnowledgeBaseExecuteSqlRequest,
    db: Session = Depends(get_db),
    space_id: Optional[int] = Depends(get_space_id),
    operator_id: int = Depends(RequireSystemPermission("*")),
):
    return execute_knowledge_base_sql_service(db, knowledge_base_id, body.sql, space_id)


# 向量化操作
@router.post("/{knowledge_base_id}/vectorize")
def vectorize_knowledge_base(
    knowledge_base_id: int,
    request: schemas.VectorizeRequest = None,
    db: Session = Depends(get_db),
    space_id: Optional[int] = Depends(get_space_id),
    operator_id: int = Depends(RequireSystemPermission("*")),
):
    return vectorize_knowledge_base_service(db, knowledge_base_id, request, space_id)


@router.post("/{knowledge_base_id}/vectorize/cancel")
def cancel_vectorization(
    knowledge_base_id: int,
    db: Session = Depends(get_db),
    space_id: Optional[int] = Depends(get_space_id),
    operator_id: int = Depends(RequireSystemPermission("*")),
):
    return cancel_vectorization_service(db, knowledge_base_id, space_id)


# 克隆知识库
@router.post("/{knowledge_base_id}/clone", response_model=schemas.KnowledgeBaseDetail)
def clone_knowledge_base(
    knowledge_base_id: int,
    db: Session = Depends(get_db),
    space_id: Optional[int] = Depends(get_space_id),
    operator_id: int = Depends(RequireSystemPermission("*")),
):
    return clone_knowledge_base_service(db, knowledge_base_id, space_id)
