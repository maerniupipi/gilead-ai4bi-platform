"""
系统更新日志模型
"""
from sqlalchemy import Column, Integer, String, Text, TIMESTAMP, func, Index, Boolean
from ..core.database import Base


class SystemUpdate(Base):
    """系统更新日志表"""
    __tablename__ = "system_updates"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    version = Column(String(20), nullable=False, comment="版本号，如 v1.2.0")
    title = Column(String(200), nullable=False, comment="更新标题")
    content = Column(Text, nullable=False, comment="更新内容，支持HTML格式")
    update_type = Column(String(20), nullable=False, comment="更新类型: feature/improvement/fix/security")
    is_published = Column(Boolean, default=True, comment="是否已发布")
    release_date = Column(TIMESTAMP, nullable=False, comment="发布日期")
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp(), comment="创建时间")
    updated_at = Column(TIMESTAMP, server_default=func.current_timestamp(), onupdate=func.current_timestamp(), comment="更新时间")

    __table_args__ = (
        Index("idx_system_updates_version", "version"),
        Index("idx_system_updates_is_published", "is_published"),
        Index("idx_system_updates_release_date", "release_date"),
    )
