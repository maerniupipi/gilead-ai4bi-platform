from sqlalchemy import Column, Integer, String, Boolean, Text, TIMESTAMP, JSON, func
from ...core.database import Base


class EvalCase(Base):
    __tablename__ = "eval_cases"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    suite_id = Column(Integer, nullable=False, index=True, comment="所属评测集ID")
    input_prompt = Column(Text, nullable=False, comment="输入提示词")
    input_variables = Column(JSON, nullable=True, comment="模板变量值")
    expected_output_type = Column(String(20), default="text", comment="期望输出类型")
    difficulty = Column(String(20), default="medium", comment="难度：easy/medium/hard")
    category = Column(String(100), nullable=True, comment="问题分类")
    remark = Column(Text, nullable=True, comment="备注")
    sort_order = Column(Integer, default=0, comment="排序序号")
    is_active = Column(Boolean, default=True, comment="是否启用")
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    updated_at = Column(TIMESTAMP, server_default=func.current_timestamp(), onupdate=func.current_timestamp())
