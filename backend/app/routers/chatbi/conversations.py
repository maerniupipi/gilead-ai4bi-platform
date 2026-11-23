"""Conversation browsing for all logged-in platform users."""
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ...core.database import get_db
from ...schemas.chatbi_conversations import ConversationDetail, ConversationList
from ...services.chatbi.conversation_admin import conversation_detail, list_conversations
from .admin import KeyManagementRoute, key_admin


class ConversationManagementRoute(KeyManagementRoute):
    validation_message = "对话管理请求字段不符合约定"


router = APIRouter(prefix="/api/chatbi/conversations", tags=["ChatBI 对话管理"],
                   dependencies=[Depends(key_admin)], route_class=ConversationManagementRoute)


@router.get("", response_model=ConversationList)
def conversations(
    key_id: str | None = Query(None, max_length=36), user: str | None = Query(None, max_length=320),
    keyword: str | None = Query(None, max_length=200, description="问题、答案、Session ID 或关联实验室/工作流 TraceID"),
    status: Literal["running", "succeeded", "failed", "stopped", "empty"] | None = None,
    kind: Literal["chat"] | None = None,
    start_at: int | None = Query(None, ge=0), end_at: int | None = Query(None, ge=0),
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), db: Session = Depends(get_db),
):
    return list_conversations(db, key_id=key_id, user=user, keyword=keyword, status=status, kind=kind,
                              start_at=start_at, end_at=end_at, page=page, page_size=page_size)


@router.get("/{conversation_id}", response_model=ConversationDetail)
def detail(conversation_id: UUID, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
           db: Session = Depends(get_db)):
    return conversation_detail(db, conversation_id, page=page, page_size=page_size)
