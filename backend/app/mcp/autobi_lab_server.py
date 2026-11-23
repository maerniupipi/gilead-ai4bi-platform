"""
AutoBI 实验室 MCP：单工具「发起网关问答」。
与 ``POST /api/autobi/gateway/v2/lab`` 业务一致；MCP 侧聚合 SSE 为 JSON 返回。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from mcp.server.fastmcp import FastMCP
from sqlalchemy.orm import Session

from ..core.database import SessionLocal
from ..schemas.autobi_gateway import LabGatewayV2Request
from ..services.autobi.lab_gateway_collect import run_lab_gateway_v2_collect

lab_mcp = FastMCP(
    "autobi-lab",
    instructions=(
        "AutoBI 实验室网关：根据用户自然语言问题、项目 API ID（api_access_id）"
        "发起一次完整流水线；返回 trace_id、数据总结正文 summary；失败时 error 非空。"
    ),
)


@lab_mcp.tool()
async def lab_gateway_ask(
    content: str,
    id: str,
    features: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    发起一次实验室问答（等价于 HTTP POST /api/autobi/gateway/v2/lab，非流式聚合结果）。

    :param content: 用户问题（自然语言）
    :param id: 项目 10 位 api_access_id（与实验室前端网关 body.id 一致）
    :param features: 可选，与网关请求体 features 相同，用于替换提示词占位符
    """
    db: Session = SessionLocal()
    try:
        body = LabGatewayV2Request(content=content, id=id, features=features)
        return await run_lab_gateway_v2_collect(db, body)
    finally:
        db.close()


def build_lab_mcp_sse_app():
    """供 FastAPI ``mount`` 的 Starlette 子应用（默认含 /sse 与消息端点）。"""
    return lab_mcp.sse_app()
