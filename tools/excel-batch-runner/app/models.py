"""Validated configuration and row-level state."""
from dataclasses import asdict, dataclass, field
from typing import Literal
from urllib.parse import urlsplit
from uuid import uuid4
import math
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

TERMINAL_ROWS = {"success", "failed", "skipped", "invalid", "cancelled", "interrupted"}
SPLIT_FORMATS = {"split", "split_trace"}
CURRENT_OUTPUT_FORMAT = "split_trace"


class RunConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    url: str = "http://localhost:8000/api/external/agent-chat/sse"
    app_id: int = Field(default=1, gt=0)
    version_id: int = Field(default=1, gt=0)
    caller: str = Field(default="agent-platform-debug", min_length=1, max_length=200)
    channel: str = Field(default="api-docs", max_length=200)
    concurrency: int = Field(default=3, ge=1, le=32)
    connect_timeout: float = Field(default=15, gt=0, le=3600)
    read_timeout: float = Field(default=120, gt=0, le=86400)
    total_timeout: float = Field(default=600, gt=0, le=86400)
    headers: dict[str, str] = Field(default_factory=dict, repr=False)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value):
        value = value.strip()
        parsed = urlsplit(value)
        if (parsed.scheme not in {"http", "https"} or not parsed.hostname
                or parsed.username or parsed.password or parsed.fragment or parsed.query
                or any(c.isspace() for c in value)):
            raise ValueError("接口地址必须为无内嵌认证、查询参数或片段的 HTTP/HTTPS URL")
        try:
            parsed.port
        except ValueError:
            raise ValueError("接口端口无效") from None
        return value

    @field_validator("headers")
    @classmethod
    def validate_headers(cls, value):
        blocked = {"host", "content-length", "transfer-encoding", "connection",
                   "accept", "content-type"}
        for key, item in value.items():
            if (not re.fullmatch(r"[!#$%&'*+\-.^_~|0-9A-Za-z]+", key)
                    or key.lower() in blocked or "\r" in item or "\n" in item):
                raise ValueError("请求头名称或内容无效，不能覆盖传输协议头")
            try:
                item.encode("ascii")
            except UnicodeEncodeError:
                raise ValueError("自定义请求头值必须为 ASCII") from None
        return value


class Selection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    upload_id: str
    sheets: list[str] = Field(min_length=1)
    start_row: int = Field(default=2, ge=1, le=1048576)
    overwrite: bool = False


class OpenWorkbookRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str = Field(min_length=1, max_length=4096)
    start_row: int = Field(default=2, ge=1, le=1048576)


class StartRequest(Selection):
    config: RunConfig = Field(default_factory=RunConfig)


@dataclass
class RowResult:
    sheet: str
    row: int
    question: str
    row_id: str = field(default_factory=lambda: uuid4().hex)
    conversation_id: str = field(default_factory=lambda: uuid4().hex)
    status: str = "pending"
    output: str = ""
    output_format: str = "trace"  # Missing on historical rows; new API tasks use split_trace.
    sql: str = ""
    answer: str = ""
    lab_trace_ids: list[str] = field(default_factory=list)
    workflow_trace_ids: list[str] = field(default_factory=list)
    error: str = ""
    elapsed: float = 0
    event_count: int = 0
    export_warning: str = ""

    def to_dict(self, include_output=True):
        result = asdict(self)
        if not include_output:
            for key in ("output", "sql", "answer"):
                result.pop(key)
        return result
