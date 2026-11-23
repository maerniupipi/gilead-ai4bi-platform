"""
模型供应商数据模型
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, JSON
from sqlalchemy.sql import func
from ..core.database import Base


class ModelProvider(Base):
    """模型供应商表"""
    __tablename__ = "model_providers"

    id = Column(Integer, primary_key=True, index=True, comment="主键ID")
    name = Column(String(100), nullable=False, comment="供应商名称")
    base_url = Column(String(500), nullable=False, comment="API Base URL")
    api_key = Column(String(500), nullable=True, comment="API Key")
    protocol = Column(String(50), default="openai", comment="协议类型: openai, anthropic, google等")
    models = Column(Text, nullable=True, comment="模型列表，JSON格式存储")
    model_settings = Column(JSON, nullable=True, comment="按模型名称保存思考配置")
    description = Column(Text, nullable=True, comment="备注说明")
    is_active = Column(Boolean, default=True, comment="是否启用")
    is_builtin = Column(Boolean, default=False, comment="是否为内置供应商")
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")
