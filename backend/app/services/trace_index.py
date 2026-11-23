"""Indexed Trace ID lookup, with incremental migration of historical records."""
import json
import re

from sqlalchemy import or_

from ..models.chatbi import ChatBITraceLookup, ChatBIDiagnosticIndexState, ChatBIMessageDiagnostic

_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)


def index_diagnostic(connection, row):
    for model in (ChatBITraceLookup, ChatBIDiagnosticIndexState):
        connection.execute(model.__table__.delete().where(model.message_id == row.message_id))
    ids = {value.lower() for value in _UUID.findall(json.dumps([row.traces, row.invocations], ensure_ascii=False))}
    if ids:
        connection.execute(ChatBITraceLookup.__table__.insert(), [
            {"trace_id": trace_id, "message_id": row.message_id} for trace_id in ids])
    connection.execute(ChatBIDiagnosticIndexState.__table__.insert().values(
        message_id=row.message_id, updated_at=row.updated_at))


def unindexed_condition():
    return or_(ChatBIDiagnosticIndexState.message_id.is_(None),
               ChatBIDiagnosticIndexState.updated_at != ChatBIMessageDiagnostic.updated_at)


def backfill_trace_index(factory, batch_size=100):
    with factory() as db:
        rows = db.query(ChatBIMessageDiagnostic).outerjoin(ChatBIDiagnosticIndexState,
            ChatBIDiagnosticIndexState.message_id == ChatBIMessageDiagnostic.message_id
        ).filter(unindexed_condition()).order_by(ChatBIMessageDiagnostic.message_id).limit(batch_size).all()
        for row in rows:
            # Lock and refresh the diagnostic so a terminal update cannot race
            # an older migration snapshot and replace its newer index.
            current = db.query(ChatBIMessageDiagnostic).filter_by(message_id=row.message_id).with_for_update().populate_existing().first()
            if current is not None:
                index_diagnostic(db.connection(), current)
        db.commit()
        return len(rows)
