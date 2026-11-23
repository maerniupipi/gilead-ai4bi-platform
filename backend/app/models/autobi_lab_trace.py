from sqlalchemy import Column, Integer, String, Text, BigInteger, JSON, func, TIMESTAMP
from ..core.database import Base


class AutobiLabTrace(Base):
    """实验室流水线追踪记录（从 Redis 迁移到 MySQL）。"""
    __tablename__ = "autobi_lab_traces"

    id = Column(Integer, primary_key=True, autoincrement=True)
    trace_id = Column(String(36), nullable=False, unique=True, index=True, comment="UUID 追踪ID")
    project_id = Column(String(20), nullable=False, index=True, comment="实验室项目ID")
    project_name = Column(String(200), nullable=True, comment="实验室项目名称")
    user_message = Column(Text, nullable=False, comment="用户输入的问题")
    knowledge_base_id = Column(Integer, nullable=True, comment="知识库ID")
    steps = Column(JSON, nullable=False, comment="18步流水线状态数组")
    created_at = Column(BigInteger, nullable=False, index=True, comment="创建时间(epoch ms)")
    updated_at = Column(BigInteger, nullable=False, comment="更新时间(epoch ms)")
    db_created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    db_updated_at = Column(TIMESTAMP, server_default=func.current_timestamp(), onupdate=func.current_timestamp())
