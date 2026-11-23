"""评测用例数据访问层"""
from typing import Any, Dict, List, Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from ...models.eval import EvalCase


def list_cases(
    db: Session,
    suite_id: int,
    is_active: bool = None,
    difficulty: str = None,
    category: str = None,
    keyword: str = None,
    skip: int = 0,
    limit: int = 50,
) -> List[EvalCase]:
    """列出评测集下的用例"""
    q = db.query(EvalCase).filter(EvalCase.suite_id == suite_id)
    if is_active is not None:
        q = q.filter(EvalCase.is_active == is_active)
    if difficulty is not None:
        q = q.filter(EvalCase.difficulty == difficulty)
    if category is not None:
        q = q.filter(EvalCase.category == category)
    if keyword and keyword.strip():
        kw = f"%{keyword.strip()}%"
        q = q.filter(EvalCase.input_prompt.like(kw))
    return (
        q.order_by(EvalCase.sort_order.asc(), EvalCase.id.asc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def count_cases(
    db: Session,
    suite_id: int,
    is_active: bool = None,
    difficulty: str = None,
    category: str = None,
) -> int:
    """统计用例数量"""
    q = db.query(func.count(EvalCase.id)).filter(EvalCase.suite_id == suite_id)
    if is_active is not None:
        q = q.filter(EvalCase.is_active == is_active)
    if difficulty is not None:
        q = q.filter(EvalCase.difficulty == difficulty)
    if category is not None:
        q = q.filter(EvalCase.category == category)
    return q.scalar() or 0


def get_case(db: Session, case_id: int, suite_id: int = None) -> Optional[EvalCase]:
    """获取单个用例"""
    q = db.query(EvalCase).filter(EvalCase.id == case_id)
    if suite_id is not None:
        q = q.filter(EvalCase.suite_id == suite_id)
    return q.first()


def create_case(db: Session, suite_id: int, **kwargs) -> EvalCase:
    """创建用例"""
    case = EvalCase(suite_id=suite_id, **kwargs)
    db.add(case)
    db.flush()
    return case


def update_case(db: Session, case_id: int, suite_id: int, **kwargs) -> Optional[EvalCase]:
    """更新用例"""
    case = get_case(db, case_id, suite_id)
    if case is None:
        return None
    for key, value in kwargs.items():
        if value is not None:
            setattr(case, key, value)
    db.flush()
    return case


def delete_case(db: Session, case_id: int, suite_id: int) -> bool:
    """删除用例"""
    case = get_case(db, case_id, suite_id)
    if case is None:
        return False
    db.delete(case)
    db.flush()
    return True


def batch_delete_cases(db: Session, case_ids: List[int], suite_id: int) -> int:
    """批量删除用例，返回删除数量"""
    if not case_ids:
        return 0
    result = (
        db.query(EvalCase)
        .filter(EvalCase.id.in_(case_ids), EvalCase.suite_id == suite_id)
        .delete(synchronize_session=False)
    )
    db.flush()
    return result


def batch_update_cases(db: Session, case_ids: List[int], suite_id: int, **kwargs) -> int:
    """批量更新用例，返回更新数量"""
    if not case_ids:
        return 0
    result = (
        db.query(EvalCase)
        .filter(EvalCase.id.in_(case_ids), EvalCase.suite_id == suite_id)
        .update(kwargs, synchronize_session=False)
    )
    db.flush()
    return result


def get_active_case_ids_by_filter(db: Session, suite_id: int, case_filter: dict = None) -> List[int]:
    """根据过滤条件获取启用的用例ID列表"""
    q = db.query(EvalCase.id).filter(
        EvalCase.suite_id == suite_id, EvalCase.is_active == True  # noqa: E712
    )
    if case_filter:
        if case_filter.get("difficulty"):
            q = q.filter(EvalCase.difficulty == case_filter["difficulty"])
        if case_filter.get("category"):
            q = q.filter(EvalCase.category == case_filter["category"])
        if case_filter.get("keyword"):
            kw = f"%{case_filter['keyword'].strip()}%"
            q = q.filter(EvalCase.input_prompt.like(kw))
    rows = q.order_by(EvalCase.sort_order.asc(), EvalCase.id.asc()).all()
    return [r[0] for r in rows]
