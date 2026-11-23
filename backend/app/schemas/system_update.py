"""
系统更新日志 Schema
"""
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class SystemUpdateBase(BaseModel):
    """更新日志基础Schema"""
    version: str
    title: str
    content: str
    update_type: str  # feature, improvement, fix, security
    release_date: datetime


class SystemUpdateCreate(SystemUpdateBase):
    """创建更新日志"""
    is_published: bool = True


class SystemUpdateUpdate(BaseModel):
    """更新日志更新"""
    version: Optional[str] = None
    title: Optional[str] = None
    content: Optional[str] = None
    update_type: Optional[str] = None
    is_published: Optional[bool] = None
    release_date: Optional[datetime] = None


class SystemUpdateResponse(SystemUpdateBase):
    """更新日志响应"""
    id: int
    is_published: bool
    created_at: datetime
    updated_at: datetime
    type_label: str = ""

    class Config:
        from_attributes = True

    @classmethod
    def from_orm_with_label(cls, obj):
        """从ORM对象创建，并添加类型标签"""
        data = obj.__dict__.copy()
        type_labels = {
            "feature": "新功能",
            "improvement": "优化",
            "fix": "修复",
            "security": "安全"
        }
        data["type_label"] = type_labels.get(obj.update_type, "其他")
        return cls(**data)


class SystemUpdateList(BaseModel):
    """更新日志列表"""
    items: List[SystemUpdateResponse]
    total: int
