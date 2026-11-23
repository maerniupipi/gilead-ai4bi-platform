from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ...core.database import get_db
from ...core.dependencies import get_current_user_id
from ...models.eval import EvalComparisonTemplate
from ...schemas.eval.eval_comparison_template import (
    EvalComparisonTemplateCreate, EvalComparisonTemplateUpdate,
    EvalComparisonTemplateResponse,
)
from ...services.eval.eval_comparison_template_defaults import (
    seed_system_templates_for_space,
)

router = APIRouter(prefix="/spaces/{space_id}/eval/comparison-templates", tags=["评测对比模板"])


@router.get("")
def list_templates(
    space_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """获取对比模板列表"""
    seed_system_templates_for_space(db, space_id)
    q = db.query(EvalComparisonTemplate).filter(EvalComparisonTemplate.space_id == space_id)
    total = q.count()
    items = q.order_by(EvalComparisonTemplate.is_system.desc(), EvalComparisonTemplate.is_default.desc(), EvalComparisonTemplate.id.desc()).offset(skip).limit(limit).all()
    return {
        "items": [EvalComparisonTemplateResponse.model_validate(t) for t in items],
        "total": total,
    }


@router.post("", response_model=EvalComparisonTemplateResponse)
def create_template(
    space_id: int,
    data: EvalComparisonTemplateCreate,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """创建对比模板"""
    tpl = EvalComparisonTemplate(space_id=space_id, **data.model_dump())
    db.add(tpl)
    db.commit()
    db.refresh(tpl)
    return tpl


@router.get("/{template_id}", response_model=EvalComparisonTemplateResponse)
def get_template(space_id: int, template_id: int, db: Session = Depends(get_db)):
    """获取对比模板详情"""
    tpl = db.query(EvalComparisonTemplate).filter(
        EvalComparisonTemplate.id == template_id,
        EvalComparisonTemplate.space_id == space_id,
    ).first()
    if not tpl:
        raise HTTPException(status_code=404, detail="模板不存在")
    return tpl


@router.put("/{template_id}", response_model=EvalComparisonTemplateResponse)
def update_template(
    space_id: int, template_id: int,
    data: EvalComparisonTemplateUpdate,
    db: Session = Depends(get_db),
):
    """更新对比模板"""
    tpl = db.query(EvalComparisonTemplate).filter(
        EvalComparisonTemplate.id == template_id,
        EvalComparisonTemplate.space_id == space_id,
    ).first()
    if not tpl:
        raise HTTPException(status_code=404, detail="模板不存在")
    update_data = data.model_dump(exclude_unset=True)
    if tpl.is_system:
        # 系统模板只允许修改 is_default，不允许修改内容
        content_keys = {"name", "description", "system_prompt", "user_prompt", "comparison_method"}
        if content_keys & update_data.keys():
            raise HTTPException(status_code=403, detail="系统内置模板不可编辑")
    for k, v in update_data.items():
        setattr(tpl, k, v)
    db.commit()
    db.refresh(tpl)
    return tpl


@router.delete("/{template_id}")
def delete_template(space_id: int, template_id: int, db: Session = Depends(get_db)):
    """删除对比模板"""
    tpl = db.query(EvalComparisonTemplate).filter(
        EvalComparisonTemplate.id == template_id,
        EvalComparisonTemplate.space_id == space_id,
    ).first()
    if not tpl:
        raise HTTPException(status_code=404, detail="模板不存在")
    if tpl.is_system:
        raise HTTPException(status_code=403, detail="系统内置模板不可删除")
    db.delete(tpl)
    db.commit()
    return {"ok": True}


@router.post("/{template_id}/clone", response_model=EvalComparisonTemplateResponse)
def clone_template(
    space_id: int, template_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """克隆模板"""
    tpl = db.query(EvalComparisonTemplate).filter(
        EvalComparisonTemplate.id == template_id,
        EvalComparisonTemplate.space_id == space_id,
    ).first()
    if not tpl:
        raise HTTPException(status_code=404, detail="模板不存在")
    clone = EvalComparisonTemplate(
        space_id=space_id,
        name=f"{tpl.name}(副本)",
        description=tpl.description,
        system_prompt=tpl.system_prompt,
        user_prompt=tpl.user_prompt,
        comparison_method=tpl.comparison_method,
        is_default=False,
        is_system=False,
    )
    db.add(clone)
    db.commit()
    db.refresh(clone)
    return clone
