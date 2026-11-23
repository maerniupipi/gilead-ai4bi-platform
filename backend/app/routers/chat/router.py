"""
聊天路由
"""
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ...core.database import get_db
from ...schemas.chat import ChatRequest, ChatResponse
from ...services.chat import ChatService

router = APIRouter(prefix="/api/chat", tags=["聊天"])


@router.post("/send", response_model=ChatResponse)
async def send_chat(chat_request: ChatRequest, db: Session = Depends(get_db)):
    """普通聊天（非流式）"""
    return await ChatService.send_chat(db, chat_request)


@router.post("/stream")
async def stream_chat(chat_request: ChatRequest, db: Session = Depends(get_db)):
    """流式聊天"""
    return StreamingResponse(
        ChatService.stream_chat(db, chat_request),
        media_type="text/event-stream",
    )
