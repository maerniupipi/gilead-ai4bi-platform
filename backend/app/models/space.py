"""
空间模型 - 定义工作空间
"""
from sqlalchemy import Column, Integer, String, Boolean, Text, TIMESTAMP, JSON, func
from ..core.database import Base


class Space(Base):
    """空间配置表 - 定义独立的工作空间"""
    __tablename__ = "spaces"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(100), nullable=False, comment="空间名称")
    code = Column(String(50), nullable=False, unique=True, comment="空间编码")
    description = Column(Text, nullable=True, comment="空间描述")
    avatar = Column(String(500), nullable=True, comment="空间头像/图标URL")
    is_active = Column(Boolean, default=True, comment="是否启用")
    settings = Column(JSON, nullable=True, comment="空间个性化设置")
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    updated_at = Column(TIMESTAMP, server_default=func.current_timestamp(), onupdate=func.current_timestamp())

    def __repr__(self):
        return f"<Space(id={self.id}, name='{self.name}', code='{self.code}')>"
