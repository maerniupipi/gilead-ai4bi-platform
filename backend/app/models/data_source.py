"""
数据源模型 - 存储数据库连接配置信息
"""
from sqlalchemy import Column, Integer, String, Boolean, TIMESTAMP, func
from sqlalchemy.orm import relationship
from ..core.database import Base


class DataSource(Base):
    """数据源配置表 - 管理外部数据库连接信息"""
    __tablename__ = "data_source"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    space_id = Column(Integer, nullable=False, default=1, index=True, comment="所属空间ID")
    name = Column(String(100), nullable=False)
    database_type = Column(String(50), nullable=False)
    host = Column(String(255), nullable=False)
    port = Column(Integer, nullable=False)
    username = Column(String(100), nullable=False)
    password = Column(String(500), nullable=False)
    default_database = Column(String(100), nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    updated_at = Column(TIMESTAMP, server_default=func.current_timestamp(), onupdate=func.current_timestamp())
    is_deleted = Column(Boolean, default=False)

    knowledge_accesses = relationship("KnowledgeAccess", back_populates="data_source")
