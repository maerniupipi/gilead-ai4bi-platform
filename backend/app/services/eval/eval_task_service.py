"""
评测任务服务层
"""
import asyncio
import datetime as _dt
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from ...core.database import SessionLocal
from ...core.execution import read_database
from ...models.eval import (
    EvalTask,
    EvalSubTask,
    EvalRun,
    EvalCase,
    EvalSuite,
    EvalComparison,
    EvalCaseGroundTruth,
    EvalOutputTemplate,
    EvalSuiteTag,
)
from .eval_comparison_service import run_comparison
from .eval_target_adapter import call_target

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# DB-driven config helpers
# ---------------------------------------------------------------------------

def _get_config_int(db: Session, key: str, default: int, minimum: int = 1) -> int:
    """从 eval_configs 表读取整数配置。"""
    from ...repositories.eval.eval_config_repo import get_value
    try:
        return max(minimum, int(get_value(db, key, str(default))))
    except (ValueError, TypeError):
        return default
    except Exception as e:  # noqa: BLE001
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
        logger.debug("读取评测配置失败，使用默认值: key=%s default=%s error=%s", key, default, e)
        return default


def _env_int(name: str, default: int, minimum: int = 1) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return max(minimum, int(raw))
    except ValueError:
        logger.warning("环境变量 %s=%r 不是整数，使用默认值 %s", name, raw, default)
        return default


# 跟踪正在运行的后台任务，用于 pause/cancel 时取消
_running_tasks: Dict[int, asyncio.Task] = {}
_task_loop = None
_cancel_events: Dict[int, asyncio.Event] = {}
_judge_executor = ThreadPoolExecutor(
    max_workers=_env_int("EVAL_JUDGE_THREAD_WORKERS", 3),
    thread_name_prefix="eval-judge",
)


def dispatch_task(task_id):
    from ...worker import background_mode
    if background_mode() == "external":
        return

    def spawn():
        if task_id in _running_tasks:
            return
        bg_task = asyncio.create_task(execute_task_background(task_id))
        _running_tasks[task_id] = bg_task
        bg_task.add_done_callback(lambda done: _running_tasks.pop(task_id, None)
                                 if _running_tasks.get(task_id) is done else None)

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        if _task_loop is None:
            raise HTTPException(503, "评测任务执行器尚未启动")
        _task_loop.call_soon_threadsafe(spawn)
    else:
        spawn()


async def _run_judge_blocking(fn, *args, **kwargs):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_judge_executor, partial(fn, *args, **kwargs))


def shutdown_judge_executor() -> None:
    _judge_executor.shutdown(wait=False, cancel_futures=True)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _task_to_dict(
    row: EvalTask,
    sub_tasks: Optional[List[Dict[str, Any]]] = None,
    *,
    db: Optional[Session] = None,
    include_estimates: bool = False,
) -> Dict[str, Any]:
    total = row.total_cases or 0
    completed = row.completed_cases or 0
    passed = row.passed_cases or 0
    failed = row.failed_cases or 0
    progress = round(completed / max(total, 1) * 100, 1)
    pass_rate = round(passed / max(total, 1) * 100, 1)

    d: Dict[str, Any] = {
        "id": row.id,
        "suite_id": row.suite_id,
        "name": row.name,
        "description": row.description,
        "output_template_id": row.output_template_id,
        "case_filter": row.case_filter,
        "exec_params": row.exec_params,
        "status": row.status,
        "total_cases": total,
        "completed_cases": completed,
        "passed_cases": passed,
        "failed_cases": failed,
        "error_cases": row.error_cases or 0,
        "progress": progress,
        "pass_rate": pass_rate,
        # 前端兼容别名
        "total": total,
        "passed": passed,
        "failed": failed,
        "scheduled_at": row.scheduled_at,
        "started_at": row.started_at,
        "completed_at": row.completed_at,
        "created_by": row.created_by,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }

    # 阶段标记（从 exec_params 读取）
    exec_params = row.exec_params if isinstance(row.exec_params, dict) else {}
    phase = exec_params.get("phase") if row.status == "running" else None
    d["phase"] = phase

    # 预估时间（仅 running 状态，且有已完成的 run）
    if include_estimates and row.status == "running" and completed > 3 and db is not None:
        target_ms, judge_ms = _calc_avg_durations(db, row.id)
        if target_ms > 0:
            concurrency = _get_config_int(db, "eval_concurrency", 3)
            remaining = total - completed
            # Phase 1 剩余：remaining 个 case 的 target 调用
            d["estimated_target_seconds"] = int(target_ms / 1000 * remaining / concurrency)
            # Phase 2 剩余：remaining 个 case 的 judge（如果当前在 target 阶段）
            # 如果已经在 judge 阶段，remaining 需要减去已 judge 的数量
            if phase == "target":
                d["estimated_judge_seconds"] = int(judge_ms * remaining / concurrency)
            elif phase == "judge":
                # judge 阶段：remaining 是还没 judge 的
                d["estimated_judge_seconds"] = int(judge_ms * remaining / concurrency)
                d["estimated_target_seconds"] = 0
            else:
                d["estimated_judge_seconds"] = int(judge_ms * remaining / concurrency)
        else:
            d["estimated_target_seconds"] = None
            d["estimated_judge_seconds"] = None
    else:
        d["estimated_target_seconds"] = None
        d["estimated_judge_seconds"] = None

    if sub_tasks is not None:
        d["sub_tasks"] = sub_tasks
    return d


def _calc_avg_durations(db: Session, task_id: int) -> tuple:
    """计算任务已完成 run 的平均 target 调用时间和平均 judge 时间。返回 (avg_target_ms, avg_judge_seconds)。"""
    from sqlalchemy import cast, Float

    sub_task_ids = db.query(EvalSubTask.id).filter(EvalSubTask.task_id == task_id).subquery()

    # 平均 target 调用时间（从 run 的 execution_time_ms）
    avg_target = (
        db.query(func.avg(EvalRun.execution_time_ms))
        .filter(
            EvalRun.sub_task_id.in_(sub_task_ids),
            EvalRun.status == "success",
            EvalRun.execution_time_ms.isnot(None),
        )
        .scalar()
    )

    # 平均 judge 时间：comparison.created_at - run.completed_at
    # 两阶段模式下 run 是并发的，不能用 run 间隔估算
    elapsed = (
        func.extract("epoch", EvalComparison.created_at - EvalRun.completed_at)
        if db.get_bind().dialect.name == "postgresql"
        else func.timestampdiff(text("SECOND"), EvalRun.completed_at, EvalComparison.created_at)
    )
    avg_judge_raw = (
        db.query(func.avg(cast(elapsed, Float)))
        .join(EvalRun, EvalRun.id == EvalComparison.run_id)
        .filter(
            EvalRun.sub_task_id.in_(sub_task_ids),
            EvalRun.status == "success",
            EvalRun.completed_at.isnot(None),
        )
        .scalar()
    )

    avg_judge = float(avg_judge_raw) if avg_judge_raw and avg_judge_raw > 0 else 30.0

    return (avg_target or 0), avg_judge


def _sub_task_to_dict(row: EvalSubTask) -> Dict[str, Any]:
    return {
        "id": row.id,
        "task_id": row.task_id,
        "target_type": row.target_type,
        "target_id": row.target_id,
        "target_config": row.target_config,
        "status": row.status,
        "total_cases": row.total_cases,
        "completed_cases": row.completed_cases,
        "passed_cases": row.passed_cases,
        "failed_cases": row.failed_cases,
        "error_cases": row.error_cases,
        "started_at": row.started_at,
        "completed_at": row.completed_at,
        "error_message": row.error_message,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _get_sub_tasks(db: Session, task_id: int) -> List[Dict[str, Any]]:
    rows = (
        db.query(EvalSubTask)
        .filter(EvalSubTask.task_id == task_id)
        .order_by(EvalSubTask.id.asc())
        .all()
    )
    return [_sub_task_to_dict(r) for r in rows]


def _validate_suite(db: Session, suite_id: int) -> EvalSuite:
    suite = db.query(EvalSuite).filter(EvalSuite.id == suite_id).first()
    if not suite:
        raise HTTPException(status_code=404, detail="评测集不存在")
    return suite


def _get_cases_for_task(db: Session, task: EvalTask) -> List[EvalCase]:
    """根据任务的 case_filter 获取用例列表。"""
    q = db.query(EvalCase).filter(
        EvalCase.suite_id == task.suite_id,
        EvalCase.is_active.is_(True),
    )

    case_filter = task.case_filter or {}

    if "difficulty" in case_filter and case_filter["difficulty"]:
        q = q.filter(EvalCase.difficulty == case_filter["difficulty"])

    if "category" in case_filter and case_filter["category"]:
        q = q.filter(EvalCase.category == case_filter["category"])

    if "case_ids" in case_filter and case_filter["case_ids"]:
        q = q.filter(EvalCase.id.in_(case_filter["case_ids"]))

    return q.order_by(EvalCase.sort_order.asc(), EvalCase.id.asc()).all()


def _update_task_progress(db: Session, task_id: int) -> None:
    """从子任务汇总更新任务进度。"""
    task = db.query(EvalTask).filter(EvalTask.id == task_id).first()
    if not task:
        return

    agg = (
        db.query(
            func.sum(EvalSubTask.total_cases),
            func.sum(EvalSubTask.completed_cases),
            func.sum(EvalSubTask.passed_cases),
            func.sum(EvalSubTask.failed_cases),
            func.sum(EvalSubTask.error_cases),
        )
        .filter(EvalSubTask.task_id == task_id)
        .first()
    )

    task.total_cases = int(agg[0] or 0)
    task.completed_cases = int(agg[1] or 0)
    task.passed_cases = int(agg[2] or 0)
    task.failed_cases = int(agg[3] or 0)
    task.error_cases = int(agg[4] or 0)


def _coerce_timeout_seconds(value: Any, default: int = 180) -> int:
    try:
        timeout = int(value)
    except (TypeError, ValueError):
        timeout = default
    return max(30, min(timeout, 600))


def _run_llm_comparison_in_thread(
    run_id: int,
    task_id: Optional[int] = None,
    timeout_seconds: Optional[int] = None,
) -> None:
    """Run mandatory LLM comparison in a worker thread using its own DB session."""
    db = SessionLocal()
    try:
        run = db.query(EvalRun).filter(EvalRun.id == run_id).first()
        if not run or run.status not in ("running", "success"):
            return

        db.query(EvalComparison).filter(EvalComparison.run_id == run_id).delete(
            synchronize_session=False
        )
        db.commit()
        judge_retry = _get_config_int(db, "eval_judge_retry", 2)
        run_comparison(
            db,
            run_id,
            force_llm_judge=True,
            timeout_seconds=timeout_seconds,
            retry_count=judge_retry,
        )

        run = db.query(EvalRun).filter(EvalRun.id == run_id).first()
        if not run:
            return
        run.status = "success"
        st = db.query(EvalSubTask).filter(EvalSubTask.id == run.sub_task_id).first()
        if st:
            _recalculate_sub_task_stats(db, st)
            _update_task_progress(db, st.task_id)
            db.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning("LLM comparison failed: run=%s task=%s error=%s", run_id, task_id, e)
        try:
            exists = db.query(EvalComparison.id).filter(EvalComparison.run_id == run_id).first()
            if not exists:
                db.add(EvalComparison(
                    run_id=run_id,
                    ground_truth_id=0,
                    comparison_method="llm_judge",
                    is_correct=None,
                    score=None,
                    comparison_detail={"error": f"LLM 评判异常: {e}"},
                    llm_judge_raw_output=str(e),
                ))
            run = db.query(EvalRun).filter(EvalRun.id == run_id).first()
            if run and run.status == "running":
                run.status = "success"
            db.commit()
        except Exception as inner_e:  # noqa: BLE001
            logger.warning("LLM comparison error handler failed: run=%s error=%s", run_id, inner_e)
    finally:
        db.close()


def _schedule_missing_comparisons_for_task(db: Session, task_id: int) -> int:
    """Compensate successful runs that have no comparison record yet."""
    rows = (
        db.query(EvalRun.id)
        .join(EvalSubTask, EvalSubTask.id == EvalRun.sub_task_id)
        .outerjoin(EvalComparison, EvalComparison.run_id == EvalRun.id)
        .filter(
            EvalSubTask.task_id == task_id,
            EvalRun.status == "success",
            EvalComparison.id.is_(None),
        )
        .all()
    )
    scheduled = 0
    for (run_id,) in rows:
        _run_llm_comparison_in_thread(run_id, task_id)
        scheduled += 1
    return scheduled


# ---------------------------------------------------------------------------
# service functions
# ---------------------------------------------------------------------------

def list_tasks_service(
    db: Session,
    space_id: int,
    suite_id: Optional[int] = None,
    status: Optional[str] = None,
    keyword: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
) -> Dict[str, Any]:
    """列出任务。"""
    # 通过 suite 的 space_id 过滤
    suite_ids_q = db.query(EvalSuite.id).filter(EvalSuite.space_id == space_id)
    q = db.query(EvalTask).filter(EvalTask.suite_id.in_(suite_ids_q))

    if suite_id is not None:
        q = q.filter(EvalTask.suite_id == suite_id)

    if status:
        q = q.filter(EvalTask.status == status)

    if keyword:
        q = q.filter(EvalTask.name.ilike(f"%{keyword.strip()}%"))

    total = q.count()
    rows = q.order_by(EvalTask.created_at.desc()).offset(skip).limit(limit).all()

    items = [_task_to_dict(r, db=db) for r in rows]
    return {"items": items, "total": total, "skip": skip, "limit": limit}


def get_task_service(db: Session, task_id: int, space_id: int) -> Dict[str, Any]:
    """获取任务详情（含子任务）。"""
    task = db.query(EvalTask).filter(EvalTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    # 验证空间权限
    suite = db.query(EvalSuite).filter(EvalSuite.id == task.suite_id).first()
    if not suite or suite.space_id != space_id:
        raise HTTPException(status_code=403, detail="无权访问该任务")

    sub_tasks = _get_sub_tasks(db, task_id)
    return _task_to_dict(task, sub_tasks=sub_tasks, db=db)


def create_task_service(
    db: Session, space_id: int, user_id: int, data: Dict[str, Any],
) -> Dict[str, Any]:
    """创建任务。"""
    suite_id = data.get("suite_id")
    if not suite_id:
        raise HTTPException(status_code=400, detail="评测集ID不能为空")

    suite = _validate_suite(db, suite_id)
    if suite.space_id != space_id:
        raise HTTPException(status_code=403, detail="无权访问该评测集")

    name = (data.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="任务名称不能为空")

    # 创建任务
    scheduled_at = data.get("scheduled_at")
    initial_status = "scheduled" if scheduled_at else "draft"
    task = EvalTask(
        suite_id=suite_id,
        name=name,
        description=data.get("description"),
        output_template_id=data.get("comparison_template_id") or data.get("output_template_id"),
        case_filter=data.get("case_filter"),
        exec_params=data.get("exec_params"),
        scheduled_at=scheduled_at,
        status=initial_status,
        created_by=user_id,
    )
    db.add(task)
    db.flush()

    # 创建子任务（每个 target 一个子任务）
    sub_tasks_data = data.get("sub_tasks", [])
    if not sub_tasks_data:
        # 默认使用评测集的默认配置创建一个子任务
        sub_tasks_data = [{
            "target_type": suite.default_task_source_type,
            "target_id": suite.default_task_source_id,
            "target_config": suite.default_task_source_config or {},
        }]

    for st_data in sub_tasks_data:
        sub_task = EvalSubTask(
            task_id=task.id,
            target_type=st_data.get("target_type", "agent"),
            target_id=st_data.get("target_id"),
            target_config=st_data.get("target_config"),
            status="pending",
        )
        db.add(sub_task)

    db.commit()
    db.refresh(task)
    return get_task_service(db, task.id, space_id)


def _prepare_task_runs(db: Session, task_id: int) -> None:
    """清理旧运行记录、重置子任务状态、创建新 run 记录。供 start_task_service 和 scheduler 共用。"""
    task = db.query(EvalTask).filter(EvalTask.id == task_id).first()
    if not task:
        return

    sub_tasks = db.query(EvalSubTask).filter(EvalSubTask.task_id == task_id).all()
    if not sub_tasks:
        return

    cases = _get_cases_for_task(db, task)
    if not cases:
        return

    # 清理旧运行记录
    sub_task_ids = [st.id for st in sub_tasks]
    if sub_task_ids:
        old_run_ids = [
            r[0] for r in db.query(EvalRun.id).filter(EvalRun.sub_task_id.in_(sub_task_ids)).all()
        ]
        if old_run_ids:
            db.query(EvalComparison).filter(EvalComparison.run_id.in_(old_run_ids)).delete(
                synchronize_session=False
            )
            db.query(EvalRun).filter(EvalRun.id.in_(old_run_ids)).delete(
                synchronize_session=False
            )

    # 重置子任务状态
    for st in sub_tasks:
        st.status = "pending"
        st.total_cases = len(cases)
        st.completed_cases = 0
        st.passed_cases = 0
        st.failed_cases = 0
        st.error_cases = 0
        st.error_message = None
        st.started_at = None
        st.completed_at = None

    # 更新任务状态
    task.status = "running"
    task.total_cases = len(cases) * len(sub_tasks)
    task.completed_cases = 0
    task.passed_cases = 0
    task.failed_cases = 0
    task.error_cases = 0
    task.started_at = _dt.datetime.utcnow()
    task.completed_at = None

    # 创建 run 记录
    for st in sub_tasks:
        for case in cases:
            db.add(EvalRun(sub_task_id=st.id, case_id=case.id, status="pending"))

    db.commit()


def start_task_service(
    db: Session, task_id: int, space_id: int,
) -> Dict[str, Any]:
    """启动任务。"""
    task = db.query(EvalTask).filter(EvalTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    suite = db.query(EvalSuite).filter(EvalSuite.id == task.suite_id).first()
    if not suite or suite.space_id != space_id:
        raise HTTPException(status_code=403, detail="无权访问该任务")

    if task.status not in ("draft", "scheduled", "failed", "cancelled", "paused"):
        raise HTTPException(
            status_code=400,
            detail=f"任务状态为 {task.status}，无法启动",
        )

    sub_tasks = db.query(EvalSubTask).filter(EvalSubTask.task_id == task_id).all()
    if not sub_tasks:
        raise HTTPException(status_code=400, detail="任务没有子任务")

    cases = _get_cases_for_task(db, task)
    if not cases:
        raise HTTPException(status_code=400, detail="没有匹配的测试用例")

    _prepare_task_runs(db, task_id)
    db.refresh(task)

    # 启动后台执行，并跟踪任务引用
    dispatch_task(task_id)

    return get_task_service(db, task_id, space_id)


def pause_task_service(
    db: Session, task_id: int, space_id: int,
) -> Dict[str, Any]:
    """暂停任务。"""
    task = db.query(EvalTask).filter(EvalTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    suite = db.query(EvalSuite).filter(EvalSuite.id == task.suite_id).first()
    if not suite or suite.space_id != space_id:
        raise HTTPException(status_code=403, detail="无权访问该任务")

    if task.status != "running":
        raise HTTPException(status_code=400, detail="只有运行中的任务可以暂停")

    task.status = "paused"
    db.commit()
    db.refresh(task)

    # 通知后台协程停止 + 取消后台任务
    cancel_ev = _cancel_events.get(task_id)
    if cancel_ev:
        cancel_ev.set()
    bg_task = _running_tasks.pop(task_id, None)
    if bg_task and not bg_task.done():
        bg_task.cancel()

    return get_task_service(db, task_id, space_id)


def resume_task_service(
    db: Session, task_id: int, space_id: int,
) -> Dict[str, Any]:
    """恢复任务。"""
    task = db.query(EvalTask).filter(EvalTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    suite = db.query(EvalSuite).filter(EvalSuite.id == task.suite_id).first()
    if not suite or suite.space_id != space_id:
        raise HTTPException(status_code=403, detail="无权访问该任务")

    if task.status != "paused":
        raise HTTPException(status_code=400, detail="只有暂停的任务可以恢复")

    task.status = "running"
    db.commit()
    db.refresh(task)

    # 先取消可能残留的旧后台任务，再启动新的
    old_bg = _running_tasks.pop(task_id, None)
    if old_bg and not old_bg.done():
        old_bg.cancel()

    dispatch_task(task_id)

    return get_task_service(db, task_id, space_id)


def cancel_task_service(
    db: Session, task_id: int, space_id: int,
) -> Dict[str, Any]:
    """取消任务。"""
    task = db.query(EvalTask).filter(EvalTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    suite = db.query(EvalSuite).filter(EvalSuite.id == task.suite_id).first()
    if not suite or suite.space_id != space_id:
        raise HTTPException(status_code=403, detail="无权访问该任务")

    if task.status in ("completed", "cancelled"):
        raise HTTPException(status_code=400, detail=f"任务状态为 {task.status}，无法取消")

    task.status = "cancelled"
    task.completed_at = _dt.datetime.utcnow()

    # 更新子任务状态
    db.query(EvalSubTask).filter(
        EvalSubTask.task_id == task_id,
        EvalSubTask.status.in_(["pending", "running"]),
    ).update({"status": "cancelled"}, synchronize_session=False)

    db.commit()
    db.refresh(task)

    # 通知后台协程停止 + 取消后台任务
    cancel_ev = _cancel_events.get(task_id)
    if cancel_ev:
        cancel_ev.set()
    bg_task = _running_tasks.pop(task_id, None)
    if bg_task and not bg_task.done():
        bg_task.cancel()

    return get_task_service(db, task_id, space_id)


def retry_failed_service(
    db: Session, task_id: int, space_id: int,
) -> Dict[str, Any]:
    """重试失败的用例。"""
    task = db.query(EvalTask).filter(EvalTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    suite = db.query(EvalSuite).filter(EvalSuite.id == task.suite_id).first()
    if not suite or suite.space_id != space_id:
        raise HTTPException(status_code=403, detail="无权访问该任务")

    if task.status not in ("completed", "failed"):
        raise HTTPException(status_code=400, detail="只有已完成或失败的任务可以重试")

    # 重置失败的 runs
    failed_runs = (
        db.query(EvalRun)
        .join(EvalSubTask, EvalSubTask.id == EvalRun.sub_task_id)
        .filter(EvalSubTask.task_id == task_id, EvalRun.status == "error")
        .all()
    )

    if not failed_runs:
        raise HTTPException(status_code=400, detail="没有失败的用例需要重试")

    for run in failed_runs:
        run.status = "pending"
        run.raw_response = None
        run.parsed_response = None
        run.error_message = None
        run.execution_time_ms = None
        run.attempt = (run.attempt or 1) + 1
        run.started_at = None
        run.completed_at = None

    # 删除失败 run 的对比记录
    failed_run_ids = [r.id for r in failed_runs]
    db.query(EvalComparison).filter(EvalComparison.run_id.in_(failed_run_ids)).delete(
        synchronize_session=False
    )

    # 更新子任务计数
    sub_tasks = db.query(EvalSubTask).filter(EvalSubTask.task_id == task_id).all()
    for st in sub_tasks:
        st_failed = sum(1 for r in failed_runs if r.sub_task_id == st.id)
        if st_failed > 0:
            st.status = "pending"
            st.completed_cases -= st_failed
            st.error_cases -= st_failed

    task.status = "running"

    db.commit()
    db.refresh(task)

    old_bg = _running_tasks.pop(task_id, None)
    if old_bg and not old_bg.done():
        old_bg.cancel()

    dispatch_task(task_id)

    return get_task_service(db, task_id, space_id)


def update_task_service(
    db: Session, task_id: int, space_id: int, data: Dict[str, Any],
) -> Dict[str, Any]:
    """更新任务（名称、描述、定时设置）。"""
    task = db.query(EvalTask).filter(EvalTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    suite = db.query(EvalSuite).filter(EvalSuite.id == task.suite_id).first()
    if not suite or suite.space_id != space_id:
        raise HTTPException(status_code=403, detail="无权访问该任务")

    if task.status == "running":
        raise HTTPException(status_code=400, detail="运行中的任务不能编辑")

    if "name" in data and data["name"] is not None:
        task.name = data["name"]
    if "description" in data:
        task.description = data["description"]

    # 定时任务设置
    if "scheduled_at" in data:
        if data["scheduled_at"]:
            task.scheduled_at = data["scheduled_at"]
            task.status = "scheduled"
        else:
            # 取消定时：清除 scheduled_at，状态回退到 draft
            task.scheduled_at = None
            if task.status == "scheduled":
                task.status = "draft"

    db.commit()
    db.refresh(task)
    return get_task_service(db, task_id, space_id)


def delete_task_service(
    db: Session, task_id: int, space_id: int,
) -> Dict[str, Any]:
    """删除任务（运行中的任务不能删除）。"""
    task = db.query(EvalTask).filter(EvalTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    suite = db.query(EvalSuite).filter(EvalSuite.id == task.suite_id).first()
    if not suite or suite.space_id != space_id:
        raise HTTPException(status_code=403, detail="无权访问该任务")

    if task.status == "running":
        raise HTTPException(status_code=400, detail="运行中的任务不能删除")

    # 删除关联数据
    sub_task_ids = [
        st[0]
        for st in db.query(EvalSubTask.id).filter(EvalSubTask.task_id == task_id).all()
    ]
    if sub_task_ids:
        run_ids = [
            r[0]
            for r in db.query(EvalRun.id).filter(EvalRun.sub_task_id.in_(sub_task_ids)).all()
        ]
        if run_ids:
            db.query(EvalComparison).filter(EvalComparison.run_id.in_(run_ids)).delete(
                synchronize_session=False
            )
            db.query(EvalRun).filter(EvalRun.id.in_(run_ids)).delete(synchronize_session=False)
        db.query(EvalSubTask).filter(EvalSubTask.id.in_(sub_task_ids)).delete(
            synchronize_session=False
        )

    db.delete(task)
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# background execution engine — two-phase concurrent
# ---------------------------------------------------------------------------


async def execute_task_background(task_id: int, cancel_event: Optional[asyncio.Event] = None) -> None:
    """
    后台执行任务 — 两阶段并发模式。
    Phase 1: 并发调用所有 target（最多 N 个并发）
    Phase 2: 并发执行所有 LLM 评判（最多 N 个并发）

    cancel_event: 外部可设置此 Event 来通知任务停止（避免每个协程查 DB）。
    """
    if cancel_event is None:
        cancel_event = asyncio.Event()
    # 将 event 注册到全局字典，供 pause/cancel 设置
    _cancel_events[task_id] = cancel_event

    db = SessionLocal()
    try:
        task = db.query(EvalTask).filter(EvalTask.id == task_id).first()
        if not task:
            logger.warning("execute_task_background: task %s not found", task_id)
            return

        sub_tasks = (
            db.query(EvalSubTask)
            .filter(EvalSubTask.task_id == task_id, EvalSubTask.status != "cancelled")
            .all()
        )
        if not sub_tasks:
            logger.warning("execute_task_background: no sub_tasks for task %s", task_id)
            return

        cases = _get_cases_for_task(db, task)
        if not cases:
            logger.warning("execute_task_background: no cases for task %s", task_id)
            task.status = "completed"
            task.completed_at = _dt.datetime.utcnow()
            db.commit()
            return

        concurrency = _get_config_int(db, "eval_concurrency", 3)
        sub_task_ids = [st.id for st in sub_tasks]
        case_ids = [case.id for case in cases]

        # 标记子任务为 running
        for st in sub_tasks:
            st.status = "running"
            st.started_at = _dt.datetime.utcnow()
        task.status = "running"
        db.commit()

        # ── Phase 1: 并发调用 target ──
        _set_task_phase(db, task_id, "target")
        logger.info("task %s: Phase 1 starting, %d sub-tasks × %d cases, concurrency=%d",
                     task_id, len(sub_tasks), len(cases), concurrency)

        semaphore = asyncio.Semaphore(concurrency)

        async def _run_target_with_sem(st_id: int, case_id: int):
            async with semaphore:
                if cancel_event.is_set():
                    return
                await _execute_case_target_only(st_id, case_id)

        target_coros = [
            _run_target_with_sem(sub_task_id, case_id)
            for sub_task_id in sub_task_ids
            for case_id in case_ids
        ]
        await asyncio.gather(*target_coros, return_exceptions=True)

        # 检查是否被取消/暂停
        if cancel_event.is_set():
            _finalize_task(db, task_id)
            return

        # ── Phase 2: 并发执行 LLM 评判 ──
        _set_task_phase(db, task_id, "judge")
        logger.info("task %s: Phase 2 starting (LLM judge), concurrency=%d", task_id, concurrency)

        semaphore2 = asyncio.Semaphore(concurrency)

        async def _run_judge_with_sem(st_id: int, case_id: int):
            async with semaphore2:
                if cancel_event.is_set():
                    return
                await _execute_case_judge_only(st_id, case_id)

        judge_coros = [
            _run_judge_with_sem(sub_task_id, case_id)
            for sub_task_id in sub_task_ids
            for case_id in case_ids
        ]
        await asyncio.gather(*judge_coros, return_exceptions=True)

        # ── 汇总并设置最终状态 ──
        _finalize_task(db, task_id)

    except Exception as e:  # noqa: BLE001
        logger.exception("execute_task_background failed: task=%s error=%s", task_id, e)
        try:
            task = db.query(EvalTask).filter(EvalTask.id == task_id).first()
            if task and task.status not in ("cancelled", "completed"):
                task.status = "failed"
                task.completed_at = _dt.datetime.utcnow()
                _clear_task_phase(db, task_id)
                db.commit()
        except Exception:  # noqa: BLE001
            pass
    finally:
        db.close()
        _cancel_events.pop(task_id, None)


def _set_task_phase(db: Session, task_id: int, phase: str) -> None:
    """在 exec_params 中标记当前执行阶段。"""
    task = db.query(EvalTask).filter(EvalTask.id == task_id).first()
    if task:
        params = dict(task.exec_params or {})
        params["phase"] = phase
        task.exec_params = params
        db.commit()


def _clear_task_phase(db: Session, task_id: int) -> None:
    """清除 exec_params 中的阶段标记。"""
    task = db.query(EvalTask).filter(EvalTask.id == task_id).first()
    if task and isinstance(task.exec_params, dict):
        params = dict(task.exec_params)
        params.pop("phase", None)
        task.exec_params = params


async def _is_task_running(task_id: int) -> bool:
    """检查任务是否仍在运行（未被取消/暂停）。兼容旧调用。"""
    event = _cancel_events.get(task_id)
    if event:
        return not event.is_set()
    with SessionLocal() as db:
        return await read_database(db, lambda session: session.query(EvalTask.status).filter(
            EvalTask.id == task_id).scalar() == "running")


def _finalize_task(db: Session, task_id: int) -> None:
    """汇总进度，更新子任务状态，设置最终任务状态。"""
    db.expire_all()
    _update_task_progress(db, task_id)

    # 更新子任务状态
    sub_tasks = db.query(EvalSubTask).filter(EvalSubTask.task_id == task_id).all()
    for st in sub_tasks:
        if st.status == "cancelled":
            continue
        _recalculate_sub_task_stats(db, st)
        st.status = "completed"
        st.completed_at = _dt.datetime.utcnow()

    # 判断最终状态
    task = db.query(EvalTask).filter(EvalTask.id == task_id).first()
    if task:
        if task.status == "cancelled":
            pass  # 已被取消，不覆盖
        elif task.error_cases and task.error_cases > 0:
            if task.completed_cases and task.completed_cases >= task.total_cases:
                task.status = "completed"
            else:
                task.status = "failed"
        elif task.completed_cases and task.completed_cases >= task.total_cases:
            task.status = "completed"
        else:
            task.status = "failed"

        if task.status in ("completed", "failed"):
            task.completed_at = _dt.datetime.utcnow()

        _clear_task_phase(db, task_id)
        db.commit()

    _running_tasks.pop(task_id, None)


async def _execute_case_target_only(sub_task_id: int, case_id: int) -> None:
    """Phase 1: 仅执行 call_target + 保存 run 结果，不执行 LLM 评判。"""
    db = SessionLocal()
    try:
        st = db.query(EvalSubTask).filter(EvalSubTask.id == sub_task_id).first()
        case = db.query(EvalCase).filter(EvalCase.id == case_id).first()
        if not st or not case:
            return
        task = db.query(EvalTask).filter(EvalTask.id == st.task_id).first()
        exec_params = task.exec_params if task and isinstance(task.exec_params, dict) else {}
        timeout_seconds = _coerce_timeout_seconds(exec_params.get("timeout_seconds"))
        target_type = st.target_type
        target_config = dict(st.target_config or {})
        input_prompt = case.input_prompt
        input_variables = case.input_variables

        # 查找 pending 的 run
        run = (
            db.query(EvalRun)
            .filter(
                EvalRun.sub_task_id == sub_task_id,
                EvalRun.case_id == case_id,
                EvalRun.status == "pending",
            )
            .first()
        )
        if not run:
            return

        run.status = "running"
        run.started_at = _dt.datetime.utcnow()
        run_id = run.id
        db.commit()

        # One run invokes its target once; saved retry settings do not resubmit it.
        result = await call_target(
            target_type=target_type, target_config=target_config,
            input_prompt=input_prompt, input_variables=input_variables,
            timeout_seconds=timeout_seconds,
        )

        # 保存运行结果
        run.raw_response = result.get("raw_response")
        run.parsed_response = result.get("parsed_response")
        run.execution_time_ms = result.get("execution_time_ms")
        run.error_message = result.get("error")
        run.completed_at = _dt.datetime.utcnow()
        has_error = bool(result.get("error"))
        run.status = "error" if has_error else "success"
        db.commit()
        _mark_target_finished(db, sub_task_id, has_error)

    except Exception as e:  # noqa: BLE001
        logger.exception("_execute_case_target_only failed: sub_task=%s case=%s error=%s",
                         sub_task_id, case_id, e)
        try:
            run = (
                db.query(EvalRun)
                .filter(EvalRun.sub_task_id == sub_task_id, EvalRun.case_id == case_id)
                .first()
            )
            if run and run.status in ("pending", "running"):
                run.status = "error"
                run.error_message = str(e)[:1000]
                run.completed_at = _dt.datetime.utcnow()
                db.commit()
                _mark_target_finished(db, sub_task_id, True)
        except Exception:  # noqa: BLE001
            pass
    finally:
        db.close()


async def _execute_case_judge_only(sub_task_id: int, case_id: int) -> None:
    """Phase 2: 仅对 success 状态的 run 执行 LLM 评判。"""
    db = SessionLocal()
    try:
        run = (
            db.query(EvalRun)
            .filter(
                EvalRun.sub_task_id == sub_task_id,
                EvalRun.case_id == case_id,
                EvalRun.status == "success",
            )
            .first()
        )
        if not run:
            return  # 跳过非 success 的 run（error 或 pending）

        task = db.query(EvalTask).filter(
            EvalTask.id == db.query(EvalSubTask.task_id).filter(EvalSubTask.id == sub_task_id).scalar_subquery()
        ).first()
        exec_params = task.exec_params if task and isinstance(task.exec_params, dict) else {}
        timeout_seconds = _coerce_timeout_seconds(exec_params.get("timeout_seconds"))
        run_id = run.id
        task_id = task.id if task else None

        db.close()
        db = None

        await _run_judge_blocking(
            _run_llm_comparison_in_thread,
            run_id,
            task_id,
            timeout_seconds,
        )

    except Exception as e:  # noqa: BLE001
        logger.exception("_execute_case_judge_only failed: sub_task=%s case=%s error=%s",
                         sub_task_id, case_id, e)
    finally:
        if db is not None:
            db.close()


def _mark_target_finished(db: Session, sub_task_id: int, has_error: bool) -> None:
    """Target 阶段完成后用原子 SQL 推进进度，避免轮询时进度长时间为 0。"""
    try:
        st = db.query(EvalSubTask).filter(EvalSubTask.id == sub_task_id).first()
        if not st:
            return
        task_id = st.task_id
        sub_values = {
            "completed_cases": func.coalesce(EvalSubTask.completed_cases, 0) + 1,
        }
        task_values = {
            "completed_cases": func.coalesce(EvalTask.completed_cases, 0) + 1,
        }
        if has_error:
            sub_values["error_cases"] = func.coalesce(EvalSubTask.error_cases, 0) + 1
            task_values["error_cases"] = func.coalesce(EvalTask.error_cases, 0) + 1
        db.query(EvalSubTask).filter(EvalSubTask.id == sub_task_id).update(
            sub_values,
            synchronize_session=False,
        )
        db.query(EvalTask).filter(EvalTask.id == task_id).update(
            task_values,
            synchronize_session=False,
        )
        db.commit()
    except Exception as e:  # noqa: BLE001
        db.rollback()
        logger.warning("mark target progress failed: sub_task=%s error=%s", sub_task_id, e)


async def _execute_single_case(sub_task_id: int, case_id: int) -> None:
    """执行单个用例（兼容包装器：target + judge 串行）。用于 retry_failed 等场景。"""
    await _execute_case_target_only(sub_task_id, case_id)
    await _execute_case_judge_only(sub_task_id, case_id)


def _recalculate_sub_task_stats(db: Session, st: EvalSubTask) -> None:
    """从 run 表重新计算子任务统计。"""
    from sqlalchemy import case
    success_expr = case((EvalRun.status == "success", 1), else_=0)
    error_expr = case((EvalRun.status == "error", 1), else_=0)
    agg = (
        db.query(
            func.count(EvalRun.id),
            func.sum(success_expr),
            func.sum(error_expr),
        )
        .filter(EvalRun.sub_task_id == st.id)
        .first()
    )

    total = int(agg[0] or 0)
    success_count = int(agg[1] or 0)
    error_count = int(agg[2] or 0)

    # 通过对比结果计算 passed/failed
    passed = (
        db.query(func.count(func.distinct(EvalComparison.run_id)))
        .join(EvalRun, EvalRun.id == EvalComparison.run_id)
        .filter(
            EvalRun.sub_task_id == st.id,
            EvalComparison.is_correct.is_(True),
        )
        .scalar()
    )
    failed = (
        db.query(func.count(func.distinct(EvalComparison.run_id)))
        .join(EvalRun, EvalRun.id == EvalComparison.run_id)
        .filter(
            EvalRun.sub_task_id == st.id,
            EvalComparison.is_correct.is_(False),
        )
        .scalar()
    )

    st.total_cases = total
    st.completed_cases = success_count + error_count
    st.passed_cases = int(passed or 0)
    st.failed_cases = int(failed or 0)
    st.error_cases = error_count


# ---------------------------------------------------------------------------
# additional helpers referenced by router
# ---------------------------------------------------------------------------

def task_progress_service(task_id: int, space_id: int, request=None):
    """任务进度 SSE 推送。返回 StreamingResponse。"""
    import asyncio
    import json
    import os
    from fastapi import HTTPException
    from fastapi.responses import StreamingResponse

    db = SessionLocal()
    try:
        task = db.query(EvalTask).filter(EvalTask.id == task_id).first()
        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")

        suite = db.query(EvalSuite).filter(EvalSuite.id == task.suite_id).first()
        if not suite or suite.space_id != space_id:
            raise HTTPException(status_code=403, detail="无权访问该任务")
    finally:
        db.close()

    async def _progress_stream():
        interval_seconds = max(1, int(os.getenv("EVAL_PROGRESS_SSE_INTERVAL_SECONDS", "2")))
        max_seconds = max(interval_seconds, int(os.getenv("EVAL_PROGRESS_SSE_MAX_SECONDS", "3600")))
        max_iterations = max(1, max_seconds // interval_seconds)
        iteration = 0
        while iteration < max_iterations:
            iteration += 1
            if request is not None and await request.is_disconnected():
                break
            with SessionLocal() as db2:
                t = await read_database(db2, lambda session: session.get(EvalTask, task_id))
            if not t:
                yield f"data: {json.dumps({'type': 'error', 'message': '任务不存在'})}\n\n"
                break
            exec_p = t.exec_params if isinstance(t.exec_params, dict) else {}
            phase = exec_p.get("phase") if t.status == "running" else None
            data = {
                "type": "progress",
                "task_id": task_id,
                "status": t.status,
                "total": t.total_cases,
                "completed": t.completed_cases,
                "passed": t.passed_cases,
                "failed": t.failed_cases,
                "error": t.error_cases,
                "percentage": round(t.completed_cases / max(t.total_cases, 1) * 100, 1),
                "phase": phase,
            }
            yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
            if t.status in ("completed", "failed", "cancelled", "partial"):
                yield f"data: {json.dumps({'type': 'done', 'status': t.status})}\n\n"
                break
            await asyncio.sleep(interval_seconds)
        # 超时后发送结束信号
        if iteration >= max_iterations:
            yield f"data: {json.dumps({'type': 'done', 'status': 'timeout', 'message': 'SSE 超时'})}\n\n"

    return StreamingResponse(
        _progress_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )


def task_stats_service(db: Session, space_id: int, suite_id: Optional[int] = None) -> dict:
    """获取任务统计概览（按状态分组聚合），用于前端统计卡片。"""
    suite_ids_q = db.query(EvalSuite.id).filter(EvalSuite.space_id == space_id)
    q = db.query(EvalTask.status, func.count(EvalTask.id)).filter(EvalTask.suite_id.in_(suite_ids_q))
    if suite_id is not None:
        q = q.filter(EvalTask.suite_id == suite_id)
    rows = q.group_by(EvalTask.status).all()

    stats = {row[0]: row[1] for row in rows}
    total = sum(stats.values())
    return {
        "total": total,
        "running": stats.get("running", 0),
        "completed": stats.get("completed", 0) + stats.get("success", 0),
        "failed": stats.get("failed", 0),
    }


def list_sub_tasks_service(db: Session, task_id: int, space_id: int) -> list:
    """获取子任务列表。"""
    task = db.query(EvalTask).filter(EvalTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    suite = db.query(EvalSuite).filter(EvalSuite.id == task.suite_id).first()
    if not suite or suite.space_id != space_id:
        raise HTTPException(status_code=403, detail="无权访问该任务")

    subs = db.query(EvalSubTask).filter(EvalSubTask.task_id == task_id).order_by(EvalSubTask.id.asc()).all()
    return [_sub_task_to_dict(s) for s in subs]


def task_summary_service(db: Session, task_id: int, space_id: int) -> dict:
    """获取任务统计概览。"""
    task = db.query(EvalTask).filter(EvalTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    suite = db.query(EvalSuite).filter(EvalSuite.id == task.suite_id).first()
    if not suite or suite.space_id != space_id:
        raise HTTPException(status_code=403, detail="无权访问该任务")

    pass_rate = round(task.passed_cases / max(task.total_cases, 1) * 100, 1)

    # 按子任务汇总
    subs = db.query(EvalSubTask).filter(EvalSubTask.task_id == task_id).all()
    sub_summaries = []
    for s in subs:
        sub_summaries.append({
            "id": s.id,
            "target_type": s.target_type,
            "status": s.status,
            "total": s.total_cases,
            "passed": s.passed_cases,
            "failed": s.failed_cases,
            "error": s.error_cases,
        })

    return {
        "task_id": task_id,
        "name": task.name,
        "status": task.status,
        "total_cases": task.total_cases,
        "passed": task.passed_cases,
        "failed": task.failed_cases,
        "error": task.error_cases,
        "pass_rate": pass_rate,
        "sub_tasks": sub_summaries,
        "started_at": str(task.started_at) if task.started_at else None,
        "completed_at": str(task.completed_at) if task.completed_at else None,
    }


def export_results_service(db: Session, task_id: int, space_id: int) -> dict:
    """导出评测结果（返回 JSON 数据）。"""
    task = db.query(EvalTask).filter(EvalTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    suite = db.query(EvalSuite).filter(EvalSuite.id == task.suite_id).first()
    if not suite or suite.space_id != space_id:
        raise HTTPException(status_code=403, detail="无权访问该任务")

    # 获取所有子任务的运行记录
    subs = db.query(EvalSubTask).filter(EvalSubTask.task_id == task_id).all()
    all_runs = []
    for st in subs:
        runs = db.query(EvalRun).filter(EvalRun.sub_task_id == st.id).order_by(EvalRun.id.asc()).all()
        for r in runs:
            # 获取对比信息
            comp = db.query(EvalComparison).filter(EvalComparison.run_id == r.id).first()
            # 获取用例信息
            case = db.query(EvalCase).filter(EvalCase.id == r.case_id).first()
            all_runs.append({
                "case_id": r.case_id,
                "input_prompt": case.input_prompt if case else "",
                "status": r.status,
                "parsed_response": r.parsed_response,
                "execution_time_ms": r.execution_time_ms,
                "is_correct": comp.is_correct if comp else None,
                "score": float(comp.score) if comp and comp.score is not None else None,
                "comparison_method": comp.comparison_method if comp else None,
                "target_type": st.target_type,
            })

    return {
        "task_id": task_id,
        "task_name": task.name,
        "total": len(all_runs),
        "items": all_runs,
    }


def generate_report_service(db: Session, task_id: int, space_id: int) -> dict:
    """生成评测报告（返回 JSON 格式的报告数据）。"""
    task = db.query(EvalTask).filter(EvalTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    suite = db.query(EvalSuite).filter(EvalSuite.id == task.suite_id).first()
    if not suite or suite.space_id != space_id:
        raise HTTPException(status_code=403, detail="无权访问该任务")

    summary = task_summary_service(db, task_id, space_id)
    export = export_results_service(db, task_id, space_id)

    return {
        "report": {
            "task": summary,
            "data": export["items"],
        }
    }


def archive_failed_cases_service(
    db: Session,
    task_id: int,
    space_id: int,
    user_id: int,
) -> dict:
    """将当前任务失败用例归档为新的评测集。"""
    task = db.query(EvalTask).filter(EvalTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    suite = db.query(EvalSuite).filter(EvalSuite.id == task.suite_id).first()
    if not suite or suite.space_id != space_id:
        raise HTTPException(status_code=403, detail="无权访问该任务")

    sub_task_ids = [r[0] for r in db.query(EvalSubTask.id).filter(EvalSubTask.task_id == task_id).all()]
    if not sub_task_ids:
        raise HTTPException(status_code=400, detail="任务没有子任务")

    latest_run_ids = (
        db.query(func.max(EvalRun.id).label("run_id"))
        .filter(EvalRun.sub_task_id.in_(sub_task_ids))
        .group_by(EvalRun.case_id)
        .subquery()
    )
    failed_runs = (
        db.query(EvalRun)
        .join(latest_run_ids, EvalRun.id == latest_run_ids.c.run_id)
        .outerjoin(EvalComparison, EvalComparison.run_id == EvalRun.id)
        .filter(EvalComparison.is_correct.is_(False))
        .order_by(EvalRun.id.asc())
        .all()
    )
    if not failed_runs:
        raise HTTPException(status_code=400, detail="没有失败用例可归档")

    base_name = f"{suite.name}-失败归档-{_dt.datetime.utcnow().strftime('%Y-%m-%d')}"
    candidate = base_name
    counter = 2
    while db.query(EvalSuite.id).filter(EvalSuite.space_id == space_id, EvalSuite.name == candidate).first():
        candidate = f"{base_name}-{counter}"
        counter += 1

    new_suite = EvalSuite(
        space_id=suite.space_id,
        folder_id=suite.folder_id,
        name=candidate,
        description=f"从任务「{task.name}」归档的失败用例",
        version=suite.version,
        default_task_source_type=suite.default_task_source_type,
        default_task_source_id=suite.default_task_source_id,
        default_task_source_config=suite.default_task_source_config,
        default_comparison_method=suite.default_comparison_method,
        default_comparison_config=suite.default_comparison_config,
        status="draft",
        created_by=user_id,
    )
    db.add(new_suite)
    db.flush()

    for tag in db.query(EvalSuiteTag).filter(EvalSuiteTag.suite_id == suite.id).all():
        db.add(EvalSuiteTag(suite_id=new_suite.id, tag_id=tag.tag_id))

    archived_case_ids = []
    for index, run in enumerate(failed_runs, start=1):
        case = db.query(EvalCase).filter(EvalCase.id == run.case_id).first()
        if not case:
            continue
        new_case = EvalCase(
            suite_id=new_suite.id,
            input_prompt=case.input_prompt,
            input_variables=case.input_variables,
            expected_output_type=case.expected_output_type,
            difficulty=case.difficulty,
            category=case.category,
            remark=case.remark,
            sort_order=index,
            is_active=case.is_active,
        )
        db.add(new_case)
        db.flush()
        archived_case_ids.append(new_case.id)

        gts = db.query(EvalCaseGroundTruth).filter(EvalCaseGroundTruth.case_id == case.id).all()
        for gt in gts:
            db.add(EvalCaseGroundTruth(
                case_id=new_case.id,
                version=gt.version,
                ground_truth=gt.ground_truth,
                ground_truth_type=gt.ground_truth_type,
                comparison_method=gt.comparison_method,
                comparison_config=gt.comparison_config,
                is_active=gt.is_active,
            ))

    for tmpl in db.query(EvalOutputTemplate).filter(EvalOutputTemplate.suite_id == suite.id).all():
        db.add(EvalOutputTemplate(
            suite_id=new_suite.id,
            name=tmpl.name,
            fields=tmpl.fields,
            is_default=tmpl.is_default,
        ))

    db.commit()
    return {
        "ok": True,
        "suite_id": new_suite.id,
        "suite_name": new_suite.name,
        "case_count": len(archived_case_ids),
    }
