from sqlalchemy import Column, Integer, String, Text, TIMESTAMP, JSON, func
from ...core.database import Base


class EvalTask(Base):
    __tablename__ = "eval_tasks"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    suite_id = Column(Integer, nullable=False, index=True, comment="所属评测集ID")
    name = Column(String(200), nullable=False, comment="任务名称")
    description = Column(Text, nullable=True, comment="任务描述")
    output_template_id = Column(Integer, nullable=True, comment="输出模板ID")
    case_filter = Column(JSON, nullable=True, comment="用例过滤条件")
    exec_params = Column(JSON, nullable=True, comment="执行参数")
    status = Column(String(30), default="draft", comment="状态")
    total_cases = Column(Integer, default=0, comment="总用例数")
    completed_cases = Column(Integer, default=0, comment="已完成数")
    passed_cases = Column(Integer, default=0, comment="通过数")
    failed_cases = Column(Integer, default=0, comment="未通过数")
    error_cases = Column(Integer, default=0, comment="错误数")
    scheduled_at = Column(TIMESTAMP, nullable=True, comment="定时执行时间")
    started_at = Column(TIMESTAMP, nullable=True, comment="开始时间")
    completed_at = Column(TIMESTAMP, nullable=True, comment="完成时间")
    created_by = Column(Integer, nullable=False, comment="创建者ID")
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    updated_at = Column(TIMESTAMP, server_default=func.current_timestamp(), onupdate=func.current_timestamp())
