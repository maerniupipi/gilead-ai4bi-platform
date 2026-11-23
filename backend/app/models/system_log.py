from sqlalchemy import Column, Integer, BigInteger, String, Text, JSON, Index
from ..core.database import Base


class SystemLog(Base):
    __tablename__ = 'system_logs'
    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(BigInteger, nullable=False, index=True)
    level = Column(String(16), nullable=False, index=True)
    service = Column(String(64), nullable=False)
    instance = Column(String(128), nullable=False)
    logger = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    exception = Column(Text)
    request_id = Column(String(64), index=True)
    conversation_id = Column(String(36), index=True)
    message_id = Column(String(36), index=True)
    trace_id = Column(String(128), index=True)
    user_id = Column(String(320), index=True)
    data = Column(JSON, nullable=False, default=dict)
    __table_args__ = (Index('ix_system_logs_level_time', 'level', 'created_at'),)
