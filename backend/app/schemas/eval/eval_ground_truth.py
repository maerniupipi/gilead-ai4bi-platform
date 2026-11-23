from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field


class EvalGroundTruthBase(BaseModel):
    """评估标准答案基础模型"""
    ground_truth: str = Field(..., description="标准答案内容")
    ground_truth_type: str = Field("text", description="标准答案类型")
    comparison_method: str = Field(..., description="比较方法")
    comparison_config: Optional[dict] = Field(None, description="比较配置")
    version: str = Field("v1.0", description="版本号")
    is_active: bool = Field(True, description="是否启用")


class EvalGroundTruthCreate(EvalGroundTruthBase):
    """创建评估标准答案请求"""
    pass


class EvalGroundTruthUpdate(BaseModel):
    """更新评估标准答案请求"""
    ground_truth: Optional[str] = Field(None, description="标准答案内容")
    ground_truth_type: Optional[str] = Field(None, description="标准答案类型")
    comparison_method: Optional[str] = Field(None, description="比较方法")
    comparison_config: Optional[dict] = Field(None, description="比较配置")
    version: Optional[str] = Field(None, description="版本号")
    is_active: Optional[bool] = Field(None, description="是否启用")


class EvalGroundTruthResponse(EvalGroundTruthBase):
    """评估标准答案响应模型"""
    id: int
    case_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
