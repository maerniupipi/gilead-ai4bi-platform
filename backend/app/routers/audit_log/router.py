"""
审计日志路由
"""
from typing import Optional
from datetime import datetime
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ...core.database import get_db
from ...core.permissions import RequireSystemPermission
from ...services.audit_log.service import AuditLogService
from ...schemas.audit_log import AuditLogResponse, AuditLogListResponse

router = APIRouter(tags=["审计日志"])


@router.get("", response_model=AuditLogListResponse)
def list_audit_logs(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    user_id: Optional[int] = Query(None, description="按用户ID筛选"),
    action: Optional[str] = Query(None, description="按操作类型筛选"),
    resource_type: Optional[str] = Query(None, description="按资源类型筛选"),
    space_id: Optional[int] = Query(None, description="按空间ID筛选"),
    status_code: Optional[int] = Query(None, description="按HTTP状态码筛选"),
    start_time: Optional[datetime] = Query(None, description="开始时间"),
    end_time: Optional[datetime] = Query(None, description="结束时间"),
    db: Session = Depends(get_db),
    operator_id: int = Depends(RequireSystemPermission("*")),
):
    """获取审计日志列表（仅超级管理员可访问）"""
    result = AuditLogService.list_logs(
        db, skip, limit, user_id, action, resource_type, space_id, status_code, start_time, end_time
    )
    return {"logs": result.logs, "total": result.total}


@router.get("/{log_id}", response_model=AuditLogResponse)
def get_audit_log(
    log_id: int,
    db: Session = Depends(get_db),
    operator_id: int = Depends(RequireSystemPermission("*")),
):
    """获取审计日志详情（仅超级管理员可访问）"""
    return AuditLogService.get_log(db, log_id)
