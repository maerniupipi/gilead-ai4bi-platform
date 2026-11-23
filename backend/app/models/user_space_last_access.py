"""
用户最后访问空间记录模型
"""
from sqlalchemy import Column, Integer, BigInteger, TIMESTAMP, func
from ..core.database import Base


class UserSpaceLastAccess(Base):
    """用户最后访问空间记录表"""
    __tablename__ = "user_space_last_access"

    user_id = Column(BigInteger, primary_key=True, index=True, comment="用户ID")
    last_space_id = Column(Integer, nullable=False, comment="最后访问的空间ID")
    updated_at = Column(TIMESTAMP, server_default=func.current_timestamp(), onupdate=func.current_timestamp())

    def __repr__(self):
        return f"<UserSpaceLastAccess(user_id={self.user_id}, last_space_id={self.last_space_id})>"
