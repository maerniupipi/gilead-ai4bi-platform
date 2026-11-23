from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


NER_MAX_PER_KNOWLEDGE_BASE = 1000
NER_FIELD_MAX_LEN = 50
NER_SHEET_NAME_MAX_LEN = 64


class KbNerRowBase(BaseModel):
    sheet_name: str = Field(..., max_length=NER_SHEET_NAME_MAX_LEN, description="对应 Excel 工作表名")
    table_name: str = Field(..., max_length=NER_FIELD_MAX_LEN)
    field_name: str = Field(..., max_length=NER_FIELD_MAX_LEN)
    standard_name: str = Field("", max_length=NER_FIELD_MAX_LEN)
    alias: str = Field("", max_length=NER_FIELD_MAX_LEN)
    remark: str = Field("", max_length=NER_FIELD_MAX_LEN)


class KbNerRowCreate(KbNerRowBase):
    pass


class KbNerRowUpdate(BaseModel):
    sheet_name: Optional[str] = Field(None, max_length=NER_SHEET_NAME_MAX_LEN)
    table_name: Optional[str] = Field(None, max_length=NER_FIELD_MAX_LEN)
    field_name: Optional[str] = Field(None, max_length=NER_FIELD_MAX_LEN)
    standard_name: Optional[str] = Field(None, max_length=NER_FIELD_MAX_LEN)
    alias: Optional[str] = Field(None, max_length=NER_FIELD_MAX_LEN)
    remark: Optional[str] = Field(None, max_length=NER_FIELD_MAX_LEN)


class KbNerRowOut(KbNerRowBase):
    id: int
    knowledge_base_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class KbNerSheetSummary(BaseModel):
    sheet_name: str
    row_count: int


class KbNerRowPage(BaseModel):
    total: int
    items: List[KbNerRowOut]


class KbNerImportMode(str, Enum):
    replace_all = "replace_all"
    append = "append"


class KbNerImportRequest(BaseModel):
    mode: KbNerImportMode
    rows: List[KbNerRowBase] = Field(..., description="导入行列表")


class KbNerImportResult(BaseModel):
    inserted: int
    message: str
