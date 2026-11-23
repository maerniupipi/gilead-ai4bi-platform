"""External agent chat schemas."""
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class ExternalAgentChatRequest(BaseModel):
    app_id: int = Field(..., description="智能体应用 ID")
    version_id: Optional[int] = Field(None, description="智能体版本 ID；为空时使用输出版本")
    message: str = Field(..., min_length=1, description="用户问题")
    conversation_id: Optional[str] = Field(None, description="外部会话 ID")
    caller: Optional[str] = Field(None, description="调用方标识")
    inputs: Dict[str, Any] = Field(default_factory=dict, description="附加输入变量")
    stream: bool = True
