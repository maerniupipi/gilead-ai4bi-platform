"""
知识库模型 - 管理知识库及其关联的表结构、字段、词条和样例
"""
from sqlalchemy import Column, Integer, BigInteger, String, Text, Boolean, ForeignKey, TIMESTAMP, func
from sqlalchemy.orm import relationship
from ..core.database import Base


class KnowledgeBase(Base):
    """知识库表 - 知识库主表，关联知识接入"""
    __tablename__ = "knowledge_base"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    space_id = Column(Integer, nullable=False, default=1, index=True, comment="所属空间ID")
    name = Column(String(255), nullable=False)
    description = Column(Text)
    knowledge_access_id = Column(Integer, ForeignKey("knowledge_access.id"), nullable=False)
    table_count = Column(Integer, default=0)
    vector_progress = Column(Integer, default=0)
    vectorization_status = Column(String(20), default='pending')  # pending, processing, cancelling, cancelled, completed, failed
    vector_collection_name = Column(String(100))
    # 向量化步骤配置 (JSON格式: {"field_vectorization": true, "value_vectorization": true, ...})
    vectorization_steps = Column(Text)
    # 当前执行的步骤
    current_vectorization_step = Column(String(50))
    # 脏数据标记 - 知识词条变更后标记
    knowledge_term_dirty = Column(Boolean, default=False)
    # 脏数据标记 - 样例库变更后标记
    sample_library_dirty = Column(Boolean, default=False)
    status = Column(Boolean, default=True)
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    updated_at = Column(TIMESTAMP, server_default=func.current_timestamp(), onupdate=func.current_timestamp())
    is_deleted = Column(Boolean, default=False)

    knowledge_access = relationship("KnowledgeAccess")
    kb_table_structures = relationship("KbTableStructure", back_populates="knowledge_base", cascade="all, delete-orphan")
    kb_knowledge_terms = relationship("KbKnowledgeTerm", back_populates="knowledge_base", cascade="all, delete-orphan")
    kb_sample_libraries = relationship("KbSampleLibrary", back_populates="knowledge_base", cascade="all, delete-orphan")
    kb_ner_rows = relationship("KbNerRow", back_populates="knowledge_base", cascade="all, delete-orphan")


class KbNerRow(Base):
    """知识库 NER 映射行（按 Excel Sheet 分组，单库最多 1000 条）"""

    __tablename__ = "kb_ner_row"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    space_id = Column(Integer, nullable=False, default=1, index=True, comment="所属空间ID")
    knowledge_base_id = Column(Integer, ForeignKey("knowledge_base.id"), nullable=False, index=True)
    sheet_name = Column(String(64), nullable=False)
    table_name = Column(String(50), nullable=False)
    field_name = Column(String(50), nullable=False)
    standard_name = Column(String(50), nullable=False, default="")
    alias = Column(String(50), nullable=False, default="")
    remark = Column(String(50), nullable=False, default="")
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    updated_at = Column(TIMESTAMP, server_default=func.current_timestamp(), onupdate=func.current_timestamp())

    knowledge_base = relationship("KnowledgeBase", back_populates="kb_ner_rows")


class KbTableStructure(Base):
    """知识库表结构关联表 - 记录知识库选择的表"""
    __tablename__ = "kb_table_structure"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    knowledge_base_id = Column(Integer, ForeignKey("knowledge_base.id"), nullable=False)
    table_structure_id = Column(Integer, ForeignKey("table_structure.id"), nullable=False)
    table_name = Column(String(255), nullable=False)
    table_alias = Column(String(255))
    is_vectorized = Column(Boolean, default=True)
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    updated_at = Column(TIMESTAMP, server_default=func.current_timestamp(), onupdate=func.current_timestamp())

    knowledge_base = relationship("KnowledgeBase", back_populates="kb_table_structures")
    table_structure = relationship("TableStructure")
    kb_table_fields = relationship("KbTableField", back_populates="kb_table_structure", cascade="all, delete-orphan")


class KbTableField(Base):
    """知识库表字段关联表 - 记录知识库选择的字段"""
    __tablename__ = "kb_table_field"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    kb_table_structure_id = Column(Integer, ForeignKey("kb_table_structure.id"), nullable=False)
    table_field_id = Column(Integer, ForeignKey("table_field.id"), nullable=False)
    field_name = Column(String(255), nullable=False)
    field_alias = Column(String(255))
    field_type = Column(String(50), nullable=False)
    is_vectorized = Column(Boolean, default=True)
    is_enabled = Column(Boolean, default=True)
    is_value_vectorized = Column(Boolean, default=False)  # 表值是否已向量化
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    updated_at = Column(TIMESTAMP, server_default=func.current_timestamp(), onupdate=func.current_timestamp())

    kb_table_structure = relationship("KbTableStructure", back_populates="kb_table_fields")
    table_field = relationship("TableField")


class KbKnowledgeTerm(Base):
    """知识库词条关联表 - 记录知识库引用的词条"""
    __tablename__ = "kb_knowledge_term"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    knowledge_base_id = Column(Integer, ForeignKey("knowledge_base.id"), nullable=False)
    knowledge_term_id = Column(Integer, ForeignKey("knowledge_term.id"), nullable=False)
    # 缓存字段 - 用于快速显示，实际值从 knowledge_term 关联获取
    term_name_cache = Column(String(255), nullable=True, comment="词条名称缓存")
    term_value_cache = Column(Text, nullable=True, comment="词条值缓存")
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    updated_at = Column(TIMESTAMP, server_default=func.current_timestamp(), onupdate=func.current_timestamp())

    knowledge_base = relationship("KnowledgeBase", back_populates="kb_knowledge_terms")
    knowledge_term = relationship("KnowledgeTerm", back_populates="kb_knowledge_term_refs")

    @property
    def term_name(self):
        """从引用的 knowledge_term 获取词条名称，如果不存在则返回缓存"""
        if self.knowledge_term and not self.knowledge_term.is_deleted:
            return self.knowledge_term.term_name
        return self.term_name_cache

    @property
    def term_value(self):
        """从引用的 knowledge_term 获取词条值，如果不存在则返回缓存"""
        if self.knowledge_term and not self.knowledge_term.is_deleted:
            return self.knowledge_term.term_value
        return self.term_value_cache


class KbSampleLibrary(Base):
    """知识库样例关联表 - 记录知识库引用的样例"""
    __tablename__ = "kb_sample_library"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    knowledge_base_id = Column(Integer, ForeignKey("knowledge_base.id"), nullable=False)
    sample_id = Column(Integer, ForeignKey("sample_library.id"), nullable=False)
    # 缓存字段 - 用于快速显示，实际值从 sample_library 关联获取
    sample_name_cache = Column(String(255), nullable=True, comment="样例名称缓存")
    sample_content_cache = Column(Text, nullable=True, comment="样例内容缓存")
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    updated_at = Column(TIMESTAMP, server_default=func.current_timestamp(), onupdate=func.current_timestamp())

    knowledge_base = relationship("KnowledgeBase", back_populates="kb_sample_libraries")
    sample_library = relationship("SampleLibrary", back_populates="kb_sample_library_refs")

    @property
    def sample_name(self):
        """从引用的 sample_library 获取样例名称，如果不存在则返回缓存"""
        if self.sample_library and not self.sample_library.is_deleted:
            return self.sample_library.sample_name
        return self.sample_name_cache

    @property
    def sample_content(self):
        """从引用的 sample_library 获取样例内容，如果不存在则返回缓存"""
        if self.sample_library and not self.sample_library.is_deleted:
            return self.sample_library.sql_content
        return self.sample_content_cache
