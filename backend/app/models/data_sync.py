"""Platform-owned synchronization configuration, runs and progress events."""
from sqlalchemy import BigInteger, Boolean, Column, ForeignKey, Integer, String, Text

from ..core.database import Base


class DataSyncTask(Base):
    __tablename__ = "data_sync_tasks"
    id = Column(String(16), primary_key=True)
    name = Column(String(100), nullable=False)
    schedule_enabled = Column(Boolean, nullable=False, default=False)
    cron_expression = Column(String(100), nullable=False, default="0 2 * * *")
    timezone = Column(String(64), nullable=False, default="Asia/Shanghai")
    next_run_at = Column(BigInteger, nullable=True, index=True)
    active_run_id = Column(String(36), nullable=True)
    last_run_id = Column(String(36), nullable=True)
    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=False)


class DataSyncRun(Base):
    __tablename__ = "data_sync_runs"
    id = Column(String(36), primary_key=True)
    task_id = Column(String(16), ForeignKey("data_sync_tasks.id"), nullable=False, index=True)
    task_name = Column(String(100), nullable=False)
    trigger_type = Column(String(16), nullable=False)
    requested_by = Column(Integer, nullable=True)
    status = Column(String(20), nullable=False, index=True)
    stage = Column(String(20), nullable=False, default="queued")
    page_no = Column(Integer, nullable=False, default=0)
    fetched_rows = Column(BigInteger, nullable=False, default=0)
    loaded_rows = Column(BigInteger, nullable=False, default=0)
    total_rows = Column(BigInteger, nullable=True)
    message = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    worker_id = Column(String(36), nullable=True)
    lease_until = Column(BigInteger, nullable=True, index=True)
    created_at = Column(BigInteger, nullable=False, index=True)
    started_at = Column(BigInteger, nullable=True)
    finished_at = Column(BigInteger, nullable=True)


class DataSyncEvent(Base):
    __tablename__ = "data_sync_events"
    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String(36), ForeignKey("data_sync_runs.id"), nullable=False, index=True)
    stage = Column(String(20), nullable=False)
    message = Column(Text, nullable=False)
    page_no = Column(Integer, nullable=False, default=0)
    fetched_rows = Column(BigInteger, nullable=False, default=0)
    loaded_rows = Column(BigInteger, nullable=False, default=0)
    created_at = Column(BigInteger, nullable=False)
