from typing import Optional
from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy.orm import Session

from ...core.database import get_db
from ...core.dependencies import get_current_user_id
from ...schemas.eval import (
    EvalSuiteCreate, EvalSuiteUpdate, EvalSuiteResponse,
    EvalShareIssueRequest, EvalShareIssueOut,
)
from ...services.eval import eval_suite_service

router = APIRouter(prefix="/spaces/{space_id}/eval/suites", tags=["评测集"])


@router.get("", response_model=dict)
def list_suites(
    space_id: int,
    folder_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    tag_id: Optional[int] = Query(None),
    keyword: Optional[str] = Query(None, description="搜索关键词"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=2000),
    db: Session = Depends(get_db),
):
    """获取评测集列表"""
    return eval_suite_service.list_suites_service(db, space_id, folder_id, status, tag_id, skip, limit, keyword)


@router.post("", response_model=EvalSuiteResponse)
def create_suite(
    space_id: int,
    data: EvalSuiteCreate,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """创建评测集"""
    return eval_suite_service.create_suite_service(db, space_id, user_id, data.model_dump())


@router.get("/{suite_id}", response_model=EvalSuiteResponse)
def get_suite(space_id: int, suite_id: int, db: Session = Depends(get_db)):
    """获取评测集详情"""
    return eval_suite_service.get_suite_service(db, suite_id, space_id)


@router.put("/{suite_id}", response_model=EvalSuiteResponse)
def update_suite(space_id: int, suite_id: int, data: EvalSuiteUpdate, db: Session = Depends(get_db)):
    """更新评测集"""
    return eval_suite_service.update_suite_service(db, suite_id, space_id, data.model_dump(exclude_unset=True))


@router.delete("/{suite_id}")
def delete_suite(space_id: int, suite_id: int, db: Session = Depends(get_db)):
    """删除评测集"""
    return eval_suite_service.delete_suite_service(db, suite_id, space_id)


@router.post("/{suite_id}/copy", response_model=EvalSuiteResponse)
def copy_suite(
    space_id: int,
    suite_id: int,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """复制评测集"""
    return eval_suite_service.copy_suite_service(db, suite_id, space_id, user_id)


@router.get("/{suite_id}/export")
def export_suite(space_id: int, suite_id: int, db: Session = Depends(get_db)):
    """导出评测集"""
    return eval_suite_service.export_suite_service(db, suite_id, space_id)


@router.post("/{suite_id}/share", response_model=EvalShareIssueOut)
def issue_share(
    space_id: int,
    suite_id: int,
    body: EvalShareIssueRequest = Body(default_factory=EvalShareIssueRequest),
    db: Session = Depends(get_db),
):
    """生成或复用分享 token"""
    return eval_suite_service.issue_share_token_service(db, suite_id, space_id, rotate=body.rotate)


@router.delete("/{suite_id}/share")
def revoke_share(space_id: int, suite_id: int, db: Session = Depends(get_db)):
    """撤销分享 token"""
    eval_suite_service.revoke_share_token_service(db, suite_id, space_id)
    return {"revoked": True}
