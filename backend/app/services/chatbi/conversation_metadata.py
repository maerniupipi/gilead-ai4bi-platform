"""Persist service Key and opaque user attribution for conversation browsing."""
import time
from ...models.chatbi import ChatBIConversationContext
from .config import APIError


def record_conversation_context(db, conversation_id, user):
    if not user.credential_id:
        return
    row = db.get(ChatBIConversationContext, conversation_id)
    if row and row.key_id and row.key_id != user.credential_id:
        raise APIError(404, "conversation_not_exists", "会话不存在")
    if not row:
        row = ChatBIConversationContext(conversation_id=conversation_id)
        db.add(row)
    row.key_id, row.user_id = user.credential_id, user.user_id
    row.attribution_source, row.updated_at = "request", int(time.time())
