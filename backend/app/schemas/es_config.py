"""
ES配置相关Pydantic模型
"""
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field


class EsConfigBase(BaseModel):
    space_id: Optional[int] = Field(None, description="所属空间ID")
    name: str = Field(..., description="配置名称")
    host: Optional[str] = Field(None, description="ES Host地址")
    port: Optional[str] = Field(None, description="端口")
    username: Optional[str] = Field(None, description="用户名")
    password: Optional[str] = Field(None, description="密码")
    is_default: bool = Field(default=True, description="是否默认")
    is_active: bool = Field(default=True, description="是否启用")


class EsConfigCreate(EsConfigBase):
    pass


class EsConfigUpdate(BaseModel):
    name: Optional[str] = None
    host: Optional[str] = None
    port: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    is_default: Optional[bool] = None
    is_active: Optional[bool] = None


class EsConfigResponse(EsConfigBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class EsConfigTestRequest(EsConfigBase):
    pass


class EsConfigTestResponse(BaseModel):
    success: bool
    message: str
    response_data: Optional[dict] = None