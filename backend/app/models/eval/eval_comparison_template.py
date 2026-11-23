from sqlalchemy import Column, Integer, String, Boolean, Text, TIMESTAMP, func
from ...core.database import Base


class EvalComparisonTemplate(Base):
    """评测对比提示词模板"""
    __tablename__ = "eval_comparison_templates"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    space_id = Column(Integer, nullable=False, index=True, comment="所属空间ID")
    name = Column(String(100), nullable=False, comment="模板名称")
    description = Column(String(500), nullable=True, comment="模板描述")
    system_prompt = Column(Text, nullable=False, comment="系统提示词")
    user_prompt = Column(Text, nullable=False, comment="用户提示词模板，包含 {question} {expected} {generated_sql} 占位符")
    comparison_method = Column(String(30), default="llm_judge", comment="对比方式")
    is_default = Column(Boolean, default=False, comment="是否默认模板")
    is_system = Column(Boolean, default=False, comment="系统内置模板，不可删除/编辑")
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    updated_at = Column(TIMESTAMP, server_default=func.current_timestamp(), onupdate=func.current_timestamp())
