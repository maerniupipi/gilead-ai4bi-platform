from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field


class EvalRunResponse(BaseModel):
    """评估运行响应模型"""
    id: int
    sub_task_id: int
    case_id: int
    status: str
    raw_response: Optional[str] = None
    parsed_response: Optional[dict] = None
    error_message: Optional[str] = None
    execution_time_ms: Optional[int] = None
    attempt: int = 1
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class EvalRunListResponse(BaseModel):
    """评估运行列表响应"""
    items: List[EvalRunResponse]
    total: int


class EvalManualCorrection(BaseModel):
    """评估手动修正请求"""
    is_correct: bool = Field(..., description="是否正确")
    note: Optional[str] = Field(None, description="备注")
