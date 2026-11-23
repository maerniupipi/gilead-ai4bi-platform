from sqlalchemy import Column, Integer, String, Text, TIMESTAMP, JSON, func
from ...core.database import Base


class EvalRun(Base):
    __tablename__ = "eval_runs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    sub_task_id = Column(Integer, nullable=False, index=True, comment="所属子任务ID")
    case_id = Column(Integer, nullable=False, index=True, comment="评测用例ID")
    status = Column(String(20), default="pending", comment="状态")
    raw_response = Column(Text, nullable=True, comment="原始响应")
    parsed_response = Column(JSON, nullable=True, comment="解析后的响应")
    error_message = Column(Text, nullable=True, comment="错误信息")
    execution_time_ms = Column(Integer, nullable=True, comment="执行耗时ms")
    attempt = Column(Integer, default=1, comment="尝试次数")
    started_at = Column(TIMESTAMP, nullable=True, comment="开始时间")
    completed_at = Column(TIMESTAMP, nullable=True, comment="完成时间")
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
