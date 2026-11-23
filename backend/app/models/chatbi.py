"""Platform-owned conversations, service credentials, results and export jobs."""
import time
from sqlalchemy import Boolean, Column, Integer, BigInteger, JSON, String, Text, UniqueConstraint, Index, event
from ..core.database import Base


def now():
    return int(time.time())


class ChatBIConversation(Base):
    __tablename__ = "chatbi_conversations"
    id = Column(String(36), primary_key=True)
    owner = Column(String(64), nullable=False, index=True)
    runtime = Column(String(128), nullable=False)
    active_task = Column(String(36))
    turn_count = Column(Integer, nullable=False, default=0)
    created_at = Column(Integer, nullable=False, default=now)


class ChatBIConversationContext(Base):
    """Trusted identity and service-Key attribution for management lookup."""
    __tablename__ = "chatbi_conversation_contexts"
    conversation_id = Column(String(36), primary_key=True)
    key_id = Column(String(36), index=True)
    user_id = Column(String(320), index=True)
    attribution_source = Column(String(24), nullable=False, default="request")
    updated_at = Column(Integer, nullable=False, default=now)


class ChatBIPPTModelConfig(Base):
    """Platform-wide AI PPT model selection; credentials stay in model_providers."""
    __tablename__ = "chatbi_ppt_model_config"
    id = Column(Integer, primary_key=True)
    provider_id = Column(Integer, nullable=False)
    model = Column(String(200), nullable=False)
    updated_by = Column(Integer)
    updated_at = Column(Integer, nullable=False, default=now)


class ChatBIAPIKey(Base):
    """Service credential registry. Raw keys are never persisted here."""
    __tablename__ = "chatbi_api_keys"

    id = Column(String(36), primary_key=True)
    name = Column(String(100), nullable=False)
    environment = Column(String(8), nullable=False, index=True)
    key_hash = Column(String(64), nullable=False, unique=True)
    key_hint = Column(String(32), nullable=False)
    enabled = Column(Boolean, nullable=False, default=True)
    runtime = Column(String(128))
    created_at = Column(Integer, nullable=False, default=now)
    updated_at = Column(Integer, nullable=False, default=now)




class ChatBIMessage(Base):
    __tablename__ = "chatbi_messages"
    __table_args__ = (Index("ix_chatbi_message_conversation_sequence", "conversation_id", "sequence"),)
    id = Column(String(36), primary_key=True)
    conversation_id = Column(String(36), nullable=False, index=True)
    owner = Column(String(64), nullable=False, index=True)
    task_id = Column(String(36), nullable=False, unique=True)
    sequence = Column(Integer, nullable=False, default=0)
    query = Column(Text, nullable=False)
    answer = Column(Text, nullable=False, default="")
    content = Column(JSON, nullable=False, default=list)
    status = Column(String(16), nullable=False, default="running")
    stop_requested = Column(Boolean, nullable=False, default=False)
    error = Column(Text)
    created_at = Column(Integer, nullable=False, default=now)
    finished_at = Column(Integer)


class ChatBIMessageDiagnostic(Base):
    __tablename__ = "chatbi_message_diagnostics"
    message_id = Column(String(36), primary_key=True)
    request_id = Column(String(64), index=True)
    request = Column(JSON, nullable=False, default=dict)
    execution = Column(JSON, nullable=False, default=dict)
    invocations = Column(JSON, nullable=False, default=list)
    traces = Column(JSON, nullable=False, default=list)
    updated_at = Column(BigInteger, nullable=False)


class ChatBITraceLookup(Base):
    __tablename__ = "chatbi_trace_lookup"
    trace_id = Column(String(36), primary_key=True)
    message_id = Column(String(36), primary_key=True, index=True)


class ChatBIDiagnosticIndexState(Base):
    __tablename__ = "chatbi_diagnostic_index_states"
    message_id = Column(String(36), primary_key=True)
    updated_at = Column(BigInteger, nullable=False)


class ChatBIResult(Base):
    __tablename__ = "chatbi_results"
    id = Column(String(36), primary_key=True)
    conversation_id = Column(String(36), nullable=False, index=True)
    message_id = Column(String(36), nullable=False, index=True)
    owner = Column(String(64), nullable=False, index=True)
    title = Column(String(512), nullable=False, default="")
    columns = Column(JSON, nullable=False)
    rows = Column(JSON, nullable=False)
    total_rows = Column(Integer, nullable=False)
    complete = Column(Boolean, nullable=False, default=True)
    created_at = Column(Integer, nullable=False, default=now)


class ChatBIExport(Base):
    __tablename__ = "chatbi_exports"
    __table_args__ = (UniqueConstraint("owner", "idempotency_key", name="uq_chatbi_export_request"),)
    id = Column(String(36), primary_key=True)
    file_id = Column(String(36), nullable=False, unique=True)
    owner = Column(String(64), nullable=False, index=True)
    user_id = Column(String(320), nullable=False)
    conversation_id = Column(String(36), nullable=False, index=True)
    kind = Column(String(8), nullable=False)
    summary_type = Column(String(32))
    payload = Column(JSON, nullable=False)
    request_hash = Column(String(64), nullable=False)
    idempotency_key = Column(String(128))
    status = Column(String(16), nullable=False, default="pending", index=True)
    error = Column(Text)
    file_name = Column(String(256), nullable=False)
    file_size = Column(Integer, nullable=False, default=0)
    created_at = Column(Integer, nullable=False, default=now)
    started_at = Column(Integer)
    finished_at = Column(Integer)
    expires_at = Column(Integer)
    lease_until = Column(Integer)


TABLES = [c.__table__ for c in (ChatBIConversation, ChatBIMessage, ChatBIMessageDiagnostic, ChatBITraceLookup, ChatBIDiagnosticIndexState, ChatBIResult, ChatBIExport, ChatBIAPIKey, ChatBIConversationContext, ChatBIPPTModelConfig)]


@event.listens_for(ChatBIMessageDiagnostic, "after_insert")
@event.listens_for(ChatBIMessageDiagnostic, "after_update")
def _index_diagnostic(mapper, connection, row):
    from ..services.trace_index import index_diagnostic
    index_diagnostic(connection, row)


@event.listens_for(ChatBIMessageDiagnostic, "after_delete")
def _delete_diagnostic_index(mapper, connection, row):
    for model in (ChatBITraceLookup, ChatBIDiagnosticIndexState):
        connection.execute(model.__table__.delete().where(model.message_id == row.message_id))
