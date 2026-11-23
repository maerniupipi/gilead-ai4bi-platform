from sqlalchemy import Column, Integer, String, Boolean, Text, TIMESTAMP, JSON, func
from ...core.database import Base


class EvalCaseGroundTruth(Base):
    __tablename__ = "eval_case_ground_truths"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    case_id = Column(Integer, nullable=False, index=True, comment="所属用例ID")
    version = Column(String(50), default="v1.0", comment="参考答案版本")
    ground_truth = Column(Text, nullable=False, comment="参考答案内容")
    ground_truth_type = Column(String(20), default="text", comment="参考答案格式")
    comparison_method = Column(String(30), nullable=False, comment="对比方式")
    comparison_config = Column(JSON, nullable=True, comment="对比配置参数")
    is_active = Column(Boolean, default=True, comment="是否启用")
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    updated_at = Column(TIMESTAMP, server_default=func.current_timestamp(), onupdate=func.current_timestamp())
