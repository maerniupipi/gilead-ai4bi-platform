"""评测集数据访问层"""
from typing import List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from ...models.eval import EvalSuite, EvalSuiteTag, EvalCase


def list_suites(
    db: Session,
    space_id: int,
    folder_id: int = None,
    status: str = None,
    tag_id: int = None,
    skip: int = 0,
    limit: int = 50,
) -> List[EvalSuite]:
    """列出评测集，支持按文件夹、状态、标签过滤"""
    q = db.query(EvalSuite).filter(EvalSuite.space_id == space_id)
    if folder_id is not None:
        q = q.filter(EvalSuite.folder_id == folder_id)
    if status is not None:
        q = q.filter(EvalSuite.status == status)
    if tag_id is not None:
        q = q.join(EvalSuiteTag, EvalSuiteTag.suite_id == EvalSuite.id).filter(
            EvalSuiteTag.tag_id == tag_id
        )
    return (
        q.order_by(EvalSuite.updated_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def count_suites(
    db: Session,
    space_id: int,
    folder_id: int = None,
    status: str = None,
) -> int:
    """统计评测集数量"""
    q = db.query(func.count(EvalSuite.id)).filter(EvalSuite.space_id == space_id)
    if folder_id is not None:
        q = q.filter(EvalSuite.folder_id == folder_id)
    if status is not None:
        q = q.filter(EvalSuite.status == status)
    return q.scalar() or 0


def get_suite(db: Session, suite_id: int, space_id: int = None) -> Optional[EvalSuite]:
    """获取单个评测集"""
    q = db.query(EvalSuite).filter(EvalSuite.id == suite_id)
    if space_id is not None:
        q = q.filter(EvalSuite.space_id == space_id)
    return q.first()


def create_suite(db: Session, **kwargs) -> EvalSuite:
    """创建评测集"""
    suite = EvalSuite(**kwargs)
    db.add(suite)
    db.flush()
    return suite


def update_suite(db: Session, suite_id: int, space_id: int, **kwargs) -> Optional[EvalSuite]:
    """更新评测集"""
    suite = get_suite(db, suite_id, space_id)
    if suite is None:
        return None
    for key, value in kwargs.items():
        if value is not None:
            setattr(suite, key, value)
    db.flush()
    return suite


def delete_suite(db: Session, suite_id: int, space_id: int) -> bool:
    """删除评测集"""
    suite = get_suite(db, suite_id, space_id)
    if suite is None:
        return False
    db.delete(suite)
    db.flush()
    return True


def count_cases_for_suite(db: Session, suite_id: int) -> int:
    """统计评测集下的用例数量"""
    return (
        db.query(func.count(EvalCase.id))
        .filter(EvalCase.suite_id == suite_id)
        .scalar()
    ) or 0


def add_suite_tag(db: Session, suite_id: int, tag_id: int) -> None:
    """为评测集添加标签关联"""
    existing = (
        db.query(EvalSuiteTag)
        .filter(EvalSuiteTag.suite_id == suite_id, EvalSuiteTag.tag_id == tag_id)
        .first()
    )
    if existing is None:
        db.add(EvalSuiteTag(suite_id=suite_id, tag_id=tag_id))
        db.flush()


def remove_suite_tag(db: Session, suite_id: int, tag_id: int) -> None:
    """移除评测集的标签关联"""
    db.query(EvalSuiteTag).filter(
        EvalSuiteTag.suite_id == suite_id, EvalSuiteTag.tag_id == tag_id
    ).delete(synchronize_session=False)
    db.flush()


def get_suite_tag_ids(db: Session, suite_id: int) -> List[int]:
    """获取评测集关联的标签ID列表"""
    rows = (
        db.query(EvalSuiteTag.tag_id)
        .filter(EvalSuiteTag.suite_id == suite_id)
        .all()
    )
    return [r[0] for r in rows]
