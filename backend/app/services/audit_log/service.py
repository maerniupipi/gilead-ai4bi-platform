"""
审计日志服务层
"""
from typing import Optional
from datetime import datetime
from sqlalchemy.orm import Session
from fastapi import HTTPException

from ...repositories.audit_log.repository import AuditLogRepository
from ...schemas.audit_log import AuditLogResponse, AuditLogListResponse


class AuditLogService:
    """审计日志服务类"""

    @staticmethod
    def create_log(
        db: Session,
        *,
        user_id: Optional[int] = None,
        username: Optional[str] = None,
        action: str,
        resource_type: str,
        resource_id: Optional[str] = None,
        resource_name: Optional[str] = None,
        space_id: Optional[int] = None,
        ip_address: Optional[str] = None,
        method: str = "GET",
        path: str = "",
        status_code: Optional[int] = None,
        request_body: Optional[str] = None,
        response_body: Optional[str] = None,
        duration_ms: Optional[int] = None,
        error_message: Optional[str] = None,
    ) -> AuditLogResponse:
        """创建审计日志"""
        log = AuditLogRepository.create(
            db,
            user_id=user_id,
            username=username,
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id else None,
            resource_name=resource_name,
            space_id=space_id,
            ip_address=ip_address,
            method=method,
            path=path,
            status_code=status_code,
            request_body=request_body,
            response_body=response_body,
            duration_ms=duration_ms,
            error_message=error_message,
        )

        return AuditLogResponse.model_validate(log)

    @staticmethod
    def list_logs(
        db: Session,
        skip: int = 0,
        limit: int = 50,
        user_id: Optional[int] = None,
        action: Optional[str] = None,
        resource_type: Optional[str] = None,
        space_id: Optional[int] = None,
        status_code: Optional[int] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> AuditLogListResponse:
        """获取审计日志列表"""
        logs = AuditLogRepository.get_list(
            db, skip, limit, user_id, action, resource_type, space_id, status_code, start_time, end_time
        )
        total = AuditLogRepository.count(
            db, user_id, action, resource_type, space_id, status_code, start_time, end_time
        )
        return AuditLogListResponse(
            logs=[AuditLogResponse.model_validate(log) for log in logs],
            total=total,
        )

    @staticmethod
    def get_log(db: Session, log_id: int) -> AuditLogResponse:
        """获取审计日志详情"""
        log = AuditLogRepository.get_by_id(db, log_id)
        if not log:
            raise HTTPException(status_code=404, detail="日志不存在")
        return AuditLogResponse.model_validate(log)
