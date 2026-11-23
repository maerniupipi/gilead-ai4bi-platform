"""
AutoBI 实验室：左侧对话列表与聊天区轮次（持久化 MySQL）。
流水线步骤明细仅存 Redis（trace_id），见 lab_trace。
"""
from sqlalchemy import Column, Integer, Text, ForeignKey, TIMESTAMP, func
from sqlalchemy.dialects.mysql import LONGTEXT

from ..core.database import Base


class AutobiLabChatState(Base):
    __tablename__ = "autobi_lab_chat_state"

    project_id = Column(
        Integer,
        ForeignKey("autobi_projects.id", ondelete="CASCADE"),
        primary_key=True,
    )
    # JSON：{ "conversations": [...], "active_conversation_id": "..." }，camelCase 与前端一致
    payload_json = Column(Text().with_variant(LONGTEXT(), "mysql"), nullable=False)
    updated_at = Column(
        TIMESTAMP,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )
