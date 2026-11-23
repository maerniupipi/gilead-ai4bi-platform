from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime

from .knowledge_access import KnowledgeAccess


# 向量化步骤定义
VECTORIZATION_STEPS = [
    {"key": "field_vectorization", "name": "字段向量化", "order": 1},
    {"key": "value_vectorization", "name": "值向量化", "order": 2},
    {"key": "table_field_to_es", "name": "值存ES", "order": 3},
    {"key": "knowledge_term_to_es", "name": "知识词存ES", "order": 4},
    {"key": "sample_library_to_es", "name": "样例库向量化", "order": 5},
]


class KnowledgeBaseBase(BaseModel):
    space_id: Optional[int] = Field(1, description="所属空间ID")
    name: str = Field(..., description="知识库名称")
    description: Optional[str] = Field(None, description="描述")
    knowledge_access_id: int = Field(..., description="关联的知识接入ID")
    status: Optional[bool] = Field(True, description="知识库状态（1-启用，0-禁用）")


class KnowledgeBaseCreate(KnowledgeBaseBase):
    pass


class KnowledgeBaseUpdate(KnowledgeBaseBase):
    space_id: Optional[int] = Field(None, description="所属空间ID")
    name: Optional[str] = Field(None, description="知识库名称")
    knowledge_access_id: Optional[int] = Field(None, description="关联的知识接入ID")


class VectorizationSteps(BaseModel):
    """向量化步骤配置"""
    field_vectorization: bool = Field(True, description="字段向量化")
    value_vectorization: bool = Field(True, description="值向量化")
    table_field_to_es: bool = Field(False, description="值存ES")
    knowledge_term_to_es: bool = Field(False, description="知识词存ES")
    sample_library_to_es: bool = Field(False, description="样例库向量化")


class KnowledgeBase(KnowledgeBaseBase):
    id: int
    space_id: int
    table_count: int
    vector_progress: int
    vectorization_status: str = Field('pending', description="向量化状态: pending, processing, cancelling, cancelled, completed, failed")
    vector_collection_name: Optional[str] = Field(None, description="向量库集合名称")
    vectorization_steps: Optional[str] = Field(None, description="向量化步骤配置(JSON)")
    current_vectorization_step: Optional[str] = Field(None, description="当前向量化步骤")
    knowledge_term_dirty: bool = Field(False, description="知识词条脏数据标记")
    sample_library_dirty: bool = Field(False, description="样例库脏数据标记")
    created_at: datetime
    updated_at: datetime
    is_deleted: bool

    class Config:
        from_attributes = True


class KbTableStructureBase(BaseModel):
    table_structure_id: int = Field(..., description="关联的表结构ID")
    is_vectorized: Optional[bool] = Field(True, description="是否向量化")


class KbTableStructureCreate(KbTableStructureBase):
    pass


class KbTableStructureUpdate(BaseModel):
    is_vectorized: Optional[bool] = Field(None, description="是否向量化")


class KbTableFieldBase(BaseModel):
    is_vectorized: Optional[bool] = Field(True, description="是否向量化")
    is_enabled: Optional[bool] = Field(True, description="是否启用")


class KbTableFieldCreate(BaseModel):
    table_field_id: int = Field(..., description="关联的表字段ID")
    is_vectorized: Optional[bool] = Field(True, description="是否向量化")
    is_enabled: Optional[bool] = Field(True, description="是否启用")


class KbTableFieldUpdate(KbTableFieldBase):
    pass


class KbTableField(BaseModel):
    id: int
    kb_table_structure_id: int
    table_field_id: int
    field_name: str
    field_alias: Optional[str]
    field_type: str
    is_vectorized: bool
    is_enabled: bool
    is_value_vectorized: bool = Field(False, description="表值是否已向量化")
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class KbTableStructure(BaseModel):
    id: int
    knowledge_base_id: int
    table_structure_id: int
    table_name: str
    table_alias: Optional[str]
    is_vectorized: bool
    created_at: datetime
    updated_at: datetime
    kb_table_fields: List[KbTableField] = Field(default_factory=list)

    class Config:
        from_attributes = True


class KbKnowledgeTermBase(BaseModel):
    knowledge_term_id: int = Field(..., description="关联的知识词条ID")


class KbKnowledgeTermCreate(KbKnowledgeTermBase):
    pass


class KbKnowledgeTerm(BaseModel):
    id: int
    knowledge_base_id: int
    knowledge_term_id: int
    term_name_cache: Optional[str] = Field(None, description="词条名称缓存")
    term_value_cache: Optional[str] = Field(None, description="词条值缓存")
    # 从关联的 knowledge_term 获取实际值
    term_name: Optional[str] = Field(None, description="词条名称（来自知识接入）")
    term_value: Optional[str] = Field(None, description="词条值（来自知识接入）")
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class KbSampleLibraryBase(BaseModel):
    sample_id: int = Field(..., description="关联的样例ID")


class KbSampleLibraryCreate(KbSampleLibraryBase):
    pass


class KbSampleLibrary(BaseModel):
    id: int
    knowledge_base_id: int
    sample_id: int
    sample_name_cache: Optional[str] = Field(None, description="样例名称缓存")
    sample_content_cache: Optional[str] = Field(None, description="样例内容缓存")
    # 从关联的 sample_library 获取实际值
    sample_name: Optional[str] = Field(None, description="样例名称（来自知识接入）")
    sample_content: Optional[str] = Field(None, description="样例内容（来自知识接入）")
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class VectorizeRequest(BaseModel):
    """向量化请求"""
    mode: str = Field("incremental", description="向量化模式: incremental 或 full")
    steps: VectorizationSteps = Field(default_factory=VectorizationSteps, description="要执行的向量化步骤")


class KnowledgeBaseDetail(KnowledgeBase):
    knowledge_access: KnowledgeAccess
    kb_table_structures: List[KbTableStructure] = Field(default_factory=list)
    kb_knowledge_terms: List[KbKnowledgeTerm] = Field(default_factory=list)
    kb_sample_libraries: List[KbSampleLibrary] = Field(default_factory=list)


class KnowledgeBaseExecuteSqlRequest(BaseModel):
    sql: str = Field(..., description="待执行的 SQL（仅允许查询，禁止 INSERT/UPDATE/DELETE）")


class KnowledgeBaseExecuteSqlResponse(BaseModel):
    columns: List[str] = Field(default_factory=list, description="结果列名")
    rows: List[Dict[str, Any]] = Field(default_factory=list, description="结果行（字典列表）")
    row_count: int = Field(0, description="返回行数")
