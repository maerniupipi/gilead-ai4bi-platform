"""Upgrade the previous service schema without rewriting conversation evidence."""
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.chatbi import TABLES, ChatBIMessage, ChatBIMessageDiagnostic, ChatBITraceLookup, ChatBIDiagnosticIndexState
from app.services.trace_index import backfill_trace_index
from scripts.init_chatbi_tables import initialize_service_tables


def test_existing_service_schema_adds_indexes_and_backfills_without_losing_evidence(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'upgrade.db'}")
    new_tables = {ChatBITraceLookup.__table__, ChatBIDiagnosticIndexState.__table__}
    Base.metadata.create_all(engine, tables=[table for table in TABLES if table not in new_tables])
    index = next(index for index in ChatBIMessage.__table__.indexes if index.name == "ix_chatbi_message_conversation_sequence")
    index.drop(bind=engine)
    trace = "11111111-1111-4111-8111-111111111111"
    message = "22222222-2222-4222-8222-222222222222"
    with engine.begin() as connection:
        connection.execute(ChatBIMessageDiagnostic.__table__.insert().values(message_id=message,
            request={"source":"before-update"}, execution={"status":"succeeded"},
            traces=[{"trace_id":trace}], invocations=[], updated_at=1))
    initialize_service_tables(bind=engine)
    initialize_service_tables(bind=engine)
    assert {table.name for table in new_tables}.issubset(inspect(engine).get_table_names())
    assert index.name in {item["name"] for item in inspect(engine).get_indexes("chatbi_messages")}
    factory = sessionmaker(engine)
    assert backfill_trace_index(factory) == 1
    assert backfill_trace_index(factory) == 0
    with factory() as db:
        row = db.get(ChatBIMessageDiagnostic, message)
        assert row.request == {"source":"before-update"} and row.execution == {"status":"succeeded"}
        assert row.traces == [{"trace_id":trace}]
        assert db.get(ChatBITraceLookup, (trace, message)) is not None
        replacement = "33333333-3333-4333-8333-333333333333"
        row.traces, row.updated_at = [{"trace_id":replacement}], 2
        db.commit()
        assert db.get(ChatBITraceLookup, (trace, message)) is None
        assert db.get(ChatBITraceLookup, (replacement, message)) is not None
    engine.dispose()
