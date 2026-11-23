from typing import Optional, List
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ...core.database import get_db
from ...core.dependencies import get_current_user_id
from ...schemas.eval import EvalRunResponse, EvalManualCorrection
from ...services.eval import eval_comparison_service

router = APIRouter(tags=["评测运行记录"])


@router.get("/eval/sub-tasks/{sub_task_id}/runs", response_model=dict)
def list_runs(
    sub_task_id: int,
    status: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """获取运行记录列表"""
    return eval_comparison_service.list_runs_service(db, sub_task_id, status, skip, limit)


@router.get("/eval/runs/{run_id}", response_model=dict)
def get_run(run_id: int, db: Session = Depends(get_db)):
    """获取运行记录详情"""
    return eval_comparison_service.get_run_service(db, run_id)


@router.put("/eval/runs/{run_id}/manual")
def manual_correct(
    run_id: int,
    data: EvalManualCorrection,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """人工标注"""
    return eval_comparison_service.manual_correct_service(db, run_id, data, user_id)


@router.post("/eval/runs/batch-recompare", response_model=dict)
def batch_recompare(run_ids: List[int], db: Session = Depends(get_db)):
    """批量重新对比"""
    return eval_comparison_service.batch_recompare(db, run_ids)


@router.get("/eval/comparisons/{run_id}")
def get_comparison(run_id: int, db: Session = Depends(get_db)):
    """获取对比详情"""
    return eval_comparison_service.get_comparison_service(db, run_id)
