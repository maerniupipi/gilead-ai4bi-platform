"""
向量模型配置相关Pydantic模型
"""
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field


class EmbeddingConfigBase(BaseModel):
    space_id: Optional[int] = Field(None, description="所属空间ID")
    name: str = Field(..., description="配置名称")
    provider: str = Field(default="dashscope", description="提供商")
    api_key: Optional[str] = Field(None, description="API Key")
    model: str = Field(default="text-embedding-v4", description="模型名称")
    dimension: int = Field(default=1024, description="向量维度")
    base_url: Optional[str] = Field(None, description="API Base URL")
    is_default: bool = Field(default=True, description="是否默认")
    is_active: bool = Field(default=True, description="是否启用")


class EmbeddingConfigCreate(EmbeddingConfigBase):
    pass


class EmbeddingConfigUpdate(BaseModel):
    name: Optional[str] = None
    provider: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = None
    dimension: Optional[int] = None
    base_url: Optional[str] = None
    is_default: Optional[bool] = None
    is_active: Optional[bool] = None


class EmbeddingConfigResponse(EmbeddingConfigBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True