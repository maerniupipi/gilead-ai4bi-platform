"""Durable single-table queue; all ownership changes use database CAS updates."""
import re
import time
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from ...models.data_sync import DataSyncEvent, DataSyncRun, DataSyncTask
from .cron import next_run
from .settings import task_definitions, SyncConfig, configuration_status

LEASE_SECONDS = 120
ACTIVE = {"queued", "running"}
STATUSES = ACTIVE | {"succeeded", "failed", "interrupted", "skipped"}


def ensure_tasks(db):
    now = int(time.time())
    definitions = task_definitions()
    for key, config in definitions.items():
        name = str(config.get("name") or key)[:100]
        if db.get(DataSyncTask, key) is None:
            try:
                with db.begin_nested():
                    db.add(DataSyncTask(id=key, name=name, schedule_enabled=False,
                        cron_expression="0 2 * * *", timezone="Asia/Shanghai", created_at=now, updated_at=now))
                    db.flush()
            except IntegrityError:
                pass  # Another worker seeded this task.
    for task in db.query(DataSyncTask).all():
        if task.id not in definitions:
            task.schedule_enabled, task.next_run_at = False, None
    db.commit()


def run_view(run):
    fields = ("id", "task_id", "task_name", "trigger_type", "requested_by", "status", "stage", "page_no",
              "fetched_rows", "loaded_rows", "total_rows", "message", "error", "created_at", "started_at", "finished_at")
    result = {key: getattr(run, key) for key in fields}
    # Source totalCount is unreliable. Fetching progress has no invented percentage.
    result["progress_percent"] = 100 if run.status == "succeeded" else None
    result["elapsed_seconds"] = max(0, (run.finished_at or int(time.time())) - run.started_at) if run.started_at else 0
    return result


def task_view(db, task):
    config = configuration_status(task.id)
    return {key: getattr(task, key) for key in ("id", "name", "schedule_enabled", "cron_expression", "timezone",
        "next_run_at", "active_run_id")} | {"configuration": config,
        "last_run": run_view(last) if task.last_run_id and (last := db.get(DataSyncRun, task.last_run_id)) else None}


def list_tasks(db):
    ensure_tasks(db)
    return [task_view(db, db.get(DataSyncTask, key)) for key in task_definitions()]


def get_task(db, task_id):
    task = db.get(DataSyncTask, task_id)
    if task is None:
        raise HTTPException(404, "同步任务不存在")
    return task


def update_task(db, task_id, body):
    task = get_task(db, task_id)
    try:
        upcoming = body.next_after()
        if body.schedule_enabled:
            SyncConfig.from_env(task_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None
    task.name, task.schedule_enabled = body.name, body.schedule_enabled
    task.cron_expression, task.timezone = body.cron_expression, body.timezone
    task.next_run_at = upcoming if body.schedule_enabled else None
    task.updated_at = int(time.time())
    db.commit()
    return task_view(db, task)


def enqueue(db, task_id, *, requested_by=None, scheduled_for=None, now=None):
    now = int(time.time()) if now is None else now
    if scheduled_for is not None and scheduled_for > now:
        return None
    task = get_task(db, task_id)
    scheduled = scheduled_for is not None
    if not scheduled:
        try:
            SyncConfig.from_env(task_id)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None
    run_id = str(uuid4())
    conditions = [DataSyncTask.id == task_id, DataSyncTask.active_run_id.is_(None)]
    values = {"active_run_id": run_id, "last_run_id": run_id, "updated_at": now}
    if scheduled:
        conditions += [DataSyncTask.schedule_enabled.is_(True), DataSyncTask.next_run_at == scheduled_for,
                       DataSyncTask.cron_expression == task.cron_expression, DataSyncTask.timezone == task.timezone]
        values["next_run_at"] = next_run(task.cron_expression, task.timezone, now)
    claimed = db.execute(update(DataSyncTask).where(*conditions).values(**values))
    if claimed.rowcount != 1:
        if not scheduled:
            db.rollback()
            raise HTTPException(409, "该表已有排队或执行中的同步任务")
        # Advance a busy schedule exactly once; do not build an overlapping backlog.
        skipped = db.execute(update(DataSyncTask).where(DataSyncTask.id == task_id,
            DataSyncTask.schedule_enabled.is_(True), DataSyncTask.next_run_at == scheduled_for,
            DataSyncTask.cron_expression == task.cron_expression, DataSyncTask.timezone == task.timezone,
            DataSyncTask.active_run_id.is_not(None)).values(next_run_at=values["next_run_at"], updated_at=now))
        if skipped.rowcount != 1:
            db.rollback()
            return None
        run = DataSyncRun(id=run_id, task_id=task_id, task_name=task.name, trigger_type="scheduled",
            status="skipped", stage="skipped", message="前次任务仍在执行，本次计划已跳过", created_at=now, finished_at=now)
    else:
        run = DataSyncRun(id=run_id, task_id=task_id, task_name=task.name,
            trigger_type="scheduled" if scheduled else "manual", requested_by=requested_by,
            status="queued", stage="queued", message="已进入同步队列", created_at=now)
    db.add(run)
    db.commit()
    db.refresh(run)
    return run_view(run)


def enqueue_due(factory, now=None):
    now = int(time.time()) if now is None else now
    with factory() as db:
        # Keep immutable due-time snapshots: commits expire ORM objects, and a
        # different dispatcher may already have advanced a later task's schedule.
        due = db.query(DataSyncTask.id, DataSyncTask.next_run_at).filter(
            DataSyncTask.schedule_enabled.is_(True), DataSyncTask.next_run_at <= now).all()
        for task_id, due_at in due:
            enqueue(db, task_id, scheduled_for=due_at, now=now)


def claim_next(factory, owner, now=None):
    now = int(time.time()) if now is None else now
    with factory() as db:
        candidates = db.query(DataSyncRun.id).filter_by(status="queued").order_by(DataSyncRun.created_at, DataSyncRun.id).limit(10).all()
        for (run_id,) in candidates:
            result = db.execute(update(DataSyncRun).where(DataSyncRun.id == run_id, DataSyncRun.status == "queued")
                .values(status="running", stage="preparing", worker_id=owner, started_at=now, lease_until=now + LEASE_SECONDS,
                        message="工作进程已领取任务"))
            db.commit()
            if result.rowcount == 1:
                return run_id
    return None


def renew_lease(factory, run_id, owner, now=None):
    now = int(time.time()) if now is None else now
    with factory() as db:
        result = db.execute(update(DataSyncRun).where(DataSyncRun.id == run_id, DataSyncRun.worker_id == owner,
            DataSyncRun.status == "running", DataSyncRun.lease_until >= now).values(lease_until=now + LEASE_SECONDS))
        db.commit()
        return result.rowcount == 1


def _event(db, run, message, now):
    db.add(DataSyncEvent(run_id=run.id, stage=run.stage, message=message, page_no=run.page_no,
        fetched_rows=run.fetched_rows, loaded_rows=run.loaded_rows, created_at=now))


def record_progress(factory, run_id, owner, **values):
    now = int(time.time())
    allowed = {key: value for key, value in values.items() if key in {
        "stage", "page_no", "fetched_rows", "loaded_rows", "total_rows", "message"}}
    with factory() as db:
        updated = db.execute(update(DataSyncRun).where(DataSyncRun.id == run_id, DataSyncRun.status == "running",
            DataSyncRun.worker_id == owner, DataSyncRun.lease_until >= now).values(**allowed, lease_until=now + LEASE_SECONDS))
        if updated.rowcount != 1:
            db.rollback()
            raise RuntimeError("执行租约已失效，已停止后续同步步骤")
        run = db.get(DataSyncRun, run_id)
        _event(db, run, values.get("message", "同步进行中"), now)
        db.commit()


def finish_run(factory, run_id, owner, status, *, count=None, error="", now=None):
    now = int(time.time()) if now is None else now
    with factory() as db:
        values = {"status": status, "stage": status, "finished_at": now, "lease_until": None, "error": error or None,
                  "message": "同步完成，正式表已提交" if status == "succeeded" else error}
        if count is not None:
            values.update(total_rows=count, fetched_rows=count, loaded_rows=count)
        updated = db.execute(update(DataSyncRun).where(DataSyncRun.id == run_id, DataSyncRun.status == "running",
            DataSyncRun.worker_id == owner, DataSyncRun.lease_until >= now).values(**values))
        if updated.rowcount != 1:
            db.rollback()
            return False
        run = db.get(DataSyncRun, run_id)
        _event(db, run, run.message, now)
        db.execute(update(DataSyncTask).where(DataSyncTask.id == run.task_id, DataSyncTask.active_run_id == run_id)
                   .values(active_run_id=None, updated_at=now))
        db.commit()
        return True


def expire_runs(factory, now=None):
    now = int(time.time()) if now is None else now
    with factory() as db:
        runs = db.query(DataSyncRun).filter(DataSyncRun.status == "running", DataSyncRun.lease_until < now).all()
        for run in runs:
            message = "工作进程中断或租约超时；未自动重试。请核实目标表与运行锁后手动执行。"
            result = db.execute(update(DataSyncRun).where(DataSyncRun.id == run.id, DataSyncRun.status == "running",
                DataSyncRun.lease_until < now).values(status="interrupted", stage="interrupted", finished_at=now,
                                                     lease_until=None, error=message, message=message))
            if result.rowcount == 1:
                _event(db, run, message, now)
                db.execute(update(DataSyncTask).where(DataSyncTask.id == run.task_id, DataSyncTask.active_run_id == run.id)
                           .values(active_run_id=None, updated_at=now))
        db.commit()


def list_runs(db, task_id=None, status=None, offset=0, limit=20):
    query = db.query(DataSyncRun)
    if task_id:
        query = query.filter_by(task_id=task_id)
    if status:
        if status not in STATUSES:
            raise HTTPException(400, "运行状态无效")
        query = query.filter_by(status=status)
    total = query.count()
    items = query.order_by(DataSyncRun.created_at.desc(), DataSyncRun.id.desc()).offset(offset).limit(limit).all()
    return {"total": total, "items": [run_view(run) for run in items]}


def run_detail(db, run_id, after_event_id=0, limit=100):
    run = db.get(DataSyncRun, run_id)
    if run is None:
        raise HTTPException(404, "同步记录不存在")
    events = db.query(DataSyncEvent).filter(DataSyncEvent.run_id == run_id, DataSyncEvent.id > after_event_id)
    items = events.order_by(DataSyncEvent.id).limit(limit + 1).all()
    return {"run": run_view(run), "events": [{key: getattr(event, key) for key in (
        "id", "stage", "message", "page_no", "fetched_rows", "loaded_rows", "created_at")} for event in items[:limit]],
        "has_more_events": len(items) > limit}


def safe_error(exc, config=None):
    if not isinstance(exc, (RuntimeError, ValueError)):
        return f"同步失败（{type(exc).__name__}），请检查目标表、网络和临时目录权限"
    message = str(exc)
    if config:
        from sqlalchemy.engine import make_url
        secrets = [*config.headers.values(), config.database_url, make_url(config.database_url).password]
        from ...core.observability import snapshot
        # Private request parameters may include tokens as well as header values.
        def collect(value):
            if isinstance(value, dict):
                for key, item in value.items():
                    if isinstance(item, str) and snapshot({key: item})[key] == "***":
                        secrets.append(item)
                    elif isinstance(item, (dict, list)):
                        collect(item)
            elif isinstance(value, list):
                for item in value:
                    collect(item)
        collect(config.request_params)
        for secret in secrets:
            if secret:
                message = message.replace(secret, "[已隐藏]")
    message = re.sub(r"value=.+? incompatible with", "value=[已隐藏] incompatible with", message)
    return message[:2000]
