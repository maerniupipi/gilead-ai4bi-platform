"""评测运行记录数据访问层"""
from typing import List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from ...models.eval import EvalRun, EvalSubTask


def list_runs(
    db: Session,
    sub_task_id: int,
    status: str = None,
    skip: int = 0,
    limit: int = 50,
) -> Tuple[List[EvalRun], int]:
    """列出子任务下的运行记录，返回 (列表, 总数)"""
    q = db.query(EvalRun).filter(EvalRun.sub_task_id == sub_task_id)
    if status is not None:
        q = q.filter(EvalRun.status == status)
    total = q.count()
    items = (
        q.order_by(EvalRun.id.asc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return items, total


def get_run(db: Session, run_id: int) -> Optional[EvalRun]:
    """获取单个运行记录"""
    return db.query(EvalRun).filter(EvalRun.id == run_id).first()


def create_run(db: Session, sub_task_id: int, case_id: int) -> EvalRun:
    """创建运行记录"""
    run = EvalRun(sub_task_id=sub_task_id, case_id=case_id)
    db.add(run)
    db.flush()
    return run


def update_run(db: Session, run_id: int, **kwargs) -> Optional[EvalRun]:
    """更新运行记录"""
    run = get_run(db, run_id)
    if run is None:
        return None
    for key, value in kwargs.items():
        if value is not None:
            setattr(run, key, value)
    db.flush()
    return run


def list_runs_by_task(
    db: Session,
    task_id: int,
    status: str = None,
    skip: int = 0,
    limit: int = 50,
) -> Tuple[List[EvalRun], int]:
    """通过子任务关联列出任务下的运行记录，返回 (列表, 总数)"""
    q = (
        db.query(EvalRun)
        .join(EvalSubTask, EvalSubTask.id == EvalRun.sub_task_id)
        .filter(EvalSubTask.task_id == task_id)
    )
    if status is not None:
        q = q.filter(EvalRun.status == status)
    total = q.count()
    items = (
        q.order_by(EvalRun.id.asc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return items, total


def update_run_manual(
    db: Session,
    run_id: int,
    is_correct: bool,
    note: str = None,
) -> Optional[EvalRun]:
    """人工标注运行结果（存储到 parsed_response 和 status）"""
    run = get_run(db, run_id)
    if run is None:
        return None
    run.status = "manual_reviewed"
    run.parsed_response = {
        **(run.parsed_response or {}),
        "manual_is_correct": is_correct,
        "manual_note": note,
    }
    db.flush()
    return run
