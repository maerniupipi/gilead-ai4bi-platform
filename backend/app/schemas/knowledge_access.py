from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class KnowledgeAccessBase(BaseModel):
    space_id: Optional[int] = Field(1, description="所属空间ID")
    name: str = Field(..., description="知识接入名称")
    description: Optional[str] = Field(None, description="描述")
    data_source_id: int = Field(..., description="数据源ID")


class KnowledgeAccessCreate(KnowledgeAccessBase):
    pass


class KnowledgeAccessUpdate(KnowledgeAccessBase):
    space_id: Optional[int] = Field(None, description="所属空间ID")
    name: Optional[str] = Field(None, description="知识接入名称")


class KnowledgeAccess(KnowledgeAccessBase):
    id: int
    data_source_name: Optional[str] = Field(None, description="数据源名称")
    created_at: datetime
    updated_at: datetime
    is_deleted: bool

    class Config:
        from_attributes = True
