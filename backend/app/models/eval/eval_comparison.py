from sqlalchemy import Column, Integer, String, Boolean, Text, TIMESTAMP, JSON, Numeric, func
from ...core.database import Base


class EvalComparison(Base):
    __tablename__ = "eval_comparisons"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    run_id = Column(Integer, nullable=False, index=True, comment="所属运行记录ID")
    ground_truth_id = Column(Integer, nullable=False, comment="使用的参考答案ID")
    comparison_method = Column(String(30), nullable=False, comment="对比方式")
    is_correct = Column(Boolean, nullable=True, comment="是否通过")
    score = Column(Numeric(5, 4), nullable=True, comment="得分 0-1")
    comparison_detail = Column(JSON, nullable=True, comment="对比详情")
    llm_judge_raw_output = Column(Text, nullable=True, comment="LLM评判原始输出")
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
