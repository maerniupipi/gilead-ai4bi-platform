"""
Redis 连接（智能体工作流等）。

实验室流水线追踪日志已迁移到 MySQL（autobi_lab_traces 表），
trace_get / trace_set 现通过 SQLAlchemy 直接读写数据库。
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Optional

from .env_loader import load_app_environment

load_app_environment()

logger = logging.getLogger(__name__)

try:
    import redis
except ImportError:  # pragma: no cover
    redis = None  # type: ignore

_client: Optional[Any] = None


def _is_loopback_redis_host(host: str) -> bool:
    h = (host or "").strip().lower()
    return h in ("127.0.0.1", "localhost", "::1")


def get_redis() -> Optional[Any]:
    """返回单例 Redis 客户端；未配置 HOST 或依赖缺失时返回 None。"""
    global _client
    host = (os.getenv("REDIS_HOST") or "").strip()
    if not host:
        return None
    if redis is None:
        logger.warning("redis 包未安装，无法连接 Redis")
        return None
    if _client is None:
        port = int(os.getenv("REDIS_PORT", "6379"))
        username = (os.getenv("REDIS_USERNAME") or "").strip() or None
        password = (os.getenv("REDIS_PASSWORD") or "").strip() or None
        if _is_loopback_redis_host(host) and (os.getenv("REDIS_USE_AUTH_ON_LOCAL") or "").strip() not in (
            "1",
            "true",
            "yes",
        ):
            username = None
            password = None
        _client = redis.Redis(
            host=host,
            port=port,
            username=username,
            password=password,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
    return _client


# ---------------------------------------------------------------------------
# 实验室流水线追踪：已从 Redis 迁移到 MySQL (autobi_lab_traces)
# ---------------------------------------------------------------------------


def trace_get(trace_id: str) -> Optional[dict[str, Any]]:
    """从 MySQL 读取实验室追踪记录。"""
    from ..core.database import SessionLocal
    from ..models.autobi_lab_trace import AutobiLabTrace

    db = SessionLocal()
    try:
        row = db.query(AutobiLabTrace).filter(AutobiLabTrace.trace_id == trace_id).first()
        if not row:
            return None
        return {
            "trace_id": row.trace_id,
            "project_id": row.project_id,
            "project_name": row.project_name,
            "user_message": row.user_message,
            "knowledge_base_id": row.knowledge_base_id,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            "steps": row.steps,
        }
    except Exception as e:
        logger.exception("MySQL GET lab trace 失败: %s", e)
        raise
    finally:
        db.close()


def trace_set(trace_id: str, payload: dict[str, Any]) -> None:
    """写入/更新实验室追踪记录到 MySQL（upsert）。"""
    from ..services.chatbi.diagnostics import record_trace
    states = [step.get('status') for step in payload.get('steps', [])]
    status = 'error' if 'error' in states or 'failed' in states else 'done' if states and all(s in {'done','success','succeeded','skipped'} for s in states) else 'running'
    record_trace(trace_id, {'project_id':payload.get('project_id'),'status':status,
                           'elapsed_ms':sum(step.get('duration_ms') or 0 for step in payload.get('steps',[]))}, kind='lab')
    from ..core.database import SessionLocal
    from ..models.autobi_lab_trace import AutobiLabTrace
    from ..core.database import trace_upsert

    steps = payload.get("steps") or []
    step_count = len(steps)

    db = SessionLocal()
    try:
        values = dict(
            trace_id=trace_id,
            project_id=str(payload.get("project_id", "")),
            project_name=payload.get("project_name"),
            user_message=payload.get("user_message", ""),
            knowledge_base_id=payload.get("knowledge_base_id"),
            steps=steps,
            created_at=payload.get("created_at", 0),
            updated_at=payload.get("updated_at", 0),
        )
        stmt = trace_upsert(db, AutobiLabTrace, values, ('steps', 'updated_at', 'project_name'))
        db.execute(stmt)
        db.commit()
        logger.info(
            "autobi lab trace 已写入 MySQL | trace_id=%s | steps=%s",
            trace_id,
            step_count,
        )
    except Exception as e:
        db.rollback()
        logger.exception("MySQL SET lab trace 失败: %s", e)
        raise
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 智能体工作流：撤销栈（最多 10 步），TTL 默认 1 小时
# ---------------------------------------------------------------------------
def agent_workflow_history_ttl_seconds() -> int:
    raw = (os.getenv("AGENT_WORKFLOW_HISTORY_TTL_SECONDS") or "3600").strip()
    if raw == "0":
        return 3600
    try:
        return max(60, int(raw))
    except ValueError:
        return 3600


def workflow_history_storage_key(app_id: int, version_id: int) -> str:
    return f"agent:wf:undo:{app_id}:{version_id}"


_memory_workflow_undo: dict[str, str] = {}


def workflow_undo_get(app_id: int, version_id: int) -> Optional[dict[str, Any]]:
    """读取 Redis 中的撤销栈 { states: [...], index: int }；无则 None。"""
    key = workflow_history_storage_key(app_id, version_id)
    r = get_redis()
    if r is not None:
        try:
            raw = r.get(key)
        except Exception as e:
            logger.exception("Redis GET workflow undo 失败: %s", e)
            raise
        if not raw:
            return None
        return json.loads(raw)
    raw = _memory_workflow_undo.get(key)
    if not raw:
        return None
    return json.loads(raw)


def workflow_undo_set(app_id: int, version_id: int, payload: dict[str, Any]) -> None:
    """写入撤销栈并刷新 TTL。"""
    key = workflow_history_storage_key(app_id, version_id)
    body = json.dumps(payload, ensure_ascii=False)
    ttl = agent_workflow_history_ttl_seconds()
    r = get_redis()
    if r is not None:
        try:
            r.setex(key, ttl, body)
        except Exception as e:
            logger.exception("Redis SET workflow undo 失败: %s", e)
            raise
        logger.debug("agent workflow undo 已写入 Redis | key=%s | ttl_sec=%s", key, ttl)
        return
    _memory_workflow_undo[key] = body
    logger.debug("agent workflow undo 已写入进程内存 | key=%s", key)


# ---------------------------------------------------------------------------
# 智能体工作流：单次执行 trace（不落 MySQL）
# ---------------------------------------------------------------------------
def agent_run_trace_ttl_seconds() -> int:
    raw = (os.getenv("AGENT_RUN_TRACE_TTL_SECONDS") or "604800").strip()
    if raw == "0":
        return 604800
    try:
        return max(60, int(raw))
    except ValueError:
        return 604800


def agent_run_trace_key(run_id: str) -> str:
    return f"agent:run:{run_id}"


_memory_agent_runs: dict[str, str] = {}


def agent_run_trace_get(run_id: str) -> Optional[dict[str, Any]]:
    key = agent_run_trace_key(run_id)
    r = get_redis()
    if r is not None:
        try:
            raw = r.get(key)
        except Exception as e:
            logger.exception("Redis GET agent run trace 失败: %s", e)
            raise
        if not raw:
            return None
        return json.loads(raw)
    raw = _memory_agent_runs.get(key)
    if not raw:
        return None
    return json.loads(raw)


def agent_run_trace_set(run_id: str, payload: dict[str, Any]) -> None:
    key = agent_run_trace_key(run_id)
    body = json.dumps(payload, ensure_ascii=False)
    ttl = agent_run_trace_ttl_seconds()
    r = get_redis()
    if r is not None:
        try:
            r.setex(key, ttl, body)
        except Exception as e:
            logger.exception("Redis SET agent run trace 失败: %s", e)
            raise
        return
    _memory_agent_runs[key] = body
