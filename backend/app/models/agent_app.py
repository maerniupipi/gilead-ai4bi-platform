"""
智能体平台应用与版本（数据库存储）
"""
from sqlalchemy import Boolean, Column, ForeignKey, Integer, JSON, String, TIMESTAMP, Text, func
from sqlalchemy.orm import relationship

from ..core.database import Base


class AgentApp(Base):
    """智能体应用"""

    __tablename__ = "agent_app"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    space_id = Column(Integer, nullable=False, default=1, index=True, comment="所属空间ID")
    folder_id = Column(
        Integer,
        ForeignKey("agent_app_folders.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    name = Column(String(128), nullable=False)
    icon = Column(String(32), nullable=False, default="*")
    description = Column(String(500), nullable=True)
    owner_display_name = Column(String(128), nullable=True)
    api_token = Column(String(128), nullable=True, comment="对外调用 token，由 bootcamp 侧维护")
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    updated_at = Column(
        TIMESTAMP,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )
    is_deleted = Column(Boolean, default=False)

    versions = relationship(
        "AgentAppVersion",
        back_populates="agent_app",
        cascade="all, delete-orphan",
    )


class AgentAppVersion(Base):
    """应用版本"""

    __tablename__ = "agent_app_version"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    agent_app_id = Column(Integer, ForeignKey("agent_app.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(64), nullable=False)
    status = Column(String(32), nullable=False, default="designing")
    mode = Column(String(64), nullable=False, default="融合编排")
    is_output = Column(Boolean, default=False)
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    # 工作流画布：最新快照 JSON { nodes, edges }；workflow_rev 用于乐观锁
    workflow_json = Column(JSON, nullable=True)
    workflow_rev = Column(Integer, nullable=False, default=0, server_default="0")

    agent_app = relationship("AgentApp", back_populates="versions")


class AgentAppCallLog(Base):
    """智能体对外调用日志。"""

    __tablename__ = "agent_app_call_logs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    agent_app_id = Column(Integer, nullable=False, index=True)
    version_id = Column(Integer, nullable=True, index=True)
    caller = Column(String(64), nullable=True)
    conversation_id = Column(String(128), nullable=True)
    request_text = Column(Text, nullable=True)
    status = Column(String(32), nullable=False, default="running")
    output_preview = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    elapsed_ms = Column(Integer, nullable=False, default=0)
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    updated_at = Column(
        TIMESTAMP,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )
