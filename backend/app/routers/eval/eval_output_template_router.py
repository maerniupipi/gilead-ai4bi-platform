from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...core.database import get_db
from ...schemas.eval import (
    EvalOutputTemplateCreate, EvalOutputTemplateUpdate, EvalOutputTemplateResponse,
)
from ...services.eval import eval_output_template_service

router = APIRouter(tags=["输出模板"])


@router.get("/eval/suites/{suite_id}/templates", response_model=List[EvalOutputTemplateResponse])
def list_templates(suite_id: int, db: Session = Depends(get_db)):
    """获取输出模板列表"""
    return eval_output_template_service.list_templates_service(db, suite_id)


@router.post("/eval/suites/{suite_id}/templates", response_model=EvalOutputTemplateResponse)
def create_template(suite_id: int, data: EvalOutputTemplateCreate, db: Session = Depends(get_db)):
    """创建输出模板"""
    return eval_output_template_service.create_template_service(db, suite_id, data.model_dump())


@router.put("/eval/templates/{template_id}", response_model=EvalOutputTemplateResponse)
def update_template(template_id: int, data: EvalOutputTemplateUpdate, db: Session = Depends(get_db)):
    """更新输出模板"""
    return eval_output_template_service.update_template_service(db, template_id, data.model_dump(exclude_unset=True))


@router.delete("/eval/templates/{template_id}")
def delete_template(template_id: int, db: Session = Depends(get_db)):
    """删除输出模板"""
    return eval_output_template_service.delete_template_service(db, template_id)


@router.put("/eval/templates/{template_id}/set-default")
def set_default_template(template_id: int, suite_id: int, db: Session = Depends(get_db)):
    """设为默认模板"""
    return eval_output_template_service.set_default_service(db, template_id, suite_id)
