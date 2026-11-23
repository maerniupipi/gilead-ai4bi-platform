from datetime import datetime
from pydantic import BaseModel, Field


class EvalTagBase(BaseModel):
    """评估标签基础模型"""
    name: str = Field(..., description="标签名称")
    color: str = Field("#409EFF", description="标签颜色")


class EvalTagCreate(EvalTagBase):
    """创建评估标签请求"""
    pass


class EvalTagUpdate(BaseModel):
    """更新评估标签请求"""
    name: str = Field(None, description="标签名称")
    color: str = Field(None, description="标签颜色")


class EvalTagResponse(EvalTagBase):
    """评估标签响应模型"""
    id: int
    space_id: int
    created_at: datetime

    class Config:
        from_attributes = True
