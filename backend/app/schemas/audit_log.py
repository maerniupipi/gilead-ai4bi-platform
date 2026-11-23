"""
审计日志Pydantic模型
"""
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field


class AuditLogResponse(BaseModel):
    """审计日志响应"""
    id: int
    user_id: Optional[int] = None
    username: Optional[str] = None
    action: str
    resource_type: str
    resource_id: Optional[str] = None
    resource_name: Optional[str] = None
    space_id: Optional[int] = None
    ip_address: Optional[str] = None
    method: str
    path: str
    status_code: Optional[int] = None
    request_body: Optional[str] = None
    response_body: Optional[str] = None
    duration_ms: Optional[int] = None
    error_message: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class AuditLogListResponse(BaseModel):
    """审计日志列表响应"""
    logs: List[AuditLogResponse]
    total: int
