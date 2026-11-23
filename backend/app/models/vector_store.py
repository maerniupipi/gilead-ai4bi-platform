"""
向量库配置数据模型
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean
from sqlalchemy.sql import func
from ..core.database import Base


class VectorStoreConfig(Base):
    """向量库配置表：同一空间仅允许启用一个"""
    __tablename__ = "vector_store_configs"

    id = Column(Integer, primary_key=True, index=True, comment="主键ID")
    space_id = Column(Integer, nullable=False, default=1, index=True, comment="所属空间ID")
    name = Column(String(100), nullable=False, comment="向量库名称")
    provider = Column(String(50), nullable=False, default="milvus", comment="向量库类型")
    host = Column(String(255), nullable=True, comment="地址/Host")
    port = Column(String(20), nullable=True, comment="端口")
    username = Column(String(100), nullable=True, comment="用户名")
    password = Column(String(500), nullable=True, comment="密码")
    database = Column(String(100), nullable=True, comment="数据库/namespace")
    collection_prefix = Column(String(100), nullable=True, comment="集合前缀")
    dimension = Column(Integer, nullable=True, comment="向量维度")
    extra_config = Column(Text, nullable=True, comment="扩展配置JSON")
    is_active = Column(Boolean, default=True, nullable=False, comment="是否启用")
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")
