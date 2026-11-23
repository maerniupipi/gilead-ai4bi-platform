"""
评测调度服务：启动时恢复运行中任务、定时检查到期任务
"""
import asyncio
import logging
from datetime import datetime

from ...core.database import SessionLocal

logger = logging.getLogger(__name__)


async def recover_running_tasks():
    """启动时恢复因进程重启而中断的运行中评测任务。"""
    from ...models.eval.eval_task import EvalTask
    from ...models.eval.eval_run import EvalRun
    from ...models.eval.eval_sub_task import EvalSubTask
    from .eval_task_service import execute_task_background, _running_tasks

    db = SessionLocal()
    try:
        running_tasks = db.query(EvalTask).filter(EvalTask.status == "running").all()
        if not running_tasks:
            return
        for task in running_tasks:
            try:
                sub_task_ids = [
                    st.id for st in
                    db.query(EvalSubTask.id).filter(EvalSubTask.task_id == task.id).all()
                ]
                if sub_task_ids:
                    db.query(EvalRun).filter(
                        EvalRun.sub_task_id.in_(sub_task_ids),
                        EvalRun.status == "running",
                    ).update({"status": "pending"}, synchronize_session=False)
                db.commit()

                bg_task = asyncio.create_task(execute_task_background(task.id))
                _running_tasks[task.id] = bg_task
                bg_task.add_done_callback(lambda _t, tid=task.id: _running_tasks.pop(tid, None))
                logger.info("recover_running_tasks: re-spawned task #%s", task.id)
            except Exception as e:
                logger.warning("recover_running_tasks: failed task #%s: %s", task.id, e)
    except Exception:
        logger.exception("recover_running_tasks error")
    finally:
        db.close()


async def _start_task_async(task_id: int, space_id: int) -> None:
    """在事件循环中启动任务：DB 操作 + asyncio.create_task。"""
    from .eval_task_service import (
        execute_task_background, _running_tasks, _prepare_task_runs,
    )

    db = SessionLocal()
    try:
        _prepare_task_runs(db, task_id)

        bg_task = asyncio.create_task(execute_task_background(task_id))
        _running_tasks[task_id] = bg_task
        bg_task.add_done_callback(lambda _t: _running_tasks.pop(task_id, None))
        logger.info("_start_task_async: spawned task #%s", task_id)

    except Exception as e:
        logger.warning("_start_task_async: failed task #%s: %s", task_id, e)
    finally:
        db.close()


def run_due_schedules():
    """检查并触发到期的定时任务。"""
    db = SessionLocal()
    try:
        from ...models.eval import EvalSchedule, EvalSuite
        from .eval_schedule_service import trigger_schedule_service, compute_next_run

        now = datetime.now()
        due_schedules = (
            db.query(EvalSchedule)
            .filter(
                EvalSchedule.is_active == True,  # noqa: E712
                EvalSchedule.next_run_at <= now,
            )
            .all()
        )
        for sched in due_schedules:
            try:
                suite = db.query(EvalSuite).filter(EvalSuite.id == sched.suite_id).first()
                if not suite:
                    continue
                trigger_schedule_service(db, sched.id, space_id=suite.space_id)
                logger.info("eval_scheduler: triggered schedule #%s", sched.id)
            except Exception as e:
                logger.warning("eval_scheduler: failed schedule #%s: %s", sched.id, e)
                try:
                    sched.next_run_at = compute_next_run(sched.cron_expression)
                    db.commit()
                except Exception:
                    db.rollback()

        # 检查一次性定时任务（使用 _start_task_async 避免在同步上下文中调用 asyncio.create_task）
        from ...models.eval import EvalTask
        import asyncio

        due_tasks = (
            db.query(EvalTask)
            .filter(
                EvalTask.status == "scheduled",
                EvalTask.scheduled_at <= now,
            )
            .all()
        )
        for task in due_tasks:
            try:
                suite = db.query(EvalSuite).filter(EvalSuite.id == task.suite_id).first()
                space_id = suite.space_id if suite else 0
                # 在事件循环中异步启动
                asyncio.ensure_future(_start_task_async(task.id, space_id))
                logger.info("auto-started scheduled task #%s", task.id)
            except Exception as e:
                logger.warning("failed to start scheduled task #%s: %s", task.id, e)
    except Exception:
        logger.exception("run_due_schedules error")
    finally:
        db.close()


async def eval_scheduler_loop():
    """后台任务：每 60 秒检查一次是否有到期的定时评测任务。"""
    while True:
        try:
            await asyncio.sleep(60)
            run_due_schedules()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("eval_scheduler_loop error")
