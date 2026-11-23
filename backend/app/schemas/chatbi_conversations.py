from typing import Any
from pydantic import BaseModel


class ConversationSummary(BaseModel):
    id: str
    key_id: str | None
    key_name: str
    key_hint: str | None
    environment: str | None
    key_enabled: bool | None
    user_id: str | None
    attribution_source: str
    kind: str
    runtime: str
    first_question: str
    message_count: int
    status: str
    created_at: int
    last_active_at: int


class ConversationList(BaseModel):
    items: list[ConversationSummary]
    total: int
    page: int
    page_size: int


class ConversationTurn(BaseModel):
    id: str
    task_id: str
    sequence: int
    query: str
    answer: str
    status: str
    error: str | None
    content: list[dict[str, Any]]
    created_at: int
    finished_at: int | None
    diagnostics: dict[str, Any] | None = None


class ConversationDetail(BaseModel):
    conversation: ConversationSummary
    messages: list[ConversationTurn]
    total: int
    page: int
    page_size: int
