from enum import Enum
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime


class SampleLibraryBase(BaseModel):
    sample_name: str = Field(..., description="样例名称")
    sql_content: str = Field(..., description="SQL内容")


class SampleLibraryCreate(SampleLibraryBase):
    pass


class SampleLibraryUpdate(SampleLibraryBase):
    sample_name: Optional[str] = Field(None, description="样例名称")
    sql_content: Optional[str] = Field(None, description="SQL内容")


class SampleLibrary(SampleLibraryBase):
    id: int
    knowledge_access_id: int
    created_at: datetime
    updated_at: datetime
    is_deleted: bool

    class Config:
        from_attributes = True


class SampleLibraryImportMode(str, Enum):
    replace_all = "replace_all"
    append = "append"


class SampleLibraryImportRequest(BaseModel):
    mode: SampleLibraryImportMode
    rows: List[SampleLibraryBase] = Field(..., description="导入行列表")


class SampleLibraryImportResult(BaseModel):
    inserted: int
    message: str


class SampleLibraryPage(BaseModel):
    total: int
    items: List[SampleLibrary]
