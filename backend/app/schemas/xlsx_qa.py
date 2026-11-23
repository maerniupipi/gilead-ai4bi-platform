"""
XLSX 表格智能问答工具 · DTO（Pydantic）

命名遵守 snake_case 与后端 ORM / 前端一致。
"""
from __future__ import annotations

from typing import Any, List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# 模块
# ---------------------------------------------------------------------------

class XlsxQaModuleCreate(BaseModel):
    name: str = Field(..., max_length=128)
    description: Optional[str] = Field(None, max_length=500)
    llm_provider_id: Optional[int] = None
    llm_model: Optional[str] = None
    language: Optional[str] = Field(None, max_length=16)  # auto|zh|en|ja|ko|fr|de|es|pt|ar|ru


class XlsxQaModuleUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=128)
    description: Optional[str] = Field(None, max_length=500)
    llm_provider_id: Optional[int] = None
    llm_model: Optional[str] = None
    language: Optional[str] = Field(None, max_length=16)


class XlsxQaColumnMeta(BaseModel):
    """单列元信息。raw_header 保留原 xlsx 表头（可能含中文）；column_name 是物理列名。"""

    raw_header: str
    column_name: str
    column_type: str  # BIGINT | DOUBLE | DATETIME | TINYINT | VARCHAR | TEXT
    sample: List[Any] = Field(default_factory=list)
    distinct: Optional[int] = None


class XlsxQaSheetInfo(BaseModel):
    """单个 Sheet 的元信息 + 独立表理解。"""

    id: int
    document_id: int
    sheet_index: int
    sheet_name: str
    data_table_name: str
    total_rows: int = 0
    total_columns: int = 0
    columns: List[XlsxQaColumnMeta] = Field(default_factory=list)
    understanding_md: Optional[str] = None
    suggested_questions: List[str] = Field(default_factory=list)
    status: str = "pending"
    parse_error: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class XlsxQaDocumentInfo(BaseModel):
    id: int
    module_id: int
    file_name: str
    file_size: int
    sheet_name: Optional[str] = None
    data_table_name: Optional[str] = None
    total_rows: int = 0
    total_columns: int = 0
    columns: List[XlsxQaColumnMeta] = Field(default_factory=list)
    understanding_md: Optional[str] = None
    suggested_questions: List[str] = Field(default_factory=list)
    status: str
    parse_error: Optional[str] = None
    sheet_count: int = 0
    sheets: List[XlsxQaSheetInfo] = Field(default_factory=list)
    is_primary: bool = True
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class XlsxQaModuleSummary(BaseModel):
    """模块列表页用 —— 不展开完整字段清单。"""

    id: int
    name: str
    description: Optional[str] = None
    owner_display_name: Optional[str] = None
    llm_provider_id: Optional[int] = None
    llm_model: Optional[str] = None
    language: Optional[str] = None  # auto|zh|en|ja|ko|fr|de|es|pt|ar|ru
    has_document: bool = False
    primary_document_file_name: Optional[str] = None
    primary_document_status: Optional[str] = None
    conversation_count: int = 0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class XlsxQaModuleDetail(XlsxQaModuleSummary):
    """模块详情（含所有文件 + Sheet 信息）。"""

    primary_document: Optional[XlsxQaDocumentInfo] = None
    documents: List[XlsxQaDocumentInfo] = Field(default_factory=list)
    module_understanding_md: Optional[str] = None
    all_sheets_ready: bool = False


class XlsxQaShareIssueRequest(BaseModel):
    """生成或复用分享 token；rotate=true 时作废旧链接。"""

    rotate: bool = False


class XlsxQaShareIssueOut(BaseModel):
    token: str
    share_public_base_url: Optional[str] = Field(
        None,
        description="服务端 XLSX_QA_SHARE_PUBLIC_BASE_URL，供前端拼完整分享 URL",
    )


# ---------------------------------------------------------------------------
# 会话 / 消息
# ---------------------------------------------------------------------------

class XlsxQaConversationCreate(BaseModel):
    title: Optional[str] = Field(None, max_length=255)


class XlsxQaConversationInfo(BaseModel):
    id: int
    module_id: int
    title: str
    active_sheet_ids: Optional[List[int]] = None
    message_count: int = 0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class XlsxQaConversationSheetUpdate(BaseModel):
    """更新会话关联的 Sheet 范围。"""

    active_sheet_ids: List[int]


class XlsxQaSubQuestionResult(BaseModel):
    id: str
    question: str
    purpose: Optional[str] = ""
    sql: str = ""
    sql_status: str = "pending"  # pending | running | ok | error
    error: Optional[str] = None
    columns: List[str] = Field(default_factory=list)
    rows: List[List[Any]] = Field(default_factory=list)
    total_rows: int = 0


class XlsxQaChartSpec(BaseModel):
    """图表展示 spec。前端根据 chart_type 选择渲染方式。

    - chart_type: bar | line | pie | table | none
    - source_subquestion_id: 取某个子问题的结果表作为底数；为空时由前端按 columns/rows 直接渲染
    - dimension_field / metric_fields: 对应结果表 columns 中的列名
    """

    subquestion_id: Optional[str] = None          # 唯一标识，用于 primary/secondary 分组
    role: Optional[str] = None                     # "primary" | "secondary"
    chart_type: str = "table"
    title: Optional[str] = ""
    explain: Optional[str] = ""
    source_subquestion_id: Optional[str] = None
    dimension_field: Optional[str] = None
    metric_fields: List[str] = Field(default_factory=list)
    # 兜底：允许直接给出 chart 用的 columns + rows（当 LLM 觉得需要重组时）
    columns: List[str] = Field(default_factory=list)
    rows: List[List[Any]] = Field(default_factory=list)


class XlsxQaAssistantExtras(BaseModel):
    """assistant 消息的 extras_json 结构。"""

    plan_summary: Optional[str] = None
    subquestions: List[XlsxQaSubQuestionResult] = Field(default_factory=list)
    summary_markdown: Optional[str] = None
    follow_up_questions: List[str] = Field(default_factory=list)
    stage_timings: Optional[dict] = None
    chart: Optional[XlsxQaChartSpec] = None          # 主图（向后兼容）
    charts: List[XlsxQaChartSpec] = Field(default_factory=list)  # 全部图（含主图+辅图）
    primary_chart_id: Optional[str] = None            # 指向 charts 中某项的 subquestion_id


class XlsxQaMessageInfo(BaseModel):
    id: int
    conversation_id: int
    role: str
    content: Optional[str] = None
    status: str
    extras: Optional[XlsxQaAssistantExtras] = None
    created_at: Optional[str] = None


class XlsxQaAskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    # 允许前端覆盖模块默认的模型
    llm_provider_id: Optional[int] = None
    llm_model: Optional[str] = None


# ---------------------------------------------------------------------------
# 文档预览 / 下载
# ---------------------------------------------------------------------------

class XlsxQaPreviewOut(BaseModel):
    columns: List[str]
    rows: List[List[Any]]
    total_rows: int
    truncated: bool


class XlsxQaDownloadOut(BaseModel):
    url: str
    expires_in: int


# ---------------------------------------------------------------------------
# 高级设置：提示词
# ---------------------------------------------------------------------------

class XlsxQaPromptsConfig(BaseModel):
    """模块可自定义的提示词集合。任一字段为 None/空 → 用系统默认。"""

    plan_system: Optional[str] = None
    text_to_sql_system: Optional[str] = None
    summary_system: Optional[str] = None
    chart_system: Optional[str] = None


class XlsxQaPromptsConfigOut(BaseModel):
    """GET 接口返回：当前生效值 + 系统默认值，便于前端做"是否被覆盖"判断。"""

    current: XlsxQaPromptsConfig
    defaults: XlsxQaPromptsConfig


# ---------------------------------------------------------------------------
# 导出 PPT
# ---------------------------------------------------------------------------

class XlsxQaExportPptRequest(BaseModel):
    """PPT 导出请求。message_ids 为空时导出全部 assistant 消息。"""
    message_ids: Optional[List[int]] = None
    template_id: str = Field("executive", max_length=32)
    include_chart: bool = True
    include_subquestions: bool = True


class XlsxQaPptExportAsyncResponse(BaseModel):
    """异步导出 PPT 的立即响应。"""
    history_id: int
    status: str = "generating"


class XlsxQaPptHistoryOut(BaseModel):
    """PPT 导出历史记录响应体。"""
    id: int
    module_id: int
    conversation_id: int
    conversation_title: str
    template_id: str
    status: str  # generating | ready | failed
    status_message: Optional[str] = None
    progress_messages: List[str] = []
    error_message: Optional[str] = None
    file_size: Optional[int] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class XlsxQaPptTemplateOut(BaseModel):
    """PPT 模板响应体。"""

    id: str
    name: str
    description: str = ""
    layout: str
    colors: dict
    layout_config: Optional[dict] = None
    is_builtin: bool = False
    sort_order: int = 0


# ---------------------------------------------------------------------------
# 知识追加（采纳用户识别到的别名/映射）
# ---------------------------------------------------------------------------

class XlsxQaKnowledgeItem(BaseModel):
    """单条知识条目。description 最多 100 字。"""

    alias: str = Field(..., max_length=200)
    maps_to: str = Field("", max_length=200)
    column_hint: Optional[str] = Field(None, max_length=100)
    description: str = Field("", max_length=100)


class XlsxQaKnowledgeAppendRequest(BaseModel):
    """用户点击"采纳"时，携带编辑后的 items 追加到表理解。"""

    module_id: int
    sheet_id: Optional[int] = None
    knowledge_items: List[XlsxQaKnowledgeItem] = Field(..., min_length=1)


class XlsxQaKnowledgeAppendOut(BaseModel):
    """追加成功后的表理解 MD（供前端刷新右侧展示）。"""

    understanding_md: str
    sheet_id: Optional[int] = None


# ---------------------------------------------------------------------------
# Sheet 级操作
# ---------------------------------------------------------------------------

class XlsxQaSheetRegenerateOut(BaseModel):
    """重新生成 Sheet 理解后的结果。"""

    understanding_md: str
    suggested_questions: List[str] = Field(default_factory=list)


class XlsxQaSheetUnderstandingUpdate(BaseModel):
    """手动编辑 Sheet 表理解内容。"""
    understanding_md: str = Field(..., min_length=0, max_length=50000)
