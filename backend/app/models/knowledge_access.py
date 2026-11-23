from sqlalchemy import Column, Integer, String, Text, Boolean, ForeignKey, TIMESTAMP, func
from sqlalchemy.orm import relationship
from ..core.database import Base


class KnowledgeAccess(Base):
    __tablename__ = "knowledge_access"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    space_id = Column(Integer, nullable=False, default=1, index=True, comment="所属空间ID")
    name = Column(String(255), nullable=False)
    description = Column(Text)
    data_source_id = Column(Integer, ForeignKey("data_source.id"), nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    updated_at = Column(TIMESTAMP, server_default=func.current_timestamp(), onupdate=func.current_timestamp())
    is_deleted = Column(Boolean, default=False)

    data_source = relationship("DataSource", back_populates="knowledge_accesses")
    table_structures = relationship("TableStructure", back_populates="knowledge_access", cascade="all, delete-orphan")
    knowledge_terms = relationship("KnowledgeTerm", back_populates="knowledge_access", cascade="all, delete-orphan")
    sample_libraries = relationship("SampleLibrary", back_populates="knowledge_access", cascade="all, delete-orphan")


class TableStructure(Base):
    __tablename__ = "table_structure"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    space_id = Column(Integer, nullable=False, default=1, index=True, comment="所属空间ID")
    knowledge_access_id = Column(Integer, ForeignKey("knowledge_access.id"), nullable=False)
    table_name = Column(String(255), nullable=False)
    table_alias = Column(String(255))
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    updated_at = Column(TIMESTAMP, server_default=func.current_timestamp(), onupdate=func.current_timestamp())

    knowledge_access = relationship("KnowledgeAccess", back_populates="table_structures")
    table_fields = relationship("TableField", back_populates="table_structure", cascade="all, delete-orphan")


class TableField(Base):
    __tablename__ = "table_field"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    table_structure_id = Column(Integer, ForeignKey("table_structure.id"), nullable=False)
    field_name = Column(String(255), nullable=False)
    field_alias = Column(String(255))
    field_type = Column(String(50), nullable=False)
    is_enabled = Column(Boolean, default=True)
    is_vectorized = Column(Boolean, default=False)
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    updated_at = Column(TIMESTAMP, server_default=func.current_timestamp(), onupdate=func.current_timestamp())

    table_structure = relationship("TableStructure", back_populates="table_fields")


class KnowledgeTerm(Base):
    __tablename__ = "knowledge_term"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    space_id = Column(Integer, nullable=False, default=1, index=True, comment="所属空间ID")
    knowledge_access_id = Column(Integer, ForeignKey("knowledge_access.id"), nullable=False)
    term_name = Column(String(255), nullable=False)
    term_value = Column(Text, nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    updated_at = Column(TIMESTAMP, server_default=func.current_timestamp(), onupdate=func.current_timestamp())
    is_deleted = Column(Boolean, default=False)

    knowledge_access = relationship("KnowledgeAccess", back_populates="knowledge_terms")
    kb_knowledge_term_refs = relationship("KbKnowledgeTerm", back_populates="knowledge_term", cascade="all, delete-orphan")


class SampleLibrary(Base):
    __tablename__ = "sample_library"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    space_id = Column(Integer, nullable=False, default=1, index=True, comment="所属空间ID")
    knowledge_access_id = Column(Integer, ForeignKey("knowledge_access.id"), nullable=False)
    sample_name = Column(String(255), nullable=False)
    sql_content = Column(Text, nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    updated_at = Column(TIMESTAMP, server_default=func.current_timestamp(), onupdate=func.current_timestamp())
    is_deleted = Column(Boolean, default=False)

    knowledge_access = relationship("KnowledgeAccess", back_populates="sample_libraries")
    kb_sample_library_refs = relationship("KbSampleLibrary", back_populates="sample_library", cascade="all, delete-orphan")
