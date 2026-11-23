"""实验室流水线追踪（调试日志）：整包写入 MySQL（autobi_lab_traces 表），主键为 trace_id。

对话列表与聊天轮次（用户问题、总结、SQL 等）由 autobi_lab_chat_state 存 MySQL，勿与本模块混淆。
"""

from __future__ import annotations

import uuid
from typing import Any, Dict

from fastapi import HTTPException

from ...core.redis_client import trace_get, trace_set
from ...schemas.autobi_lab_trace import AutobiLabTraceUpsert


def _ensure_uuid(trace_id: str) -> None:
    try:
        uuid.UUID(trace_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="trace_id 须为合法 UUID") from e


def upsert_lab_trace(path_trace_id: str, body: AutobiLabTraceUpsert) -> Dict[str, Any]:
    _ensure_uuid(path_trace_id)
    if body.trace_id != path_trace_id:
        raise HTTPException(status_code=400, detail="路径与 body 中的 trace_id 不一致")
    payload = body.model_dump()
    trace_set(path_trace_id, payload)
    return {"trace_id": path_trace_id, "saved": True}


def get_lab_trace(trace_id: str) -> Dict[str, Any]:
    _ensure_uuid(trace_id)
    data = trace_get(trace_id)
    if not data:
        raise HTTPException(status_code=404, detail="未找到该追踪记录")
    return data
