"""
评测用例参考答案服务层
"""
from typing import Any, Dict, List

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ...models.eval import EvalCaseGroundTruth, EvalCase


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _gt_to_dict(row: EvalCaseGroundTruth) -> Dict[str, Any]:
    return {
        "id": row.id,
        "case_id": row.case_id,
        "version": row.version,
        "ground_truth": row.ground_truth,
        "ground_truth_type": row.ground_truth_type,
        "comparison_method": row.comparison_method,
        "comparison_config": row.comparison_config,
        "is_active": row.is_active,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _validate_case(db: Session, case_id: int) -> EvalCase:
    case = db.query(EvalCase).filter(EvalCase.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="评测用例不存在")
    return case


# ---------------------------------------------------------------------------
# service functions
# ---------------------------------------------------------------------------

def list_ground_truths_service(db: Session, case_id: int) -> List[Dict[str, Any]]:
    """列出用例的所有参考答案。"""
    _validate_case(db, case_id)
    rows = (
        db.query(EvalCaseGroundTruth)
        .filter(EvalCaseGroundTruth.case_id == case_id)
        .order_by(EvalCaseGroundTruth.id.asc())
        .all()
    )
    return [_gt_to_dict(r) for r in rows]


def create_ground_truth_service(db: Session, case_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
    """创建参考答案。"""
    _validate_case(db, case_id)

    ground_truth = (data.get("ground_truth") or "").strip()
    if not ground_truth:
        raise HTTPException(status_code=400, detail="参考答案内容不能为空")

    comparison_method = (data.get("comparison_method") or "exact").strip()
    if not comparison_method:
        raise HTTPException(status_code=400, detail="对比方式不能为空")

    row = EvalCaseGroundTruth(
        case_id=case_id,
        version=data.get("version", "v1.0"),
        ground_truth=ground_truth,
        ground_truth_type=data.get("ground_truth_type", "text"),
        comparison_method=comparison_method,
        comparison_config=data.get("comparison_config"),
        is_active=data.get("is_active", True),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _gt_to_dict(row)


def update_ground_truth_service(db: Session, gt_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
    """更新参考答案。"""
    row = db.query(EvalCaseGroundTruth).filter(EvalCaseGroundTruth.id == gt_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="参考答案不存在")

    if "ground_truth" in data:
        gt = (data["ground_truth"] or "").strip()
        if not gt:
            raise HTTPException(status_code=400, detail="参考答案内容不能为空")
        row.ground_truth = gt

    if "ground_truth_type" in data:
        row.ground_truth_type = data["ground_truth_type"]

    if "version" in data:
        row.version = data["version"]

    if "comparison_method" in data:
        cm = (data["comparison_method"] or "").strip()
        if not cm:
            raise HTTPException(status_code=400, detail="对比方式不能为空")
        row.comparison_method = cm

    if "comparison_config" in data:
        row.comparison_config = data["comparison_config"]

    if "is_active" in data:
        row.is_active = bool(data["is_active"])

    db.commit()
    db.refresh(row)
    return _gt_to_dict(row)


def delete_ground_truth_service(db: Session, gt_id: int) -> Dict[str, Any]:
    """删除参考答案。"""
    row = db.query(EvalCaseGroundTruth).filter(EvalCaseGroundTruth.id == gt_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="参考答案不存在")

    db.delete(row)
    db.commit()
    return {"ok": True}
