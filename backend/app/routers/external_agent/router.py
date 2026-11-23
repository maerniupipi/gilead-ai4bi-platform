"""External agent chat routes."""
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ...core.database import get_db
from ...schemas.external_agent import ExternalAgentChatRequest
from ...services.agent_app.external_chat import (
    external_agent_chat_stream,
    external_agent_chat_non_stream,
)

router = APIRouter()


@router.post("/agent-chat/sse")
async def external_agent_chat_sse(
    body: ExternalAgentChatRequest,
    db: Session = Depends(get_db),
):
    return StreamingResponse(
        external_agent_chat_stream(db, body),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/agent-chat")
async def external_agent_chat(
    body: ExternalAgentChatRequest,
    db: Session = Depends(get_db),
):
    """非流式调用外部智能体"""
    return await external_agent_chat_non_stream(db, body)
