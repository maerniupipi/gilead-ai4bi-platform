from sqlalchemy import Column, Integer, String, Boolean, TIMESTAMP, JSON, func
from ...core.database import Base


class EvalOutputTemplate(Base):
    __tablename__ = "eval_output_templates"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    suite_id = Column(Integer, nullable=False, index=True, comment="所属评测集ID")
    name = Column(String(100), nullable=False, comment="模板名称")
    fields = Column(JSON, nullable=False, comment="字段定义列表")
    is_default = Column(Boolean, default=False, comment="是否默认模板")
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    updated_at = Column(TIMESTAMP, server_default=func.current_timestamp(), onupdate=func.current_timestamp())
