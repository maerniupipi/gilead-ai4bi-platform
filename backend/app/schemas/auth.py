"""
认证相关的Schema定义
"""
from pydantic import BaseModel, Field
from datetime import datetime


class InviteCodeVerifyRequest(BaseModel):
    """邀请码验证请求"""
    code: str = Field(..., max_length=30, description="邀请码")


class InviteCodeVerifyResponse(BaseModel):
    """邀请码验证响应"""
    valid: bool = Field(..., description="是否有效")
    token: str = Field(default="", description="验证通过后的token")


class SessionLoginResponse(BaseModel):
    """无邀请码会话登录响应（与邀请码流程生成的 token 格式一致）"""
    token: str = Field(..., description="会话 token")


class InviteCodeCreate(BaseModel):
    """创建邀请码请求"""
    code: str = Field(..., max_length=30, description="邀请码")
    expires_at: datetime = Field(..., description="过期时间")
    is_active: bool = Field(default=True, description="是否启用")


class InviteCodeResponse(BaseModel):
    """邀请码响应"""
    id: int
    code: str
    expires_at: datetime
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True
