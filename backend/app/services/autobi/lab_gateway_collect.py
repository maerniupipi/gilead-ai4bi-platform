"""实验室网关：聚合 SSE 结果为单次 JSON（MCP / 评测 / 内部复用）。"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ...core.execution import read_database
from ...schemas.autobi_gateway import LabGatewayV2Request
from .lab_runtime import build_lab_run_spec_from_api_request, collect_lab_run_json


async def run_lab_gateway_v2_collect(db: Session, body: LabGatewayV2Request) -> Dict[str, Any]:
    """
    与 ``POST /api/autobi/gateway/v2/lab`` 同源逻辑，但不走 HTTP 流式，直接返回
    ``trace_id``、``summary``、``error``（与 ``collect_autobi_lab_gateway_json`` 一致）。
    """
    try:
        spec = await read_database(db, build_lab_run_spec_from_api_request, body)
    except HTTPException as e:
        return {
            "trace_id": None,
            "summary": "",
            "error": str(e.detail),
            "http_status": int(e.status_code),
        }
    out = await collect_lab_run_json(db, spec)
    err = out.get("error")
    return {
        "trace_id": out.get("trace_id"),
        "summary": out.get("summary") or "",
        "error": err,
        "http_status": None if err is None else 500,
    }
