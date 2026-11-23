"""评测任务数据访问层"""
from typing import List, Optional

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from ...models.eval import EvalTask, EvalSuite


def list_tasks(
    db: Session,
    space_id: int,
    suite_id: int = None,
    status: str = None,
    skip: int = 0,
    limit: int = 50,
) -> List[EvalTask]:
    """列出空间下的评测任务（通过 join suite 过滤 space_id）"""
    q = (
        db.query(EvalTask)
        .join(EvalSuite, EvalSuite.id == EvalTask.suite_id)
        .filter(EvalSuite.space_id == space_id)
    )
    if suite_id is not None:
        q = q.filter(EvalTask.suite_id == suite_id)
    if status is not None:
        q = q.filter(EvalTask.status == status)
    return (
        q.order_by(EvalTask.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def count_tasks(
    db: Session,
    space_id: int,
    suite_id: int = None,
    status: str = None,
) -> int:
    """统计任务数量"""
    q = (
        db.query(func.count(EvalTask.id))
        .join(EvalSuite, EvalSuite.id == EvalTask.suite_id)
        .filter(EvalSuite.space_id == space_id)
    )
    if suite_id is not None:
        q = q.filter(EvalTask.suite_id == suite_id)
    if status is not None:
        q = q.filter(EvalTask.status == status)
    return q.scalar() or 0


def get_task(db: Session, task_id: int, space_id: int = None) -> Optional[EvalTask]:
    """获取单个任务"""
    q = db.query(EvalTask).filter(EvalTask.id == task_id)
    if space_id is not None:
        q = q.join(EvalSuite, EvalSuite.id == EvalTask.suite_id).filter(
            EvalSuite.space_id == space_id
        )
    return q.first()


def create_task(db: Session, **kwargs) -> EvalTask:
    """创建任务"""
    task = EvalTask(**kwargs)
    db.add(task)
    db.flush()
    return task


def update_task(db: Session, task_id: int, **kwargs) -> Optional[EvalTask]:
    """更新任务"""
    task = db.query(EvalTask).filter(EvalTask.id == task_id).first()
    if task is None:
        return None
    for key, value in kwargs.items():
        if value is not None:
            setattr(task, key, value)
    db.flush()
    return task


def delete_task(db: Session, task_id: int) -> bool:
    """删除任务（仅允许删除 draft 状态）"""
    task = db.query(EvalTask).filter(EvalTask.id == task_id).first()
    if task is None:
        return False
    if task.status != "draft":
        raise HTTPException(status_code=400, detail="仅允许删除草稿状态的任务")
    db.delete(task)
    db.flush()
    return True
