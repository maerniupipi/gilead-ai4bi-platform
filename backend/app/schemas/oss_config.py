"""
OSS 配置相关 Pydantic 模型
"""
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field


class OssConfigBase(BaseModel):
    space_id: Optional[int] = Field(None, description="所属空间ID")
    name: str = Field(..., description="配置名称")
    provider: str = Field(default="aliyun", description="存储提供商: aliyun/s3/azure/minio")
    endpoint: Optional[str] = Field(None, description="Endpoint / Region")
    bucket: Optional[str] = Field(None, description="Bucket 名称")
    access_key: Optional[str] = Field(None, description="Access Key / Account Name")
    secret_key: Optional[str] = Field(None, description="Secret Key / Account Key")
    prefix: Optional[str] = Field(None, description="存储路径前缀")
    region: Optional[str] = Field(None, description="区域/Region (S3/Azure)")
    extra_config: Optional[str] = Field(None, description="扩展配置JSON")
    is_default: bool = Field(default=True, description="是否默认")
    is_active: bool = Field(default=True, description="是否启用")


class OssConfigCreate(OssConfigBase):
    pass


class OssConfigUpdate(BaseModel):
    name: Optional[str] = None
    provider: Optional[str] = None
    endpoint: Optional[str] = None
    bucket: Optional[str] = None
    access_key: Optional[str] = None
    secret_key: Optional[str] = None
    prefix: Optional[str] = None
    region: Optional[str] = None
    extra_config: Optional[str] = None
    is_default: Optional[bool] = None
    is_active: Optional[bool] = None


class OssConfigResponse(OssConfigBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class OssConfigTestRequest(OssConfigBase):
    pass


class OssConfigTestResponse(BaseModel):
    success: bool
    message: str
    response_data: Optional[dict] = None
