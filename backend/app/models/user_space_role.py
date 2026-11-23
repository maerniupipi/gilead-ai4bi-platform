"""
用户空间角色关联模型
"""
from sqlalchemy import Column, Integer, BigInteger, String, TIMESTAMP, func, UniqueConstraint
from ..core.database import Base


class UserSpaceRole(Base):
    """用户空间角色关联表"""
    __tablename__ = "user_space_roles"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=False, index=True, comment="用户ID")
    space_id = Column(Integer, nullable=False, index=True, comment="空间ID")
    role = Column(String(20), nullable=False, default="member", comment="角色：owner/admin/member/viewer")
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())

    __table_args__ = (
        UniqueConstraint('user_id', 'space_id', name='uk_user_space'),
    )

    def __repr__(self):
        return f"<UserSpaceRole(user_id={self.user_id}, space_id={self.space_id}, role='{self.role}')>"
