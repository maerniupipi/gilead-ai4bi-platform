"""
用户相关Pydantic模型
"""
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field


class UserBase(BaseModel):
    """用户基础模型"""
    username: str = Field(..., description="用户名", min_length=1, max_length=64)
    display_name: Optional[str] = Field(None, description="显示名称", max_length=128)


class UserCreate(UserBase):
    """创建用户请求"""
    password: Optional[str] = Field(None, description="密码", max_length=128)
    system_role: str = Field(default="member", description="系统级角色: super_admin/admin/member/visitor")


class UserUpdate(BaseModel):
    """更新用户请求"""
    display_name: Optional[str] = Field(None, description="显示名称", max_length=128)
    password: Optional[str] = Field(None, description="新密码", max_length=128)
    system_role: Optional[str] = Field(None, description="系统级角色")
    is_active: Optional[bool] = None


class UserLogin(BaseModel):
    """用户登录请求"""
    username: str = Field(..., description="用户名")
    password: str = Field(..., description="密码")


class UserResponse(UserBase):
    """用户响应模型"""
    id: int
    system_role: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class UserListResponse(BaseModel):
    """用户列表响应"""
    users: List[UserResponse]
    total: int


class CurrentUserResponse(BaseModel):
    """当前登录用户信息"""
    id: int
    username: str
    display_name: Optional[str]
    system_role: str
    is_active: bool

    class Config:
        from_attributes = True
