"""
邀请码模型 - 存储邀请码及其有效期信息
"""
from sqlalchemy import Column, Integer, String, Boolean, TIMESTAMP, func, DateTime
from ..core.database import Base


class InviteCode(Base):
    """邀请码表 - 管理用户访问邀请码"""
    __tablename__ = "invite_code"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    code = Column(String(30), nullable=False, unique=True, index=True, comment="邀请码，最多30个字符")
    expires_at = Column(DateTime, nullable=False, comment="邀请码过期时间")
    is_active = Column(Boolean, default=True, comment="是否启用")
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    updated_at = Column(TIMESTAMP, server_default=func.current_timestamp(), onupdate=func.current_timestamp())
    is_deleted = Column(Boolean, default=False)
