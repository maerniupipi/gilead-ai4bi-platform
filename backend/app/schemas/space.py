"""
空间相关Pydantic模型
"""
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field


class SpaceBase(BaseModel):
    """空间基础模型"""
    name: str = Field(..., description="空间名称", min_length=1, max_length=100)
    code: str = Field(..., description="空间编码", min_length=1, max_length=50)
    description: Optional[str] = Field(None, description="空间描述")
    avatar: Optional[str] = Field(None, description="空间头像URL")
    is_active: bool = Field(default=True, description="是否启用")
    settings: Optional[dict] = Field(None, description="空间个性化设置")


class SpaceCreate(SpaceBase):
    """创建空间请求"""
    pass


class SpaceUpdate(BaseModel):
    """更新空间请求"""
    name: Optional[str] = Field(None, description="空间名称", min_length=1, max_length=100)
    code: Optional[str] = Field(None, description="空间编码", min_length=1, max_length=50)
    description: Optional[str] = None
    avatar: Optional[str] = None
    is_active: Optional[bool] = None
    settings: Optional[dict] = None


class SpaceResponse(SpaceBase):
    """空间响应模型"""
    id: int
    member_count: Optional[int] = Field(None, description="成员数量")
    delete_requested_at: Optional[datetime] = Field(None, description="删除申请时间")
    delete_available_at: Optional[datetime] = Field(None, description="可彻底删除时间")
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SpaceWithRole(SpaceResponse):
    """空间响应模型（包含用户角色）"""
    role: str = Field(..., description="用户在空间中的角色")


class SpaceListResponse(BaseModel):
    """空间列表响应"""
    spaces: List[SpaceWithRole]
    current_space_id: Optional[int] = Field(None, description="当前工作空间ID")


class SpaceMemberAdd(BaseModel):
    """添加空间成员请求"""
    user_id: int = Field(..., description="用户ID")
    role: str = Field(default="member", description="角色：owner/admin/member/visitor")


class SpaceDeleteRequest(BaseModel):
    """删除空间确认请求（第二步可选传 confirm_name）"""
    confirm_name: Optional[str] = Field(None, description="确认删除时输入的空间名称")


class SpaceMemberResponse(BaseModel):
    """空间成员响应"""
    user_id: int
    display_name: Optional[str] = Field(None, description="显示名称")
    role: str
    created_at: datetime

    class Config:
        from_attributes = True


class SpaceSwitchRequest(BaseModel):
    """切换空间请求"""
    space_id: int = Field(..., description="要切换到的空间ID")
