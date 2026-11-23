"""AutoBI 实验室对话状态（存 MySQL，与 Redis 追踪分离）。"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class AutobiLabChatStateUpsert(BaseModel):
    """与前端 AutobiLaboratoryContent 中 conversations 结构一致（不含 turns[].steps）。"""

    conversations: List[Dict[str, Any]] = Field(default_factory=list)
    active_conversation_id: Optional[str] = None


class AutobiLabChatStateOut(BaseModel):
    conversations: List[Dict[str, Any]] = Field(default_factory=list)
    active_conversation_id: Optional[str] = None
