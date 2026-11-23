"""评测对比记录数据访问层"""
from typing import List, Optional

from sqlalchemy.orm import Session

from ...models.eval import EvalComparison


def get_comparison_by_run(db: Session, run_id: int) -> Optional[EvalComparison]:
    """获取运行记录的对比结果"""
    return (
        db.query(EvalComparison)
        .filter(EvalComparison.run_id == run_id)
        .order_by(EvalComparison.id.desc())
        .first()
    )


def create_comparison(
    db: Session,
    run_id: int,
    ground_truth_id: int,
    comparison_method: str,
    is_correct: bool,
    score,
    comparison_detail: dict,
    llm_judge_raw_output: str = None,
) -> EvalComparison:
    """创建对比记录"""
    comparison = EvalComparison(
        run_id=run_id,
        ground_truth_id=ground_truth_id,
        comparison_method=comparison_method,
        is_correct=is_correct,
        score=score,
        comparison_detail=comparison_detail,
        llm_judge_raw_output=llm_judge_raw_output,
    )
    db.add(comparison)
    db.flush()
    return comparison


def delete_comparison(db: Session, run_id: int) -> bool:
    """删除运行记录的所有对比结果"""
    result = (
        db.query(EvalComparison)
        .filter(EvalComparison.run_id == run_id)
        .delete(synchronize_session=False)
    )
    db.flush()
    return result > 0


def batch_get_comparisons(db: Session, run_ids: List[int]) -> List[EvalComparison]:
    """批量获取对比记录"""
    if not run_ids:
        return []
    return (
        db.query(EvalComparison)
        .filter(EvalComparison.run_id.in_(run_ids))
        .all()
    )
