from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class DataSourceBase(BaseModel):
    space_id: Optional[int] = Field(1, description="所属空间ID")
    name: str = Field(..., description="数据源名称")
    database_type: str = Field(..., description="数据库类型")
    host: str = Field(..., description="数据库地址")
    port: int = Field(..., description="端口号")
    username: str = Field(..., description="账号")
    password: str = Field(..., description="密码")
    default_database: str = Field(..., description="默认数据库")


class DataSourceCreate(DataSourceBase):
    pass


class DataSourceUpdate(DataSourceBase):
    space_id: Optional[int] = Field(None, description="所属空间ID")
    name: Optional[str] = Field(None, description="数据源名称")
    database_type: Optional[str] = Field(None, description="数据库类型")
    host: Optional[str] = Field(None, description="数据库地址")
    port: Optional[int] = Field(None, description="端口号")
    username: Optional[str] = Field(None, description="账号")
    password: Optional[str] = Field(None, description="密码")
    default_database: Optional[str] = Field(None, description="默认数据库")


class DataSource(DataSourceBase):
    id: int
    created_at: datetime
    updated_at: datetime
    is_deleted: bool

    class Config:
        from_attributes = True


class DataSourceTestRequest(DataSourceBase):
    pass


class DataSourceTestResponse(BaseModel):
    success: bool
    message: str
    response_data: Optional[dict] = None


class DataSourceQueryRequest(BaseModel):
    sql: str = Field(..., min_length=1)
    database: Optional[str] = None
    schema_name: Optional[str] = None
