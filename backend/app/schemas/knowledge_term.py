from enum import Enum
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime


class KnowledgeTermBase(BaseModel):
    term_name: str = Field(..., description="词条名称")
    term_value: str = Field(..., description="词条值")


class KnowledgeTermCreate(KnowledgeTermBase):
    pass


class KnowledgeTermUpdate(KnowledgeTermBase):
    term_name: Optional[str] = Field(None, description="词条名称")
    term_value: Optional[str] = Field(None, description="词条值")


class KnowledgeTerm(KnowledgeTermBase):
    id: int
    knowledge_access_id: int
    created_at: datetime
    updated_at: datetime
    is_deleted: bool

    class Config:
        from_attributes = True


class KnowledgeTermImportMode(str, Enum):
    replace_all = "replace_all"
    append = "append"


class KnowledgeTermImportRequest(BaseModel):
    mode: KnowledgeTermImportMode
    rows: List[KnowledgeTermBase] = Field(..., description="导入行列表")


class KnowledgeTermImportResult(BaseModel):
    inserted: int
    message: str


class KnowledgeTermPage(BaseModel):
    total: int
    items: List[KnowledgeTerm]
