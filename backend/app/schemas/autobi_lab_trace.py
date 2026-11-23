"""AutoBI 实验室流水线追踪（仅 Redis 调试日志）请求体模型。

对话 UI 状态使用 autobi_lab_chat 相关接口存库。
"""

from typing import Any, List, Optional

from pydantic import BaseModel, Field


class AutobiLabTraceStepIn(BaseModel):
    step_uuid: str = Field(..., min_length=1)
    step_id: int
    title: str
    api_key: str
    color: str
    status: str
    request: Optional[Any] = None
    response: Optional[Any] = None
    error: Optional[str] = None
    duration_ms: Optional[int] = None


class AutobiLabTraceUpsert(BaseModel):
    trace_id: str = Field(..., min_length=1)
    project_id: str
    project_name: Optional[str] = None
    user_message: str
    knowledge_base_id: Optional[int] = None
    created_at: int
    updated_at: int
    steps: List[AutobiLabTraceStepIn]
