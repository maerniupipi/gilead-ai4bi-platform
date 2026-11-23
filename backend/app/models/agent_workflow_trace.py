"""
工作流运行追踪记录（MySQL 持久化）。
"""
from sqlalchemy import Column, Integer, String, Text, BigInteger, JSON, func, TIMESTAMP

from ..core.database import Base


class AgentWorkflowTrace(Base):
    __tablename__ = "agent_workflow_traces"

    id = Column(Integer, primary_key=True, autoincrement=True)
    trace_id = Column(String(36), nullable=False, unique=True, index=True, comment="UUID 追踪ID")
    run_id = Column(String(36), nullable=False, index=True, comment="运行ID")
    app_id = Column(Integer, nullable=False, index=True, comment="应用ID")
    version_id = Column(Integer, nullable=True, comment="版本ID")
    app_name = Column(String(128), nullable=True, comment="应用名称(冗余)")
    parent_trace_id = Column(String(36), nullable=True, index=True, comment="父级 trace_id（嵌套工作流）")
    status = Column(String(32), nullable=False, default="running", comment="running|done|error")
    steps = Column(JSON, nullable=False, comment="节点执行步骤数组")
    nodes = Column(JSON, nullable=True, comment="工作流节点定义快照")
    edges = Column(JSON, nullable=True, comment="工作流边定义快照")
    output = Column(Text, nullable=True, comment="最终输出")
    error = Column(Text, nullable=True, comment="错误信息")
    elapsed_ms = Column(Integer, nullable=False, default=0, comment="总耗时(ms)")
    created_at = Column(BigInteger, nullable=False, index=True, comment="创建时间(epoch ms)")
    updated_at = Column(BigInteger, nullable=False, comment="更新时间(epoch ms)")
    db_created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    db_updated_at = Column(
        TIMESTAMP,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )
