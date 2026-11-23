from typing import Optional, List
from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy.orm import Session

from ...core.database import get_db
from ...schemas.eval import (
    EvalCaseCreate, EvalCaseUpdate, EvalCaseResponse,
    EvalGenerateRequest, EvalImportRequest,
)
from ...services.eval import eval_case_service

router = APIRouter(tags=["评测用例"])


@router.get("/eval/suites/{suite_id}/cases", response_model=dict)
def list_cases(
    suite_id: int,
    is_active: Optional[bool] = Query(None),
    difficulty: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """获取用例列表"""
    return eval_case_service.list_cases_service(
        db, suite_id, {
            "is_active": is_active,
            "difficulty": difficulty,
            "category": category,
            "keyword": keyword,
            "skip": skip,
            "limit": limit,
        }
    )


@router.post("/eval/suites/{suite_id}/cases", response_model=EvalCaseResponse)
def create_case(suite_id: int, data: EvalCaseCreate, db: Session = Depends(get_db)):
    """创建单条用例"""
    return eval_case_service.create_case_service(db, suite_id, data.model_dump())


@router.post("/eval/suites/{suite_id}/cases/batch", response_model=dict)
def batch_create_cases(suite_id: int, data: List[EvalCaseCreate], db: Session = Depends(get_db)):
    """批量创建用例"""
    return eval_case_service.batch_create_cases_service(db, suite_id, [d.model_dump() for d in data])


@router.put("/eval/cases/{case_id}", response_model=EvalCaseResponse)
def update_case(case_id: int, data: EvalCaseUpdate, suite_id: int = Query(...), db: Session = Depends(get_db)):
    """更新用例"""
    return eval_case_service.update_case_service(db, case_id, suite_id, data.model_dump(exclude_unset=True))


@router.delete("/eval/cases/{case_id}")
def delete_case(case_id: int, suite_id: int = Query(...), db: Session = Depends(get_db)):
    """删除用例"""
    return eval_case_service.delete_case_service(db, case_id, suite_id)


@router.post("/eval/suites/{suite_id}/cases/batch-update", response_model=dict)
def batch_update_cases(
    suite_id: int,
    case_ids: List[int] = Body(...),
    data: EvalCaseUpdate = Body(...),
    db: Session = Depends(get_db),
):
    """批量更新用例"""
    return eval_case_service.batch_update_cases_service(db, case_ids, suite_id, data.model_dump(exclude_unset=True))


@router.post("/eval/suites/{suite_id}/cases/batch-delete", response_model=dict)
def batch_delete_cases(suite_id: int, case_ids: List[int] = Body(...), db: Session = Depends(get_db)):
    """批量删除用例"""
    return eval_case_service.batch_delete_cases_service(db, case_ids, suite_id)


@router.post("/eval/suites/{suite_id}/cases/generate", response_model=dict)
async def generate_cases(suite_id: int, params: EvalGenerateRequest, db: Session = Depends(get_db)):
    """LLM 生成用例"""
    from ...services.eval.eval_case_generate_service import generate_cases_service
    return await generate_cases_service(db, suite_id, params.model_dump())


@router.post("/eval/suites/{suite_id}/cases/import/preview", response_model=dict)
def import_preview(suite_id: int, data: list, db: Session = Depends(get_db)):
    """导入预览"""
    return eval_case_service.import_preview_service(db, data)


@router.post("/eval/suites/{suite_id}/cases/import", response_model=dict)
def import_cases(suite_id: int, data: EvalImportRequest, db: Session = Depends(get_db)):
    """执行导入"""
    return eval_case_service.import_cases_service(db, suite_id, data.model_dump())


@router.get("/eval/suites/{suite_id}/cases/export", response_model=list)
def export_cases(suite_id: int, db: Session = Depends(get_db)):
    """导出用例"""
    return eval_case_service.export_cases_service(db, suite_id)


@router.get("/eval/suites/import-template")
def download_import_template():
    """下载导入模板"""
    return eval_case_service.download_import_template_service()
