"""评测子任务数据访问层"""
from typing import List, Optional

from sqlalchemy.orm import Session

from ...models.eval import EvalSubTask


def list_sub_tasks(db: Session, task_id: int) -> List[EvalSubTask]:
    """列出任务下的所有子任务"""
    return (
        db.query(EvalSubTask)
        .filter(EvalSubTask.task_id == task_id)
        .order_by(EvalSubTask.id.asc())
        .all()
    )


def get_sub_task(db: Session, sub_task_id: int) -> Optional[EvalSubTask]:
    """获取单个子任务"""
    return db.query(EvalSubTask).filter(EvalSubTask.id == sub_task_id).first()


def create_sub_task(
    db: Session,
    task_id: int,
    target_type: str,
    target_id: int = None,
    target_config: dict = None,
) -> EvalSubTask:
    """创建子任务"""
    sub_task = EvalSubTask(
        task_id=task_id,
        target_type=target_type,
        target_id=target_id,
        target_config=target_config,
    )
    db.add(sub_task)
    db.flush()
    return sub_task


def update_sub_task(db: Session, sub_task_id: int, **kwargs) -> Optional[EvalSubTask]:
    """更新子任务"""
    sub_task = get_sub_task(db, sub_task_id)
    if sub_task is None:
        return None
    for key, value in kwargs.items():
        if value is not None:
            setattr(sub_task, key, value)
    db.flush()
    return sub_task
