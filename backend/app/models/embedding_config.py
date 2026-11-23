"""
向量模型配置数据模型
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, UniqueConstraint
from sqlalchemy.sql import func
from ..core.database import Base


class EmbeddingConfig(Base):
    """向量模型配置表"""
    __tablename__ = "embedding_configs"
    __table_args__ = (
        UniqueConstraint("is_default", "space_id", name="uq_embedding_config_default_flag_per_space"),
    )

    id = Column(Integer, primary_key=True, index=True, comment="主键ID")
    space_id = Column(Integer, nullable=False, default=1, index=True, comment="所属空间ID")
    name = Column(String(100), nullable=False, comment="配置名称")
    provider = Column(String(50), nullable=False, default="dashscope", comment="提供商")
    api_key = Column(String(500), nullable=True, comment="API Key")
    model = Column(String(100), nullable=False, default="text-embedding-v4", comment="模型名称")
    dimension = Column(Integer, nullable=False, default=1024, comment="向量维度")
    base_url = Column(String(255), nullable=True, comment="API Base URL")
    is_default = Column(Boolean, default=True, nullable=False, comment="是否默认启用")
    is_active = Column(Boolean, default=True, nullable=False, comment="是否启用")
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")