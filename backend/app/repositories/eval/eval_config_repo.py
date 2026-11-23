"""评测配置数据访问层"""
import time
from typing import Optional, List, Dict

from sqlalchemy.orm import Session

from ...models.eval.eval_config import EvalConfig

# 简单内存缓存，避免每次执行都查 DB
_cache: Dict[str, tuple] = {}  # key -> (value, expire_ts)
_CACHE_TTL = 60  # 秒


def get_value(db: Session, key: str, default: str = "") -> str:
    """读取配置值，带内存缓存。"""
    now = time.time()
    cached = _cache.get(key)
    if cached and cached[1] > now:
        return cached[0]

    row = db.query(EvalConfig.value).filter(EvalConfig.key == key).first()
    val = row[0] if row else default
    _cache[key] = (val, now + _CACHE_TTL)
    return val


def set_value(db: Session, key: str, value: str, description: str = None) -> EvalConfig:
    """更新或创建配置。"""
    row = db.query(EvalConfig).filter(EvalConfig.key == key).first()
    if row:
        row.value = value
        if description is not None:
            row.description = description
    else:
        row = EvalConfig(key=key, value=value, description=description)
        db.add(row)
    db.flush()
    _cache.pop(key, None)
    return row


def list_all(db: Session) -> List[EvalConfig]:
    """列出所有配置。"""
    return db.query(EvalConfig).order_by(EvalConfig.key).all()


def seed_defaults(db: Session) -> None:
    """首次启动时写入默认配置。"""
    defaults = [
        ("eval_concurrency", "3", "评测任务并发数"),
        ("eval_target_timeout", "180", "单个目标调用超时(秒)"),
        ("eval_target_retry", "1", "目标调用重试次数"),
        ("eval_judge_retry", "2", "LLM评判重试次数"),
    ]
    for key, value, desc in defaults:
        exists = db.query(EvalConfig.id).filter(EvalConfig.key == key).first()
        if not exists:
            db.add(EvalConfig(key=key, value=value, description=desc))
    db.commit()
