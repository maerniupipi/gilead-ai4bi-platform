"""Platform service requests, streaming results and export jobs."""
from typing import Any, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator


class AppInfo(BaseModel):
    name: str = "AI4BI Platform"
    description: str = "数据问答与 PPT、XLSX 导出"
    tags: list[str] = Field(default_factory=lambda: ["ChatBI"])
    mode: Literal["advanced-chat"] = "advanced-chat"
    author_name: str = "ChatBI"


class UserRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    user: str = Field(min_length=1, max_length=320, description="调用服务端提供的用户标识，不依赖员工工号或邮箱格式")


class ExportFileState(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    task_id: UUID
    file_id: UUID | None
    file_type: Literal["ppt", "xlsx"]
    summary_type: Literal["AI_SUMMARY", "FULL_SUMMARY", "ALL"] | None = Field(alias="summaryType")
    status: Literal["pending", "running", "succeeded", "failed"]
    error: str | None
    file_name: str
    file_size: int
    created_at: int
    finished_at: int | None
    expires_at: int | None
    downloadable: bool
    expired: bool


class ExportState(ExportFileState):
    files: list[ExportFileState] = Field(default_factory=list)


class DownloadURL(BaseModel):
    file_id: UUID
    file_name: str
    downloadable: bool
    url: str
    expires_at: int
    file_expires_at: int


class ResultColumn(BaseModel):
    model_config = ConfigDict(extra="allow")
    key: str
    name: str


class TableOutputs(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    columns: list[ResultColumn]
    rows: list[dict[str, Any]] = Field(max_length=50)
    total_rows: int = Field(ge=0)
    truncated: bool
    data_ref: UUID
    can_export: bool
    sortable: bool


class ChartOutputs(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    dimensions: list[ResultColumn] = Field(min_length=1)
    series: list[ResultColumn] = Field(min_length=1)
    rows: list[dict[str, Any]]
    unit: str
    chart_type: Literal["bar", "line", "pie"]
    available_types: list[Literal["bar", "line", "pie"]]
    data_ref: UUID | None


class ProgressNode(BaseModel):
    """data in a finished progress node; start omits terminal fields."""
    id: str
    node_id: str
    node_type: Literal["progress"]
    title: str
    index: int
    created_at: int
    status: Literal["succeeded", "failed"]
    error: str | None
    outputs: None
    elapsed_time: float
    finished_at: int


class ChatRequest(UserRequest):
    query: str = Field(min_length=1, max_length=20000)
    inputs: dict[str, Any] = Field(default_factory=dict, description=(
        "扩展业务参数对象，默认允许任意非保留字段，值支持字符串、数字、布尔、数组、对象和 null；"
        "原样传入分析引擎顶层变量和 features。history_question 由服务端根据 conversation_id 生成，"
        "保留最近五轮历史问题，无历史时为当前是新问题。身份、会话历史、问题及运行目标等保留字段不能覆盖；"
        "部署方可通过非空 CHATBI_ALLOWED_INPUTS 白名单主动限制字段。"))
    response_mode: Literal["streaming"] = "streaming"
    conversation_id: UUID | None = Field(default=None, description=(
        "首轮省略、null 或空字符串；续轮传平台 SSE 返回的会话 UUID，"
        "由服务端读取对应历史并生成最近五轮问题变量 history_question。"))
    auto_generate_name: bool = False

    @field_validator("conversation_id", mode="before")
    @classmethod
    def blank_conversation(cls, value):
        return None if value == "" else value

    @field_validator("query")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("query must not be blank")
        return value.strip()


class ExportRequest(UserRequest):
    conversation_id: UUID
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=128)
    first_question: str | None = Field(default=None, max_length=20000,
        description="Optional naming context from trusted caller's stored conversation; defaults to the platform conversation's first question")


class PPTRequest(ExportRequest):
    summary_type: Literal["AI_SUMMARY", "FULL_SUMMARY", "ALL"] = Field(default="ALL", alias="summaryType")
    message_ids: list[UUID] | None = None

    @field_validator('summary_type', mode='before')
    @classmethod
    def normalize_summary_type(cls, value):
        if value is None or value == '':
            return 'ALL'
        if isinstance(value, str):
            value = value.strip().upper()
            return {'AI': 'AI_SUMMARY', 'SUMMARY': 'FULL_SUMMARY', 'DEFAULT': 'ALL'}.get(value, value)
        return value


class XLSXRequest(ExportRequest):
    message_id: UUID
    data_ref: UUID
