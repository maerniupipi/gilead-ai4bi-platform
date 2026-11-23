"""
AutoBI 原子能力 API 请求/响应模型
"""
from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Optional, List, Dict, Any, Union


def _coerce_query_to_str(v: Any) -> str:
    """参考 OpenTrek：query 可为字符串或字符串数组（多行拼接）。"""
    if isinstance(v, list):
        return "\n".join(str(x).strip() for x in v if x is not None)
    return str(v) if v is not None else ""


class ESValueRetrieverRequest(BaseModel):
    """ES表值召回请求（索引 es_kb{knowledge_base_id}_table_value）"""
    query: Union[str, List[str]] = Field(..., description="查询文本，可为字符串或字符串数组")
    top_k: Optional[int] = Field(default=5, ge=1, le=200, description="返回条数，默认 5")
    score_threshold: Optional[float] = Field(
        default=None,
        description="相似度下限（对 ES 归一化分数 0~1）；为空则不过滤",
    )

    @field_validator("query", mode="before")
    @classmethod
    def _normalize_query(cls, v: Any) -> str:
        return _coerce_query_to_str(v)


class ESKnowledgeRetrieverRequest(BaseModel):
    """ES知识词召回请求（索引 es_kb{knowledge_base_id}_knowledge）"""
    query: Union[str, List[str]] = Field(..., description="查询文本，可为字符串或字符串数组")
    top_k: Optional[int] = Field(default=8, ge=1, le=200, description="返回条数，默认 8")
    score_threshold: Optional[float] = Field(
        default=None,
        description="相似度下限（对 ES 归一化分数 0~1）；为空则不过滤",
    )

    @field_validator("query", mode="before")
    @classmethod
    def _normalize_query(cls, v: Any) -> str:
        return _coerce_query_to_str(v)


class SQLTemplateRetrieverRequest(BaseModel):
    """SQL样例召回请求（对齐 OpenTrek icl-template-retriever / 知识库样例库向量域 biSample）"""
    query: str = Field(..., description="自然语言查询")
    top_k: Optional[int] = Field(default=5, ge=1, le=100, description="返回条数，默认 5")
    score_threshold: Optional[float] = Field(
        default=None,
        description="相似度下限（COSINE 度量下越大越相似）；为空则不过滤",
    )


class TableMetaRetrieverRequest(BaseModel):
    """表字段召回请求（对齐 OpenTrek table-meta-retriever / Milvus 域 table_column）"""
    query: str = Field(..., description="查询文本")
    top_k: Optional[int] = Field(default=15, ge=1, le=100, description="返回条数，默认 15")
    score_threshold: Optional[float] = Field(
        default=None,
        description="相似度下限；未传时服务端默认 0.3；传 0 表示不过滤",
    )


class TableValueRetrieverRequest(BaseModel):
    """表值召回请求（Milvus field_type=table_value；可选 ES 回退）"""
    query: str = Field(..., description="查询文本")
    table_name: Optional[str] = Field(default=None, description="指定物理表名(可选)，过滤 field_table")
    top_k: Optional[int] = Field(default=6, ge=1, le=100, description="返回条数，默认 6")
    score_threshold: Optional[float] = Field(
        default=None,
        description="相似度下限（COSINE 度量下越大越相似）；为空则不过滤",
    )


class GlobalValueMetaRetrieverRequest(BaseModel):
    """表值召回(对应字段)请求（Milvus table_value；table_name 表示表名与字段名的组合）"""
    query: str = Field(..., description="查询文本")
    table_name: Optional[str] = Field(
        default=None,
        description=(
            "可选。推荐「表名.字段名」；或「表名&字段名」「表名&&字段名」（与 Milvus field_code 一致）；"
            "仅表名时表示按 field_table 过滤整表"
        ),
    )
    top_k: Optional[int] = Field(default=10, ge=1, le=100, description="返回条数，默认 10")
    score_threshold: Optional[float] = Field(
        default=None,
        description="相似度下限（COSINE）；为空则不过滤",
    )


class MultiGlobalValueMetaRetrieverRequest(BaseModel):
    """多列同值：每列向量与关键词各取 TopK，稳定合并去重，不重排。"""

    query: str = Field(..., description="查询文本")
    table_name: List[str] = Field(
        ...,
        min_length=1,
        description="多项「表名.字段名」（推荐）或「表名&&字段名」等，与 global-value-meta 中单次 table_name 含义相同",
    )
    top_k: Optional[int] = Field(default=10, ge=1, le=100, description="每列每路最多返回条数；向量和关键词去重合并后每列最多 2*top_k")
    score_threshold: Optional[float] = Field(
        default=None,
        description="向量召回阈值（沿用向量库分数）；为空则不过滤，不用于过滤关键词分数",
    )
    keyword_score_threshold: Optional[float] = Field(
        default=None, ge=0, le=1,
        description="关键词分数按该次搜索最大分数归一化后的阈值；独立于向量阈值，为空则不过滤",
    )


class NerRetrieverRequest(BaseModel):
    """NER：按知识库 NER 表中别名包含实体子串检索，输出结构化字段与自然语言摘要"""

    query: str = Field(default="", description="用户问题或上下文，用于生成说明性文案")
    entity: List[str] = Field(
        ...,
        min_length=1,
        description='待解析实体集合，如 ["上海","年份"]',
    )
    top_k: Optional[int] = Field(
        default=20,
        ge=1,
        le=500,
        description="每个实体在库中最多返回的映射行数",
    )


class GenerateSqlRequest(BaseModel):
    """生成 SQL 请求：基于提示词模板和上下文变量生成只读查询 SQL"""

    model_config = ConfigDict(protected_namespaces=())

    query: str = Field(..., description="自然语言问题")
    provider_id: int = Field(..., description="模型供应商 ID")
    model_name: str = Field(..., description="模型名称")
    system_prompt: Optional[str] = Field(
        default="",
        description="系统提示词模板，可使用 {{变量名}} 引用 context 中的值",
    )
    context: Dict[str, Any] = Field(default_factory=dict, description="提示词上下文变量")
    temperature: Optional[float] = Field(default=0.2, ge=0, le=2, description="模型温度")
    max_tokens: Optional[int] = Field(default=2048, ge=1, le=8192, description="最大输出 token")
    top_p: Optional[float] = Field(default=0.9, ge=0, le=1, description="top_p")


class ExecuteSqlRequest(BaseModel):
    """执行 SQL 请求：按知识库关联数据源只读执行 SQL"""

    sql: str = Field(..., description="待执行 SQL，仅允许查询")


class RetrieverResult(BaseModel):
    """召回结果项"""
    score: float = Field(..., description="所属检索路的分数；多列去重保留首次命中的分数，见 metadata.score_type")
    content: str = Field(..., description="召回内容")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="附加元数据")


class ESValueRetrieverResponse(BaseModel):
    """ES表值召回响应"""
    results: List[RetrieverResult] = Field(default_factory=list, description="召回结果列表")
    total: int = Field(default=0, description="结果总数")


class ESKnowledgeRetrieverResponse(BaseModel):
    """ES知识词召回响应"""
    results: List[RetrieverResult] = Field(default_factory=list, description="召回结果列表")
    total: int = Field(default=0, description="结果总数")


class SQLTemplateRetrieverResponse(BaseModel):
    """SQL样例召回响应"""
    results: List[RetrieverResult] = Field(default_factory=list, description="召回结果列表")
    total: int = Field(default=0, description="结果总数")


class TableMetaRetrieverResponse(BaseModel):
    """表字段召回响应"""
    results: List[RetrieverResult] = Field(default_factory=list, description="召回结果列表")
    total: int = Field(default=0, description="结果总数")


class TableValueRetrieverResponse(BaseModel):
    """表值召回响应"""
    results: List[RetrieverResult] = Field(default_factory=list, description="召回结果列表")
    total: int = Field(default=0, description="结果总数")


class GlobalValueMetaRetrieverResponse(BaseModel):
    """表值召回(对应字段)响应"""
    results: List[RetrieverResult] = Field(default_factory=list, description="召回结果列表")
    total: int = Field(default=0, description="结果总数")


class NerRetrieverResponse(BaseModel):
    """NER 原子能力响应"""

    results: List[RetrieverResult] = Field(
        default_factory=list,
        description="每条为一条映射，metadata 含 table_name、field_name、database_name、alias",
    )
    total: int = Field(default=0, description="结果条数")
    narrative: str = Field(default="", description="将所有映射整理后的自然语言说明")


class GenerateSqlResponse(BaseModel):
    """生成 SQL 响应"""

    sql: str = Field(default="", description="生成的 SQL")
    content: str = Field(default="", description="模型原始输出")
    prompt_preview: str = Field(default="", description="提示词预览")


class ExecuteSqlResponse(BaseModel):
    """执行 SQL 响应"""

    sql: str = Field(default="", description="执行的 SQL")
    columns: List[str] = Field(default_factory=list, description="结果列名")
    rows: List[Dict[str, Any]] = Field(default_factory=list, description="结果行")
    row_count: int = Field(default=0, description="返回行数")
