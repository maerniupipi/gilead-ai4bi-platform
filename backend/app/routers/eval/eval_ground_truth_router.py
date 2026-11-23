from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...core.database import get_db
from ...schemas.eval import EvalGroundTruthCreate, EvalGroundTruthUpdate, EvalGroundTruthResponse
from ...services.eval import eval_ground_truth_service

router = APIRouter(tags=["参考答案"])


@router.get("/eval/cases/{case_id}/ground-truths", response_model=List[EvalGroundTruthResponse])
def list_ground_truths(case_id: int, db: Session = Depends(get_db)):
    """获取参考答案列表"""
    return eval_ground_truth_service.list_ground_truths_service(db, case_id)


@router.post("/eval/cases/{case_id}/ground-truths", response_model=EvalGroundTruthResponse)
def create_ground_truth(case_id: int, data: EvalGroundTruthCreate, db: Session = Depends(get_db)):
    """创建参考答案"""
    return eval_ground_truth_service.create_ground_truth_service(db, case_id, data.model_dump())


@router.put("/eval/ground-truths/{gt_id}", response_model=EvalGroundTruthResponse)
def update_ground_truth(gt_id: int, data: EvalGroundTruthUpdate, db: Session = Depends(get_db)):
    """更新参考答案"""
    return eval_ground_truth_service.update_ground_truth_service(db, gt_id, data.model_dump(exclude_unset=True))


@router.delete("/eval/ground-truths/{gt_id}")
def delete_ground_truth(gt_id: int, db: Session = Depends(get_db)):
    """删除参考答案"""
    return eval_ground_truth_service.delete_ground_truth_service(db, gt_id)
