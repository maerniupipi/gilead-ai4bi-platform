"""
审计日志数据访问层
"""
from typing import List, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import desc
from ...models.audit_log import AuditLog


class AuditLogRepository:
    """审计日志数据访问类"""

    @staticmethod
    def create(db: Session, **kwargs) -> AuditLog:
        """创建审计日志"""
        log = AuditLog(**kwargs)
        db.add(log)
        db.commit()
        db.refresh(log)
        return log

    @staticmethod
    def get_list(
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
    ) -> List[AuditLog]:
        """获取审计日志列表"""
        query = db.query(AuditLog)

        if user_id is not None:
            query = query.filter(AuditLog.user_id == user_id)
        if action:
            query = query.filter(AuditLog.action == action)
        if resource_type:
            query = query.filter(AuditLog.resource_type == resource_type)
        if space_id is not None:
            query = query.filter(AuditLog.space_id == space_id)
        if status_code is not None:
            query = query.filter(AuditLog.status_code == status_code)
        if start_time:
            query = query.filter(AuditLog.created_at >= start_time)
        if end_time:
            query = query.filter(AuditLog.created_at <= end_time)

        return query.order_by(desc(AuditLog.created_at)).offset(skip).limit(limit).all()

    @staticmethod
    def count(
        db: Session,
        user_id: Optional[int] = None,
        action: Optional[str] = None,
        resource_type: Optional[str] = None,
        space_id: Optional[int] = None,
        status_code: Optional[int] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> int:
        """统计审计日志数量"""
        query = db.query(AuditLog)

        if user_id is not None:
            query = query.filter(AuditLog.user_id == user_id)
        if action:
            query = query.filter(AuditLog.action == action)
        if resource_type:
            query = query.filter(AuditLog.resource_type == resource_type)
        if space_id is not None:
            query = query.filter(AuditLog.space_id == space_id)
        if status_code is not None:
            query = query.filter(AuditLog.status_code == status_code)
        if start_time:
            query = query.filter(AuditLog.created_at >= start_time)
        if end_time:
            query = query.filter(AuditLog.created_at <= end_time)

        return query.count()

    @staticmethod
    def get_by_id(db: Session, log_id: int) -> Optional[AuditLog]:
        """根据ID获取审计日志"""
        return db.query(AuditLog).filter(AuditLog.id == log_id).first()
