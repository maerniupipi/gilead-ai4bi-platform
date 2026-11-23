"""智能体平台 Schema"""
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class AgentFolderCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)


class AgentFolderUpdate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)


class AgentFolderMoveBody(BaseModel):
    direction: Literal["up", "down"]


class AgentFolderItem(BaseModel):
    id: int
    name: str
    sort_order: int = 0
    is_system: bool = False
    created_at: datetime

    class Config:
        from_attributes = True


class AgentAppVersionOut(BaseModel):
    id: int
    name: str
    status: str
    mode: str
    is_output: bool
    created_at: datetime

    class Config:
        from_attributes = True


class AgentAppCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128, description="应用名称")
    icon: str = Field(
        default="*",
        max_length=32,
        description="图标；入库前会规范为最多 4 个 BMP 字符（过滤补充平面字符，兼容 utf8 列）",
    )
    description: Optional[str] = Field(None, max_length=500, description="描述")
    folder_id: Optional[int] = Field(None, description="所属文件夹；缺省使用系统默认文件夹")
    owner_display_name: Optional[str] = Field(
        None,
        max_length=128,
        description="创建者展示名；由前端根据当前登录用户传入",
    )
    api_token: Optional[str] = Field(None, max_length=128, description="对外调用 token")


class AgentAppUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=128, description="应用名称")
    icon: Optional[str] = Field(
        None,
        max_length=32,
        description="图标；入库前会规范为最多 4 个 BMP 字符",
    )
    description: Optional[str] = Field(None, max_length=500, description="描述")
    folder_id: Optional[int] = Field(None, description="移动到其它文件夹")
    api_token: Optional[str] = Field(None, max_length=128, description="对外调用 token；空字符串表示不修改")


class WorkflowUndoStack(BaseModel):
    """撤销栈：与前端 history 对齐；服务端写入 Redis 时截断为最多 10 步"""

    states: List[dict] = Field(default_factory=list, description="每步 {nodes, edges}")
    index: int = Field(0, ge=0, description="当前指针")


class WorkflowSnapshot(BaseModel):
    nodes: List[Dict[str, Any]]
    edges: List[Dict[str, Any]]


class AgentVersionCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=64, description="版本名称，如 v2.0")
    clone_from_version_id: Optional[int] = Field(
        None, description="可选；从该版本复制 workflow_json 快照到新版本（新版本为「设计中」）"
    )
    workflow: Optional[WorkflowSnapshot] = Field(None, description="可选；将导入画布与新版本一并保存，与克隆互斥")
    undo_stack: Optional[WorkflowUndoStack] = None


class SetOutputVersionBody(BaseModel):
    version_id: int = Field(..., description="作为输出版本的记录 ID")


class AgentAppSummary(BaseModel):
    id: int
    folder_id: int
    name: str
    icon: str
    description: Optional[str]
    owner_display_name: Optional[str] = None
    api_token_configured: bool = False
    created_at: datetime
    updated_at: datetime


class AgentAppDetail(BaseModel):
    id: int
    folder_id: int
    name: str
    icon: str
    description: Optional[str]
    owner_display_name: Optional[str] = None
    api_token_configured: bool = False
    created_at: datetime
    updated_at: datetime
    versions: List[AgentAppVersionOut] = []


class AgentInputParam(BaseModel):
    name: str
    type: str = "STRING"
    required: bool = False
    description: Optional[str] = None
    default_value: Optional[Any] = None
    source_type: Optional[str] = None
    constant_value: Optional[Any] = None


class AgentOutputParam(BaseModel):
    name: str
    type: str = "STRING"
    description: Optional[str] = None


class AgentVersionParamsOut(BaseModel):
    input_params: List[AgentInputParam] = []
    output_params: List[AgentOutputParam] = []


class WorkflowPutBody(BaseModel):
    nodes: List[Any] = Field(default_factory=list)
    edges: List[Any] = Field(default_factory=list)
    expected_rev: int = Field(0, ge=0, description="上次 GET 的 workflow_rev，乐观锁")
    undo_stack: Optional[WorkflowUndoStack] = None


class WorkflowGetOut(BaseModel):
    workflow: Optional[dict] = Field(None, description="{nodes, edges}，无则前端用默认画布")
    workflow_rev: int
    undo_stack: Optional[WorkflowUndoStack] = None


class WorkflowRunBody(BaseModel):
    """执行工作流（同步 JSON）。"""

    inputs: dict = Field(default_factory=dict, description="与 userInput 节点字段 variable 对应")


class WorkflowRunOut(BaseModel):
    run_id: str
    trace_id: str = Field(..., description="与 run_id 一致，便于与实验室 trace 概念对齐")
    output: Optional[str] = None
    status: str = Field(..., description="running（已入队，详情轮询 GET trace）| done | error")
    error: Optional[str] = None
    elapsed_ms: int = 0


# --- AI 创建助手 ---


class AiCreatorModelConfig(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    provider_id: int = Field(..., description="模型供应商 ID")
    model_name: str = Field(..., description="模型名")


class AiChatMessage(BaseModel):
    role: str = Field(..., description="user 或 assistant")
    content: str = Field(default="", description="文本内容；assistant 可为结构化 JSON 字符串")


class ReplyOption(BaseModel):
    id: str
    label: str
    description: Optional[str] = None
    is_other: bool = False


class ParamSchemaItem(BaseModel):
    key: str
    label: str
    description: Optional[str] = None
    type: str = "string"
    required: bool = True
    placeholder: Optional[str] = None
    default: Optional[str] = None


class ToolCallLog(BaseModel):
    tool: str
    args: Dict[str, Any] = Field(default_factory=dict)
    status: str = Field(..., description="running | success | failed")
    summary: str = ""
    result_preview: List[Dict[str, Any]] = Field(default_factory=list)
    error: Optional[str] = None


class AiChatRequest(BaseModel):
    session_id: str = Field(..., min_length=8)
    phase: str = Field(
        ...,
        description="WELCOME | EXPLORE | CLARIFY | DESIGN | PARAMS | CONFIRM",
    )
    messages: List[AiChatMessage] = Field(default_factory=list)
    collected_info: Dict[str, Any] = Field(default_factory=dict)
    creator_model: AiCreatorModelConfig = Field(..., description="对话所用 LLM 供应商与模型")
    workflow_design: Optional[Dict[str, Any]] = None
    filled_params: Dict[str, Any] = Field(default_factory=dict)
    tool_cache: Dict[str, Any] = Field(default_factory=dict)


class AiChatResponse(BaseModel):
    session_id: str
    phase: str
    next_phase: Optional[str] = None
    thinking: str = ""
    reply_type: str = Field(
        ...,
        description="text | options | workflow_preview | params_form | confirm",
    )
    content: str = ""
    options: List[ReplyOption] = Field(default_factory=list)
    workflow_design: Optional[Dict[str, Any]] = None
    params_schema: List[ParamSchemaItem] = Field(default_factory=list)
    collected_info_update: Dict[str, Any] = Field(default_factory=dict)
    tool_calls: List[ToolCallLog] = Field(default_factory=list)
    parse_error: Optional[str] = None
    workflow_json: Optional[Dict[str, Any]] = Field(
        None, description="CONFIRM 后可选返回，供前端直接保存"
    )


class AiCreatorBuildWorkflowBody(BaseModel):
    workflow_design: Dict[str, Any]
    filled_params: Dict[str, Any] = Field(default_factory=dict)


class AiCreatorBuildWorkflowOut(BaseModel):
    workflow: Dict[str, Any]
