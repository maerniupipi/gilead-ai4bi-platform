"""评测统计服务"""
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from ...models.eval import (
    EvalTask, EvalSubTask, EvalRun, EvalComparison, EvalSuite,
)

logger = logging.getLogger(__name__)


def get_task_statistics_service(db: Session, task_id: int) -> Dict[str, Any]:
    """获取单个任务的统计数据。"""
    task = db.query(EvalTask).filter(EvalTask.id == task_id).first()
    if not task:
        return {"error": "任务不存在"}

    # 子任务统计
    sub_tasks = db.query(EvalSubTask).filter(EvalSubTask.task_id == task_id).all()
    sub_task_ids = [st.id for st in sub_tasks]

    if not sub_task_ids:
        return {
            "task_id": task_id,
            "total_cases": task.total_cases,
            "completed_cases": task.completed_cases,
            "passed_cases": task.passed_cases,
            "failed_cases": task.failed_cases,
            "error_cases": task.error_cases,
            "pass_rate": round(task.passed_cases / task.completed_cases * 100, 2) if task.completed_cases else 0,
            "avg_execution_time_ms": 0,
            "comparison_breakdown": {},
        }

    # 运行记录统计
    run_stats = db.query(
        func.count(EvalRun.id).label("total"),
        func.sum(func.IF(EvalRun.status == "success", 1, 0)).label("success"),
        func.sum(func.IF(EvalRun.status == "error", 1, 0)).label("error"),
        func.avg(EvalRun.execution_time_ms).label("avg_time"),
    ).filter(EvalRun.sub_task_id.in_(sub_task_ids)).first()

    # 对比结果统计
    run_ids = [r.id for r in db.query(EvalRun.id).filter(EvalRun.sub_task_id.in_(sub_task_ids)).all()]
    comparison_stats = {}
    if run_ids:
        comp_rows = db.query(
            EvalComparison.comparison_method,
            func.count(EvalComparison.id).label("total"),
            func.sum(func.IF(EvalComparison.is_correct == True, 1, 0)).label("passed"),
            func.avg(EvalComparison.score).label("avg_score"),
        ).filter(EvalComparison.run_id.in_(run_ids)).group_by(EvalComparison.comparison_method).all()

        for row in comp_rows:
            comparison_stats[row.comparison_method] = {
                "total": row.total,
                "passed": int(row.passed or 0),
                "pass_rate": round(int(row.passed or 0) / row.total * 100, 2) if row.total else 0,
                "avg_score": round(float(row.avg_score or 0), 4),
            }

    total = run_stats.total or 0
    completed = int(run_stats.success or 0) + int(run_stats.error or 0)

    return {
        "task_id": task_id,
        "total_cases": task.total_cases,
        "completed_cases": task.completed_cases,
        "passed_cases": task.passed_cases,
        "failed_cases": task.failed_cases,
        "error_cases": task.error_cases,
        "pass_rate": round(task.passed_cases / task.completed_cases * 100, 2) if task.completed_cases else 0,
        "avg_execution_time_ms": round(float(run_stats.avg_time or 0)),
        "comparison_breakdown": comparison_stats,
    }


def get_suite_statistics_service(db: Session, suite_id: int) -> Dict[str, Any]:
    """获取评测集的整体统计数据。"""
    suite = db.query(EvalSuite).filter(EvalSuite.id == suite_id).first()
    if not suite:
        return {"error": "评测集不存在"}

    # 所有任务
    tasks = db.query(EvalTask).filter(EvalTask.suite_id == suite_id).all()
    task_ids = [t.id for t in tasks]

    if not task_ids:
        return {
            "suite_id": suite_id,
            "total_tasks": 0,
            "total_cases": 0,
            "completed_cases": 0,
            "passed_cases": 0,
            "failed_cases": 0,
            "pass_rate": 0,
        }

    # 汇总任务级统计
    total_cases = sum(t.total_cases for t in tasks)
    completed_cases = sum(t.completed_cases for t in tasks)
    passed_cases = sum(t.passed_cases for t in tasks)
    failed_cases = sum(t.failed_cases for t in tasks)
    error_cases = sum(t.error_cases for t in tasks)

    return {
        "suite_id": suite_id,
        "total_tasks": len(tasks),
        "total_cases": total_cases,
        "completed_cases": completed_cases,
        "passed_cases": passed_cases,
        "failed_cases": failed_cases,
        "error_cases": error_cases,
        "pass_rate": round(passed_cases / completed_cases * 100, 2) if completed_cases else 0,
    }


def get_suite_trend_service(db: Session, suite_id: int, limit: int = 10) -> List[Dict[str, Any]]:
    """获取评测集最近 N 次任务的趋势数据。"""
    tasks = (
        db.query(EvalTask)
        .filter(EvalTask.suite_id == suite_id, EvalTask.status == "completed")
        .order_by(EvalTask.completed_at.desc())
        .limit(limit)
        .all()
    )

    trend = []
    for t in reversed(tasks):
        pass_rate = round(t.passed_cases / t.completed_cases * 100, 2) if t.completed_cases else 0
        trend.append({
            "task_id": t.id,
            "task_name": t.name,
            "completed_at": str(t.completed_at) if t.completed_at else None,
            "total_cases": t.total_cases,
            "passed_cases": t.passed_cases,
            "failed_cases": t.failed_cases,
            "pass_rate": pass_rate,
        })

    return trend
