"""
审计日志模型
"""
from sqlalchemy import Column, Integer, String, Text, TIMESTAMP, func, Index
from ..core.database import Base


class AuditLog(Base):
    """审计日志表"""
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, nullable=True, comment="操作用户ID")
    username = Column(String(64), nullable=True, comment="用户名")
    action = Column(String(50), nullable=False, comment="操作类型: login/create/update/delete/export")
    resource_type = Column(String(50), nullable=False, comment="资源类型: user/space/knowledge_base/agent_app等")
    resource_id = Column(String(100), nullable=True, comment="资源ID")
    resource_name = Column(String(200), nullable=True, comment="资源名称/描述")
    space_id = Column(Integer, nullable=True, comment="操作所在空间ID")
    ip_address = Column(String(50), nullable=True, comment="IP地址")
    method = Column(String(10), nullable=False, comment="HTTP方法")
    path = Column(String(500), nullable=False, comment="请求路径")
    status_code = Column(Integer, nullable=True, comment="响应状态码")
    request_body = Column(Text, nullable=True, comment="请求体（脱敏后）")
    response_body = Column(Text, nullable=True, comment="响应体")
    duration_ms = Column(Integer, nullable=True, comment="请求耗时（毫秒）")
    error_message = Column(Text, nullable=True, comment="错误信息")
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp(), comment="创建时间")

    __table_args__ = (
        Index("idx_audit_logs_user_id", "user_id"),
        Index("idx_audit_logs_action", "action"),
        Index("idx_audit_logs_resource_type", "resource_type"),
        Index("idx_audit_logs_space_id", "space_id"),
        Index("idx_audit_logs_created_at", "created_at"),
    )
