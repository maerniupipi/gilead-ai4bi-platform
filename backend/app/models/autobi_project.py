"""
AutoBI 项目配置（存 OpenTrek 风格 completions 入参 JSON）
"""
from sqlalchemy import Column, Integer, String, Text, Boolean, ForeignKey, TIMESTAMP, func
from sqlalchemy.dialects.mysql import LONGTEXT

from ..core.database import Base


class AutobiProject(Base):
    __tablename__ = "autobi_projects"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    space_id = Column(Integer, nullable=False, default=1, index=True, comment="所属空间ID")
    # 对外 HTTP 调用主键（10 位字母数字），与自增 id 不同
    api_access_id = Column(String(10), unique=True, nullable=True, index=True)
    # 外链分享 token（免登录访问）
    share_token = Column(String(64), nullable=True, unique=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    knowledge_base_id = Column(Integer, ForeignKey("knowledge_base.id"), nullable=True)
    folder_id = Column(Integer, ForeignKey("autobi_folders.id"), nullable=False, server_default="1")
    # 完整存储：{ knowledge_base_id, model_bindings, request: { messages, stream, advanced_config } }
    config_json = Column(Text().with_variant(LONGTEXT(), "mysql"), nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    updated_at = Column(TIMESTAMP, server_default=func.current_timestamp(), onupdate=func.current_timestamp())
    is_deleted = Column(Boolean, default=False)
