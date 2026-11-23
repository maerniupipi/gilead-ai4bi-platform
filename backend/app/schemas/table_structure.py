from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class TableStructureBase(BaseModel):
    table_name: str = Field(..., description="表名")
    table_alias: Optional[str] = Field(None, description="表中文名")


class TableStructureCreate(TableStructureBase):
    pass


class TableStructureUpdate(TableStructureBase):
    table_name: Optional[str] = Field(None, description="表名")


class TableStructure(TableStructureBase):
    id: int
    knowledge_access_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TableFieldBase(BaseModel):
    field_name: str = Field(..., description="字段名")
    field_alias: Optional[str] = Field(None, description="字段中文名")
    field_type: str = Field(..., description="字段类型")
    is_enabled: bool = Field(True, description="是否生效")
    is_vectorized: bool = Field(False, description="是否向量化")


class TableFieldCreate(TableFieldBase):
    pass


class TableFieldUpdate(TableFieldBase):
    field_name: Optional[str] = Field(None, description="字段名")
    field_type: Optional[str] = Field(None, description="字段类型")


class TableField(TableFieldBase):
    id: int
    table_structure_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TableInfo(BaseModel):
    """Table information from external database"""
    table_name: str = Field(..., description="Table name")
    table_comment: Optional[str] = Field(None, description="Table comment")
    is_imported: bool = Field(False, description="Whether already imported")


class TableFieldInfo(BaseModel):
    """Field information from external database"""
    field_name: str = Field(..., description="Field name")
    field_type: str = Field(..., description="Field type")
    field_comment: Optional[str] = Field(None, description="Field comment")


class ImportTablesRequest(BaseModel):
    """Request for importing tables"""
    table_names: list[str] = Field(..., description="List of table names to import")


class ImportTablesResponse(BaseModel):
    """Response for importing tables"""
    imported_count: int = Field(..., description="Number of tables imported")
    imported_tables: list[str] = Field(..., description="Names of imported tables")
