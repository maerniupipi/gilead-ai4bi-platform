"""AutoBI 对外 HTTP 网关请求体。"""

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


def _effective_features(req: "LabGatewayV2Request") -> Dict[str, Any]:
    if req.features is not None:
        return dict(req.features)
    if req.metadata is not None:
        return dict(req.metadata)
    return {}


class LabGatewayV2Request(BaseModel):
    """POST /api/autobi/gateway/v2/lab — 与实验室对话逻辑一致；流式仅返回 trace_id + 数据总结。"""

    content: str = Field(..., min_length=1, description="用户自然语言问题")
    id: str = Field(..., min_length=1, description="10 位 API 调用 ID（api_access_id）")
    features: Optional[Dict[str, Any]] = Field(
        default=None,
        description="与提示词中 {{键名}} 同名则预先替换（在流水线其它占位符之前）",
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="已废弃，请使用 features；若仅传 metadata 则按 features 处理",
    )
