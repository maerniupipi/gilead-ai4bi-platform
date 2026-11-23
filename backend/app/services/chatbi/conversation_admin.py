"""Read-only admin queries; no dependence on the current Key binding for history."""
from fastapi import HTTPException
from sqlalchemy import Text, cast, func, or_, select
from uuid import UUID

from ...models.chatbi import ChatBIAPIKey, ChatBIConversation, ChatBIConversationContext, ChatBIMessage
from ...models.chatbi import ChatBIMessageDiagnostic, ChatBITraceLookup, ChatBIDiagnosticIndexState
from ..trace_index import unindexed_condition
from .diagnostics import diagnostic_view


def _base_query(db):
    # Correlated, indexed lookups let filtering/pagination operate on the
    # conversation table without materializing a GROUP BY of all messages.
    messages = ChatBIMessage
    def scalar(expression):
        return select(expression).where(messages.conversation_id == ChatBIConversation.id).correlate(ChatBIConversation).scalar_subquery()

    def endpoint(column, descending=False):
        order = messages.sequence.desc() if descending else messages.sequence.asc()
        return select(column).where(messages.conversation_id == ChatBIConversation.id).order_by(
            order, messages.created_at.desc() if descending else messages.created_at.asc(),
            messages.id.desc() if descending else messages.id.asc()).limit(1).correlate(ChatBIConversation).scalar_subquery()

    count = scalar(func.count(messages.id))
    active = func.coalesce(scalar(func.max(func.coalesce(messages.finished_at, messages.created_at))), ChatBIConversation.created_at)
    status = func.coalesce(endpoint(messages.status, True), "empty")
    query = db.query(ChatBIConversation, ChatBIConversationContext, ChatBIAPIKey,
        endpoint(messages.query), status, count, active).outerjoin(
        ChatBIConversationContext, ChatBIConversationContext.conversation_id == ChatBIConversation.id
    ).outerjoin(ChatBIAPIKey, ChatBIAPIKey.id == ChatBIConversationContext.key_id)
    return query, active, status


def _summary(row):
    conversation, context, key, question, status, count, active = row
    return {"id": conversation.id, "key_id": context.key_id if context else None,
        "key_name": key.name if key else "Key 已删除" if context and context.key_id else "未归属历史",
        "key_hint": key.key_hint if key else None, "environment": key.environment if key else None,
        "key_enabled": bool(key.enabled) if key else None,
        "user_id": context.user_id if context else None,
        "attribution_source": context.attribution_source if context else "unassigned",
        "kind": "chat",
        "runtime": conversation.runtime, "first_question": (question or "")[:200],
        "message_count": int(count), "status": status, "created_at": conversation.created_at,
        "last_active_at": int(active)}


def _contains(value):
    return "%" + value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def list_conversations(db, *, key_id=None, user=None, keyword=None, status=None, kind=None,
                       start_at=None, end_at=None, page=1, page_size=20):
    query, active, status_column = _base_query(db)
    if key_id == "unassigned":
        query = query.filter(ChatBIConversationContext.key_id.is_(None))
    elif key_id:
        try:
            parsed_key = str(UUID(key_id))
        except ValueError:
            raise HTTPException(400, "Key 筛选值必须是有效 ID")
        query = query.filter(ChatBIConversationContext.key_id == parsed_key)
    if user and user.strip():
        pattern = _contains(user.strip())
        query = query.filter(ChatBIConversationContext.user_id.ilike(pattern, escape="\\"))
    if keyword and keyword.strip():
        text = keyword.strip()
        pattern = _contains(text)
        predicates = [ChatBIMessage.query.ilike(pattern, escape="\\"),
                      ChatBIMessage.answer.ilike(pattern, escape="\\")]
        try:
            trace_id = str(UUID(text))
        except ValueError:
            trace_id = None
        if trace_id:
            trace_pattern = _contains(trace_id)
            legacy_traces = db.query(ChatBIMessageDiagnostic.message_id).outerjoin(ChatBIDiagnosticIndexState,
                ChatBIDiagnosticIndexState.message_id == ChatBIMessageDiagnostic.message_id
            ).filter(unindexed_condition()).filter(or_(
                cast(ChatBIMessageDiagnostic.traces, Text).ilike(trace_pattern, escape="\\"),
                cast(ChatBIMessageDiagnostic.invocations, Text).ilike(trace_pattern, escape="\\")))
            trace_messages = db.query(ChatBITraceLookup.message_id).filter(ChatBITraceLookup.trace_id == trace_id).union(legacy_traces)
            predicates.append(ChatBIMessage.id.in_(trace_messages))
        matching = db.query(ChatBIMessage.conversation_id).filter(or_(*predicates))
        query = query.filter(or_(ChatBIConversation.id.ilike(pattern, escape="\\"), ChatBIConversation.id.in_(matching)))
    if status:
        query = query.filter(status_column == status)
    if start_at is not None:
        query = query.filter(active >= start_at)
    if end_at is not None:
        if start_at is not None and end_at < start_at:
            raise HTTPException(400, "结束时间不能早于开始时间")
        query = query.filter(active <= end_at)
    total = query.count()
    rows = query.order_by(active.desc(), ChatBIConversation.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {"items": [_summary(row) for row in rows], "total": total, "page": page, "page_size": page_size}


def _preview_content(content):
    preview = []
    for item in content or []:
        if not isinstance(item, dict) or item.get("type") not in {"sql", "table", "chart"}:
            continue
        result = {"type": item["type"], "title": str(item.get("title") or ""), "outputs": dict(item.get("outputs") or {})}
        output = result["outputs"]
        visible_columns = []
        for field in ("columns", "dimensions", "series"):
            columns = output.get(field)
            if isinstance(columns, list):
                remaining = max(0, 30 - len(visible_columns))
                output[field] = columns[:remaining]
                if len(columns) > remaining:
                    output["columns_truncated"] = True
                visible_columns.extend(output[field])
        rows = result["outputs"].get("rows")
        if isinstance(rows, list):
            keys = {column["key"] for column in visible_columns if isinstance(column, dict) and "key" in column}
            result["outputs"]["rows"] = [{key: value for key, value in row.items() if key in keys} if isinstance(row, dict) and keys else row for row in rows[:50]]
            if len(rows) > 50:
                result["outputs"]["truncated"] = True
        preview.append(result)
    return preview


def conversation_detail(db, conversation_id, *, page=1, page_size=20):
    query, _, _ = _base_query(db)
    row = query.filter(ChatBIConversation.id == str(conversation_id)).first()
    if not row:
        raise HTTPException(404, "会话不存在")
    summary = _summary(row)
    messages = db.query(ChatBIMessage).filter_by(conversation_id=str(conversation_id)).order_by(
        ChatBIMessage.sequence, ChatBIMessage.created_at, ChatBIMessage.id
    ).offset((page - 1) * page_size).limit(page_size).all()
    diagnostics = {row.message_id: row for row in db.query(ChatBIMessageDiagnostic).filter(
        ChatBIMessageDiagnostic.message_id.in_([message.id for message in messages])).all()}
    return {"conversation": summary, "total": summary["message_count"], "page": page, "page_size": page_size,
        "messages": [{"id": msg.id, "task_id": msg.task_id, "sequence": msg.sequence, "query": msg.query,
            "answer": msg.answer, "status": msg.status, "error": msg.error,
            "content": _preview_content(msg.content), "created_at": msg.created_at, "finished_at": msg.finished_at,
            "diagnostics": diagnostic_view(diagnostics.get(msg.id))}
            for msg in messages]}
