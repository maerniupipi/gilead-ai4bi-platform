from typing import Optional, List, Any
from datetime import datetime
from pydantic import BaseModel, Field


class EvalOutputTemplateBase(BaseModel):
    """评估输出模板基础模型"""
    name: str = Field(..., description="模板名称")
    fields: List[Any] = Field(..., description="字段定义列表")
    is_default: bool = Field(False, description="是否默认模板")


class EvalOutputTemplateCreate(EvalOutputTemplateBase):
    """创建评估输出模板请求"""
    pass


class EvalOutputTemplateUpdate(BaseModel):
    """更新评估输出模板请求"""
    name: Optional[str] = Field(None, description="模板名称")
    fields: Optional[List[Any]] = Field(None, description="字段定义列表")
    is_default: Optional[bool] = Field(None, description="是否默认模板")


class EvalOutputTemplateResponse(EvalOutputTemplateBase):
    """评估输出模板响应模型"""
    id: int
    suite_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
