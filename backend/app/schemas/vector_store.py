"""
向量库配置相关Pydantic模型
"""
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field


class VectorStoreBase(BaseModel):
    space_id: Optional[int] = Field(None, description="所属空间ID")
    name: str = Field(..., description="向量库名称")
    provider: str = Field(default="milvus", description="向量库类型")
    host: Optional[str] = Field(None, description="地址/Host")
    port: Optional[str] = Field(None, description="端口")
    username: Optional[str] = Field(None, description="用户名")
    password: Optional[str] = Field(None, description="密码")
    database: Optional[str] = Field(None, description="数据库/namespace")
    collection_prefix: Optional[str] = Field(None, description="集合前缀")
    dimension: Optional[int] = Field(None, description="向量维度")
    extra_config: Optional[str] = Field(None, description="扩展配置JSON")
    is_active: bool = Field(default=True, description="是否启用")


class VectorStoreCreate(VectorStoreBase):
    pass


class VectorStoreUpdate(BaseModel):
    name: Optional[str] = None
    provider: Optional[str] = None
    host: Optional[str] = None
    port: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    database: Optional[str] = None
    collection_prefix: Optional[str] = None
    dimension: Optional[int] = None
    extra_config: Optional[str] = None
    is_active: Optional[bool] = None


class VectorStoreResponse(VectorStoreBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class VectorStoreTestRequest(VectorStoreBase):
    pass


class VectorStoreTestResponse(BaseModel):
    success: bool
    message: str
    response_data: Optional[dict] = None
