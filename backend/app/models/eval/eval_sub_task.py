from sqlalchemy import Column, Integer, String, Text, TIMESTAMP, JSON, func
from ...core.database import Base


class EvalSubTask(Base):
    __tablename__ = "eval_sub_tasks"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    task_id = Column(Integer, nullable=False, index=True, comment="所属任务ID")
    target_type = Column(String(30), nullable=False, comment="评测对象类型")
    target_id = Column(Integer, nullable=True, comment="评测对象ID")
    target_config = Column(JSON, nullable=True, comment="评测对象配置")
    status = Column(String(30), default="pending", comment="状态")
    total_cases = Column(Integer, default=0, comment="总用例数")
    completed_cases = Column(Integer, default=0, comment="已完成数")
    passed_cases = Column(Integer, default=0, comment="通过数")
    failed_cases = Column(Integer, default=0, comment="未通过数")
    error_cases = Column(Integer, default=0, comment="错误数")
    started_at = Column(TIMESTAMP, nullable=True, comment="开始时间")
    completed_at = Column(TIMESTAMP, nullable=True, comment="完成时间")
    error_message = Column(Text, nullable=True, comment="错误信息")
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    updated_at = Column(TIMESTAMP, server_default=func.current_timestamp(), onupdate=func.current_timestamp())
