from typing import Optional, Any
from datetime import datetime
from pydantic import BaseModel, Field


class EvalComparisonResponse(BaseModel):
    """评估比较响应模型"""
    id: int
    run_id: int
    ground_truth_id: int
    comparison_method: str
    is_correct: bool
    score: Optional[float] = None
    comparison_detail: Optional[Any] = None
    created_at: datetime

    class Config:
        from_attributes = True
