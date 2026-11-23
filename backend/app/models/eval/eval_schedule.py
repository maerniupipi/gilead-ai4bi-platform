from sqlalchemy import Column, Integer, String, Boolean, Text, TIMESTAMP, JSON, func
from ...core.database import Base


class EvalSchedule(Base):
    __tablename__ = "eval_schedules"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    suite_id = Column(Integer, nullable=False, index=True, comment="关联评测集ID")
    name = Column(String(200), nullable=False, comment="定时任务名称")
    task_config = Column(JSON, nullable=True, comment="创建任务时的参数")
    cron_expression = Column(String(50), nullable=False, comment="Cron表达式")
    is_active = Column(Boolean, default=True, comment="是否启用")
    last_run_at = Column(TIMESTAMP, nullable=True, comment="上次执行时间")
    last_task_id = Column(Integer, nullable=True, comment="上次创建的任务ID")
    next_run_at = Column(TIMESTAMP, nullable=True, comment="下次执行时间")
    notify_on_failure = Column(Boolean, default=True, comment="失败时通知")
    notify_channels = Column(JSON, nullable=True, comment="通知渠道配置")
    created_by = Column(Integer, nullable=False, comment="创建者ID")
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    updated_at = Column(TIMESTAMP, server_default=func.current_timestamp(), onupdate=func.current_timestamp())
