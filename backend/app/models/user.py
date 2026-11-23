"""
用户模型
"""
from sqlalchemy import Boolean, Column, Integer, String, TIMESTAMP, func
from ..core.database import Base


class User(Base):
    """用户表"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    username = Column(String(64), unique=True, nullable=False, index=True, comment="用户名")
    display_name = Column(String(128), nullable=True, comment="显示名称")
    password_hash = Column(String(256), nullable=True, comment="密码哈希")
    # 系统级角色: super_admin / admin / member / visitor
    system_role = Column(String(20), default="member", nullable=False, comment="系统级角色")
    is_active = Column(Boolean, default=True, nullable=False, comment="是否启用")
    is_preset_admin = Column(Boolean, default=False, nullable=False, comment="是否预设管理员")
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    updated_at = Column(
        TIMESTAMP,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

    @property
    def is_super_admin(self) -> bool:
        return self.system_role == "super_admin"
