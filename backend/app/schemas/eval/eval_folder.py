from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field


class EvalFolderBase(BaseModel):
    """评估文件夹基础模型"""
    name: str = Field(..., description="文件夹名称")
    description: Optional[str] = Field(None, description="描述")
    parent_id: Optional[int] = Field(None, description="父文件夹ID")
    sort_order: int = Field(0, description="排序顺序")


class EvalFolderCreate(EvalFolderBase):
    """创建评估文件夹请求"""
    pass


class EvalFolderUpdate(BaseModel):
    """更新评估文件夹请求"""
    name: Optional[str] = Field(None, description="文件夹名称")
    description: Optional[str] = Field(None, description="描述")
    parent_id: Optional[int] = Field(None, description="父文件夹ID")
    sort_order: Optional[int] = Field(None, description="排序顺序")


class EvalFolderResponse(EvalFolderBase):
    """评估文件夹响应模型"""
    id: int
    space_id: int
    is_system: bool = Field(False, description="是否系统内置")
    created_at: datetime
    updated_at: datetime
    children: Optional[List["EvalFolderResponse"]] = Field(None, description="子文件夹")
    suite_count: Optional[int] = Field(None, description="套件数量")

    class Config:
        from_attributes = True


class EvalFolderTree(BaseModel):
    """评估文件夹树形结构"""
    id: int
    name: str
    description: Optional[str] = None
    parent_id: Optional[int] = None
    sort_order: int = 0
    is_system: bool = False
    suite_count: Optional[int] = None
    children: List["EvalFolderTree"] = Field(default_factory=list)

    class Config:
        from_attributes = True
