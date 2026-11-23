"""
评测定时任务服务层
"""
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ...models.eval import EvalSchedule, EvalSuite


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _schedule_to_dict(row: EvalSchedule) -> Dict[str, Any]:
    return {
        "id": row.id,
        "suite_id": row.suite_id,
        "name": row.name,
        "task_config": row.task_config,
        "cron_expression": row.cron_expression,
        "is_active": row.is_active,
        "last_run_at": row.last_run_at,
        "last_task_id": row.last_task_id,
        "next_run_at": row.next_run_at,
        "notify_on_failure": row.notify_on_failure,
        "notify_channels": row.notify_channels,
        "created_by": row.created_by,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _validate_suite(db: Session, suite_id: int) -> EvalSuite:
    suite = db.query(EvalSuite).filter(EvalSuite.id == suite_id).first()
    if not suite:
        raise HTTPException(status_code=404, detail="评测集不存在")
    return suite


_CRON_FIELDS = ("minute", "hour", "day", "month", "weekday")

# 字段范围：(name, min, max)
_CRON_RANGES = [
    ("分", 0, 59),
    ("时", 0, 23),
    ("日", 1, 31),
    ("月", 1, 12),
    ("周", 0, 7),  # 0/7 都表示周日
]


def _split_cron_field(field: str, lo: int, hi: int) -> list[int]:
    """解析单个 cron 字段，返回所有匹配值的列表（简化版，不处理 / 步长）。"""
    values: set[int] = set()
    for part in field.split(","):
        part = part.strip()
        if part == "*":
            values.update(range(lo, hi + 1))
        elif "-" in part:
            a, b = part.split("-", 1)
            values.update(range(int(a), int(b) + 1))
        else:
            values.add(int(part))
    return sorted(v for v in values if lo <= v <= hi)


class _SimpleCron:
    """简易 cron 解析器，不依赖外部库。支持 5 段 cron 表达式的 next_run 计算。"""

    def __init__(self, expression: str):
        parts = expression.strip().split()
        if len(parts) != 5:
            raise ValueError("Cron 表达式需要 5 段")
        self._parts = parts
        self._ranges = [_CRON_RANGES[i][1:] for i in range(5)]

    def next_after(self, dt: datetime) -> datetime:
        """返回 dt 之后的下一个触发时间（精确到分钟）。"""
        dt = dt.replace(second=0, microsecond=0) + timedelta(minutes=1)
        # 向前搜索，最多尝试 366 天（覆盖一整年）
        for _ in range(366 * 24 * 60):
            if self._matches(dt):
                return dt
            dt = dt + timedelta(minutes=1)
        raise ValueError("无法在一年内找到下一个 cron 匹配时间")

    def _matches(self, dt: datetime) -> bool:
        fields = [dt.minute, dt.hour, dt.day, dt.month, (dt.weekday() + 1) % 7]  # cron weekday: 0=Sun
        for i, (field_val, (lo, hi)) in enumerate(zip(fields, self._ranges)):
            part = self._parts[i]
            if not self._field_matches(part, field_val, lo, hi):
                return False
        return True

    @staticmethod
    def _field_matches(part: str, value: int, lo: int, hi: int) -> bool:
        for alt in part.split(","):
            alt = alt.strip()
            # 步长 */N 或 0/N
            if "/" in alt:
                base, step = alt.split("/", 1)
                step = int(step)
                if base == "*":
                    start = lo
                else:
                    start = int(base)
                for v in range(start, hi + 1, step):
                    if v == value:
                        return True
                continue
            if alt == "*":
                return True
            if "-" in alt:
                a, b = alt.split("-", 1)
                if lo <= value <= hi and int(a) <= value <= int(b):
                    return True
            else:
                try:
                    if int(alt) == value:
                        return True
                except ValueError:
                    pass
        return False


def _validate_cron(expression: str) -> None:
    """校验 cron 表达式格式（5 段）并验证有效性。"""
    parts = expression.strip().split()
    if len(parts) != 5:
        raise HTTPException(
            status_code=400,
            detail="Cron 表达式格式错误，需要 5 段（分 时 日 月 周）",
        )
    try:
        _SimpleCron(expression).next_after(datetime.now())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Cron 表达式无效: {e}")


def compute_next_run(cron_expression: str, from_time: datetime = None) -> datetime:
    """根据 cron 表达式计算下一次运行时间。"""
    if from_time is None:
        from_time = datetime.now(timezone.utc).replace(tzinfo=None)
    return _SimpleCron(cron_expression).next_after(from_time)


# ---------------------------------------------------------------------------
# service functions
# ---------------------------------------------------------------------------

def list_schedules_service(
    db: Session,
    space_id: int,
    suite_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """列出定时任务。"""
    suite_ids_q = db.query(EvalSuite.id).filter(EvalSuite.space_id == space_id)
    q = db.query(EvalSchedule).filter(EvalSchedule.suite_id.in_(suite_ids_q))

    if suite_id is not None:
        q = q.filter(EvalSchedule.suite_id == suite_id)

    rows = q.order_by(EvalSchedule.created_at.desc()).all()
    return [_schedule_to_dict(r) for r in rows]


def create_schedule_service(
    db: Session, space_id: int, user_id: int, data: Dict[str, Any],
) -> Dict[str, Any]:
    """创建定时任务。"""
    suite_id = data.get("suite_id")
    if not suite_id:
        raise HTTPException(status_code=400, detail="评测集ID不能为空")

    suite = _validate_suite(db, suite_id)
    if suite.space_id != space_id:
        raise HTTPException(status_code=403, detail="无权访问该评测集")

    name = (data.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="定时任务名称不能为空")

    cron_expression = (data.get("cron_expression") or "").strip()
    if not cron_expression:
        raise HTTPException(status_code=400, detail="Cron 表达式不能为空")
    _validate_cron(cron_expression)

    next_run = compute_next_run(cron_expression)
    row = EvalSchedule(
        suite_id=suite_id,
        name=name,
        task_config=data.get("task_config"),
        cron_expression=cron_expression,
        is_active=data.get("is_active", True),
        next_run_at=next_run,
        notify_on_failure=data.get("notify_on_failure", True),
        notify_channels=data.get("notify_channels"),
        created_by=user_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _schedule_to_dict(row)


def update_schedule_service(
    db: Session, schedule_id: int, space_id: int, data: Dict[str, Any],
) -> Dict[str, Any]:
    """更新定时任务。"""
    row = db.query(EvalSchedule).filter(EvalSchedule.id == schedule_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="定时任务不存在")

    # 验证 space 权限
    suite = db.query(EvalSuite).filter(EvalSuite.id == row.suite_id).first()
    if not suite or suite.space_id != space_id:
        raise HTTPException(status_code=403, detail="无权访问该定时任务")

    if "name" in data:
        name = (data["name"] or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="定时任务名称不能为空")
        row.name = name

    if "task_config" in data:
        row.task_config = data["task_config"]

    if "cron_expression" in data:
        cron_expr = (data["cron_expression"] or "").strip()
        if not cron_expr:
            raise HTTPException(status_code=400, detail="Cron 表达式不能为空")
        _validate_cron(cron_expr)
        row.cron_expression = cron_expr
        row.next_run_at = compute_next_run(cron_expr)

    if "is_active" in data:
        row.is_active = bool(data["is_active"])

    if "notify_on_failure" in data:
        row.notify_on_failure = bool(data["notify_on_failure"])

    if "notify_channels" in data:
        row.notify_channels = data["notify_channels"]

    db.commit()
    db.refresh(row)
    return _schedule_to_dict(row)


def delete_schedule_service(db: Session, schedule_id: int, space_id: int) -> Dict[str, Any]:
    """删除定时任务。"""
    row = db.query(EvalSchedule).filter(EvalSchedule.id == schedule_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="定时任务不存在")

    # 验证 space 权限
    suite = db.query(EvalSuite).filter(EvalSuite.id == row.suite_id).first()
    if not suite or suite.space_id != space_id:
        raise HTTPException(status_code=403, detail="无权访问该定时任务")

    db.delete(row)
    db.commit()
    return {"ok": True}


def trigger_schedule_service(db: Session, schedule_id: int, space_id: int) -> Dict[str, Any]:
    """手动触发定时任务。"""
    row = db.query(EvalSchedule).filter(EvalSchedule.id == schedule_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="定时任务不存在")

    # 获取评测集的 space_id 并验证权限
    suite = db.query(EvalSuite).filter(EvalSuite.id == row.suite_id).first()
    if not suite:
        raise HTTPException(status_code=404, detail="关联评测集不存在")
    if suite.space_id != space_id:
        raise HTTPException(status_code=403, detail="无权访问该定时任务")

    from .eval_task_service import create_task_service, start_task_service

    task_config = row.task_config or {}
    task_data = {
        "suite_id": row.suite_id,
        "name": f"{row.name} - 手动触发",
        **task_config,
    }

    task = create_task_service(db, space_id=suite.space_id, user_id=row.created_by, data=task_data)
    task_id = task.get("id")
    if task_id:
        start_task_service(db, task_id=task_id, space_id=suite.space_id)

    now = datetime.now()
    row.last_run_at = now
    row.last_task_id = task_id
    row.next_run_at = compute_next_run(row.cron_expression, now)
    db.commit()

    return {"ok": True, "task_id": task_id, "message": "已创建并启动任务"}
