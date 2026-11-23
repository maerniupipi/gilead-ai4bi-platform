"""Vectorization manifest for full/incremental sync."""
from sqlalchemy import Column, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.sql import func

from ..core.database import Base


class KbVectorManifest(Base):
    """Records source items written to vector stores or ES indexes."""

    __tablename__ = "kb_vector_manifest"
    __table_args__ = (
        UniqueConstraint("kb_id", "domain", "item_key", name="uq_kb_vector_manifest_item"),
    )

    id = Column(Integer, primary_key=True, index=True)
    kb_id = Column(Integer, nullable=False, index=True)
    domain = Column(String(50), nullable=False, index=True)
    table_name = Column(String(255), nullable=True, index=True)
    field_code = Column(String(500), nullable=True, index=True)
    item_key = Column(String(512), nullable=False)
    embedding_hash = Column(String(64), nullable=True)
    payload_hash = Column(String(64), nullable=True)
    item_value = Column(Text, nullable=True)
    last_seen_run_id = Column(String(64), nullable=False, index=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
