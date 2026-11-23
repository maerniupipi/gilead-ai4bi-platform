"""评测定时任务数据访问层"""
from typing import List, Optional

from sqlalchemy.orm import Session

from ...models.eval import EvalSchedule, EvalSuite


def list_schedules(db: Session, space_id: int, suite_id: int = None) -> List[EvalSchedule]:
    """列出空间下的定时任务"""
    q = (
        db.query(EvalSchedule)
        .join(EvalSuite, EvalSuite.id == EvalSchedule.suite_id)
        .filter(EvalSuite.space_id == space_id)
    )
    if suite_id is not None:
        q = q.filter(EvalSchedule.suite_id == suite_id)
    return q.order_by(EvalSchedule.id.desc()).all()


def get_schedule(db: Session, schedule_id: int, space_id: int = None) -> Optional[EvalSchedule]:
    """获取单个定时任务"""
    q = db.query(EvalSchedule).filter(EvalSchedule.id == schedule_id)
    if space_id is not None:
        q = q.join(EvalSuite, EvalSuite.id == EvalSchedule.suite_id).filter(
            EvalSuite.space_id == space_id
        )
    return q.first()


def create_schedule(db: Session, **kwargs) -> EvalSchedule:
    """创建定时任务"""
    schedule = EvalSchedule(**kwargs)
    db.add(schedule)
    db.flush()
    return schedule


def update_schedule(db: Session, schedule_id: int, **kwargs) -> Optional[EvalSchedule]:
    """更新定时任务"""
    schedule = db.query(EvalSchedule).filter(EvalSchedule.id == schedule_id).first()
    if schedule is None:
        return None
    for key, value in kwargs.items():
        if value is not None:
            setattr(schedule, key, value)
    db.flush()
    return schedule


def delete_schedule(db: Session, schedule_id: int) -> bool:
    """删除定时任务"""
    schedule = db.query(EvalSchedule).filter(EvalSchedule.id == schedule_id).first()
    if schedule is None:
        return False
    db.delete(schedule)
    db.flush()
    return True
