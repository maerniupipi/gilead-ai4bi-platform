"""评测参考答案数据访问层"""
from typing import List, Optional

from sqlalchemy.orm import Session

from ...models.eval import EvalCaseGroundTruth


def list_ground_truths(db: Session, case_id: int) -> List[EvalCaseGroundTruth]:
    """列出用例的所有参考答案"""
    return (
        db.query(EvalCaseGroundTruth)
        .filter(EvalCaseGroundTruth.case_id == case_id)
        .order_by(EvalCaseGroundTruth.id.desc())
        .all()
    )


def get_ground_truth(db: Session, gt_id: int) -> Optional[EvalCaseGroundTruth]:
    """获取单个参考答案"""
    return db.query(EvalCaseGroundTruth).filter(EvalCaseGroundTruth.id == gt_id).first()


def create_ground_truth(db: Session, case_id: int, **kwargs) -> EvalCaseGroundTruth:
    """创建参考答案"""
    gt = EvalCaseGroundTruth(case_id=case_id, **kwargs)
    db.add(gt)
    db.flush()
    return gt


def update_ground_truth(db: Session, gt_id: int, **kwargs) -> Optional[EvalCaseGroundTruth]:
    """更新参考答案"""
    gt = get_ground_truth(db, gt_id)
    if gt is None:
        return None
    for key, value in kwargs.items():
        if value is not None:
            setattr(gt, key, value)
    db.flush()
    return gt


def delete_ground_truth(db: Session, gt_id: int) -> bool:
    """删除参考答案"""
    gt = get_ground_truth(db, gt_id)
    if gt is None:
        return False
    db.delete(gt)
    db.flush()
    return True


def get_active_ground_truth(db: Session, case_id: int) -> Optional[EvalCaseGroundTruth]:
    """获取用例最新的启用参考答案"""
    return (
        db.query(EvalCaseGroundTruth)
        .filter(
            EvalCaseGroundTruth.case_id == case_id,
            EvalCaseGroundTruth.is_active == True,  # noqa: E712
        )
        .order_by(EvalCaseGroundTruth.id.desc())
        .first()
    )
