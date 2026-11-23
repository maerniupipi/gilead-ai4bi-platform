"""
ES配置数据模型
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, UniqueConstraint
from sqlalchemy.sql import func
from ..core.database import Base


class EsConfig(Base):
    """ES配置表"""
    __tablename__ = "es_configs"
    __table_args__ = (
        UniqueConstraint("is_default", "space_id", name="uq_es_config_default_flag_per_space"),
    )

    id = Column(Integer, primary_key=True, index=True, comment="主键ID")
    space_id = Column(Integer, nullable=False, default=1, index=True, comment="所属空间ID")
    name = Column(String(100), nullable=False, comment="配置名称")
    host = Column(String(255), nullable=True, comment="ES Host地址")
    port = Column(String(20), nullable=True, comment="端口")
    username = Column(String(100), nullable=True, comment="用户名")
    password = Column(String(500), nullable=True, comment="密码")
    is_default = Column(Boolean, default=True, nullable=False, comment="是否默认启用")
    is_active = Column(Boolean, default=True, nullable=False, comment="是否启用")
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")