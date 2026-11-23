"""工作流运行追踪：MySQL 持久化读写。"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, desc, or_
from ...core.database import trace_upsert
from sqlalchemy.orm import Session

from ...core.database import SessionLocal
from ...models.agent_workflow_trace import AgentWorkflowTrace

logger = logging.getLogger(__name__)


def save_workflow_trace(trace_id: str, payload: Dict[str, Any]) -> None:
    """写入/更新工作流追踪记录到 MySQL（upsert）。"""
    from ..chatbi.diagnostics import record_trace
    record_trace(trace_id, payload)
    steps = payload.get("steps") or []
    nodes = payload.get("nodes")
    edges = payload.get("edges")
    now_ms = int(datetime.utcnow().timestamp() * 1000)

    db = SessionLocal()
    try:
        values = dict(
            trace_id=trace_id,
            run_id=payload.get("run_id", ""),
            app_id=payload.get("app_id", 0),
            version_id=payload.get("version_id"),
            app_name=payload.get("app_name"),
            parent_trace_id=payload.get("parent_trace_id"),
            status=payload.get("status", "running"),
            steps=steps,
            nodes=nodes,
            edges=edges,
            output=payload.get("output"),
            error=payload.get("error"),
            elapsed_ms=payload.get("elapsed_ms", 0),
            created_at=payload.get("created_at", now_ms),
            updated_at=now_ms,
        )
        stmt = trace_upsert(db, AgentWorkflowTrace, values, ('status', 'steps', 'output', 'error', 'elapsed_ms', 'updated_at'))
        db.execute(stmt)
        db.commit()
        logger.info(
            "workflow trace 已写入 MySQL | trace_id=%s | status=%s | steps=%d",
            trace_id,
            payload.get("status"),
            len(steps),
        )
    except Exception as e:
        db.rollback()
        logger.exception("MySQL SET workflow trace 失败: %s", e)
        raise
    finally:
        db.close()


def get_workflow_trace(trace_id: str) -> Optional[Dict[str, Any]]:
    """按 trace_id 查询工作流追踪记录。"""
    db = SessionLocal()
    try:
        row = db.query(AgentWorkflowTrace).filter(AgentWorkflowTrace.trace_id == trace_id).first()
        if not row:
            return None
        return {
            "trace_id": row.trace_id,
            "run_id": row.run_id,
            "app_id": row.app_id,
            "version_id": row.version_id,
            "app_name": row.app_name,
            "parent_trace_id": row.parent_trace_id,
            "status": row.status,
            "steps": row.steps,
            "nodes": row.nodes,
            "edges": row.edges,
            "output": row.output,
            "error": row.error,
            "elapsed_ms": row.elapsed_ms,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
    except Exception as e:
        logger.exception("MySQL GET workflow trace 失败: %s", e)
        raise
    finally:
        db.close()


def get_child_traces(parent_trace_id: str) -> List[Dict[str, Any]]:
    """查询某个父 trace 的所有子 trace 摘要。"""
    db = SessionLocal()
    try:
        rows = (
            db.query(AgentWorkflowTrace)
            .filter(AgentWorkflowTrace.parent_trace_id == parent_trace_id)
            .order_by(AgentWorkflowTrace.created_at.asc())
            .all()
        )
        return [
            {
                "trace_id": r.trace_id,
                "app_name": r.app_name,
                "status": r.status,
                "elapsed_ms": r.elapsed_ms,
                "created_at": r.created_at,
            }
            for r in rows
        ]
    except Exception as e:
        logger.exception("MySQL GET child traces 失败: %s", e)
        raise
    finally:
        db.close()


def list_workflow_traces(
    db: Session,
    keyword: Optional[str] = None,
    app_name: Optional[str] = None,
    app_id: Optional[int] = None,
    status: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    skip: int = 0,
    limit: int = 20,
) -> Dict[str, Any]:
    """列表查询工作流追踪记录。"""
    q = db.query(AgentWorkflowTrace)

    if app_id is not None:
        q = q.filter(AgentWorkflowTrace.app_id == app_id)
    if keyword:
        like = f"%{keyword}%"
        q = q.filter(
            or_(
                AgentWorkflowTrace.trace_id.like(like),
                AgentWorkflowTrace.app_name.like(like),
            )
        )
    if app_name:
        q = q.filter(AgentWorkflowTrace.app_name == app_name)
    if status:
        q = q.filter(AgentWorkflowTrace.status == status)
    if date_from:
        try:
            d = datetime.strptime(date_from, "%Y-%m-%d")
            ts = int(d.timestamp() * 1000)
            q = q.filter(AgentWorkflowTrace.created_at >= ts)
        except ValueError:
            pass
    if date_to:
        try:
            d = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
            ts = int(d.timestamp() * 1000)
            q = q.filter(AgentWorkflowTrace.created_at < ts)
        except ValueError:
            pass

    total = q.count()
    rows = q.order_by(desc(AgentWorkflowTrace.created_at)).offset(skip).limit(limit).all()

    items = [
        {
            "trace_id": r.trace_id,
            "run_id": r.run_id,
            "app_id": r.app_id,
            "version_id": r.version_id,
            "app_name": r.app_name,
            "parent_trace_id": r.parent_trace_id,
            "status": r.status,
            "elapsed_ms": r.elapsed_ms,
            "created_at": r.created_at,
            "updated_at": r.updated_at,
            "error": r.error,
        }
        for r in rows
    ]
    return {"total": total, "items": items}
