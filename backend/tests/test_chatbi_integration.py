"""Isolated integration contract tests; never connect to business data or an LLM."""
import asyncio
import json
import time
from datetime import datetime, timezone
from io import BytesIO
from types import SimpleNamespace
from urllib.parse import parse_qs, unquote, urlparse
from zipfile import ZipFile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from pptx import Presentation
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.core.middleware import ResponseEnvelopeMiddleware
from app.models.chatbi import TABLES, ChatBIConversation, ChatBIMessage, ChatBIResult, ChatBIExport
from app.models.model_provider import ModelProvider
from app.routers.chatbi.router import router
from app.schemas.chatbi import ChatRequest, PPTRequest, XLSXRequest
from app.services.chatbi import chat, exports
from app.services.chatbi.config import APIError, identity, model_bindings
from app.services.chatbi.summary import AISummaryPPTService

USER = identity("user-001")
OTHER = identity("user-002")


@pytest.fixture
def factory(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "dev")
    monkeypatch.setenv("CHATBI_ENV", "uat")
    monkeypatch.setenv("CHATBI_API_ENABLED", "true")
    monkeypatch.setenv("CHATBI_EXPORT_REQUEST_WORKER_ENABLED", "false")
    monkeypatch.setenv("CHATBI_API_KEY", "app-uat-ttttttttttttttttttttttttttttttttttttttttttt")
    monkeypatch.setenv("CHATBI_AUTOBI_PROJECT_ID", "1")
    monkeypatch.setenv("CHATBI_STORAGE_DIR", str(tmp_path / "files"))
    monkeypatch.setenv("CHATBI_PUBLIC_BASE_URL", "https://files.example.test")
    monkeypatch.setenv("CHATBI_SUMMARY_PROVIDER_ID", "1")
    monkeypatch.setenv("CHATBI_SUMMARY_MODEL", "fake")
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine, tables=[*TABLES, ModelProvider.__table__])
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as db:
        db.add(ModelProvider(id=1, name="isolated summary model", base_url="https://example.test/v1",
                            api_key="test-key", protocol="openai", models='["fake"]', is_active=True))
        db.commit()
    yield factory
    engine.dispose()


async def sample_runner(*args):
    yield {"type": "step_started", "title": "查询数据", "step_id": 16}
    yield {"type": "data_citations", "features": {"data_citations": [{
        "id": 1, "query": "区域销售", "data": [{"region": f"R{i}", "sales": i} for i in range(80)]
    }]}}
    yield {"type": "step_finished", "step_id": 16, "status": "succeeded"}
    yield {"type": "text", "content": "共 80 条数据。"}
    yield {"type": "chart_citations", "features": {"chart_citations": [{"query": "销售图", "chart": {
        "type": "A", "columns": [{"key": "region", "target": "xaxis"}, {"key": "sales", "target": "yaxis"}],
        "data": [{"region": "华东", "sales": 100}, {"region": "华北", "sales": 80}]
    }}]}}


@pytest.mark.parametrize("raw", ['[]', '{"sql_permission_rewrite":{}}', '{"chart_drawing":{"provider_id":0,"model_name":"x"}}'])
def test_model_overrides_cannot_change_permissions_or_accept_invalid_config(monkeypatch, raw):
    monkeypatch.setenv("CHATBI_MODEL_BINDINGS", raw)
    with pytest.raises(APIError) as caught:
        model_bindings()
    assert caught.value.status == 503


def test_runtime_model_override_is_local_and_keeps_identity(monkeypatch):
    from app.services.chatbi.runtime import run_analysis
    from app.services.autobi import lab_runtime
    config = {"model_bindings": {"nl2sql": {"provider_id": 9, "model_name": "original"}},
              "request": {"advanced_config": {"sql_permission_rewrite_config": {"enable": True},
                                                  "nl2sql_config": {"timeout_seconds": 120, "prompt": "SQL"}}}}
    seen = {}
    def build(db, project_id, *, content, features):
        seen.update(features=features)
        return SimpleNamespace(lab_config=json.loads(json.dumps(config)))
    async def stream(db, spec, **kwargs):
        seen["config"] = spec.lab_config
        yield 'data: {"type":"done"}\n\n'
    monkeypatch.setenv("CHATBI_MODEL_BINDINGS", '{"chart_drawing":{"provider_id":1,"model_name":"available"}}')
    monkeypatch.setenv("CHATBI_CHAT_TIMEOUT", "600")
    monkeypatch.setattr(lab_runtime, "build_lab_run_spec_from_project_id", build)
    monkeypatch.setattr(lab_runtime, "stream_lab_native_sse", stream)
    async def run():
        return [e async for e in run_analysis(None, "autobi:23", "sales", {}, "cid", [], USER)]
    asyncio.run(run())
    assert seen["config"]["model_bindings"]["chart_drawing"]["model_name"] == "available"
    assert seen["config"]["model_bindings"]["nl2sql"]["model_name"] == "original"
    advanced = seen["config"]["request"]["advanced_config"]
    assert advanced["sql_permission_rewrite_config"] == {"enable": True}
    assert advanced["nl2sql_config"]["prompt"] == "SQL"
    for key in ("knowledge_rewrite", "nl2sql", "ner_retrieval", "bi_summary", "chart_drawing"):
        assert advanced[f"{key}_config"]["timeout_seconds"] == 600
    assert config["request"]["advanced_config"]["nl2sql_config"]["timeout_seconds"] == 120
    assert seen["features"]["features"]["user_id"] == USER.user_id
    assert "chart_drawing" not in config["model_bindings"]


async def collect(mid, body, factory, runner=sample_runner):
    return [json.loads(s[6:]) async for s in chat.stream_chat(mid, body, USER, factory=factory, runner=runner) if s.startswith("data: ")]


@pytest.mark.parametrize("elapsed,status", [(599, "succeeded"), (601, "failed")])
def test_question_deadline_allows_ten_minutes_then_releases_lock(factory, monkeypatch, elapsed, status):
    clock = {"elapsed": 0}
    monkeypatch.setenv("CHATBI_CHAT_TIMEOUT", "600")
    monkeypatch.setattr(chat, "time", SimpleNamespace(time=time.time, monotonic=lambda: clock["elapsed"]))
    async def delayed(*args):
        clock["elapsed"] = elapsed
        yield {"type": "text", "content": "delayed answer"}
    body = ChatRequest(user=USER.user, query="slow question")
    with factory() as db:
        mid = chat.prepare_chat(db, body, USER)
    events = asyncio.run(collect(mid, body, factory, delayed))
    terminal = next(e for e in events if e["event"] == "workflow_finished")
    assert terminal["data"]["status"] == status
    if status == "failed":
        assert events[-1]["code"] == "timeout"
        assert events[-1]["status"] == 504
    with factory() as db:
        msg = db.get(ChatBIMessage, mid)
        assert msg.status == status
        assert db.get(ChatBIConversation, msg.conversation_id).active_task is None


def analysis(factory, conversation_id=None, query="查看销售"):
    body = ChatRequest(user=USER.user, query=query, conversation_id=conversation_id)
    with factory() as db:
        mid = chat.prepare_chat(db, body, USER)
    events = asyncio.run(collect(mid, body, factory))
    return events, mid


def test_chat_preview_full_snapshot_and_order(factory):
    events, mid = analysis(factory)
    table = next(e for e in events if e["event"] == "node_finished" and e["data"]["node_type"] == "table")["data"]["outputs"]
    assert len(table["rows"]) == 50
    assert table["total_rows"] == 80 and table["truncated"] and not table["sortable"]
    assert table["can_export"]
    assert events[-1]["data"]["status"] == "succeeded"
    assert len({e["message_id"] for e in events}) == 1
    with factory() as db:
        result = db.get(ChatBIResult, table["data_ref"])
        assert len(result.rows) == 80
        message = db.get(ChatBIMessage, mid)
        assert message.status == "succeeded" and message.sequence == 1
        cid = message.conversation_id
    _, next_mid = analysis(factory, cid, "继续分析")
    with factory() as db:
        assert db.get(ChatBIMessage, next_mid).sequence == 2
        with pytest.raises(APIError) as caught:
            chat.prepare_chat(db, ChatRequest(user=OTHER.user, query="x", conversation_id=cid), OTHER)
        assert caught.value.status == 404


@pytest.mark.parametrize("envelope", ["native", "legacy", "workflow"])
def test_final_sql_reaches_stream_and_persisted_answer(factory, envelope):
    from app.services.chatbi.runtime import normalize
    sql = "SELECT city, SUM(sales) AS total\nFROM sales\nWHERE region = 'authorized-region'\nGROUP BY city"
    citation = {"query": "城市销售", "sql": sql}
    payload = {"type": "bailian_sql", **citation}
    if envelope == "legacy":
        payload = {"message": {"type": "sql_citations", "features": json.dumps({"sql_citations": [citation]})}}
    elif envelope == "workflow":
        payload = {"type": "sql_citations", "features": {"sql_citations": [citation]}}
    async def runner(*args):
        yield normalize(payload)
        yield {"type": "text", "content": "销售结果。"}
    body = ChatRequest(user=USER.user, query="城市销售")
    with factory() as db:
        mid = chat.prepare_chat(db, body, USER)
    events = asyncio.run(collect(mid, body, factory, runner))
    sql_nodes = [e for e in events if e["event"] == "node_finished" and e["data"]["node_type"] == "sql"]
    assert len(sql_nodes) == 1
    node = sql_nodes[0]["data"]
    assert node["outputs"] == {"sql": sql, "schema_version": "1.0"}
    assert node["status"] == "succeeded" and node["title"] == "城市销售"
    with factory() as db:
        answer = db.get(ChatBIMessage, mid)
        assert next(c for c in answer.content if c["type"] == "sql")["outputs"]["sql"] == sql
        assert answer.answer == "销售结果。"


def test_empty_sql_does_not_create_result_node(factory):
    async def runner(*args):
        yield {"type": "sql_citations", "features": {"sql_citations": [
            {"sql": None}, {"sql": ""}, {"sql": "  "}, {"sql": "None"},
        ]}}
        yield {"type": "text", "content": "无需查询"}
    body = ChatRequest(user=USER.user, query="hello")
    with factory() as db:
        mid = chat.prepare_chat(db, body, USER)
    events = asyncio.run(collect(mid, body, factory, runner))
    assert not any(e.get("data", {}).get("node_type") == "sql" for e in events)


def test_stop_cancels_running_operation_and_releases_conversation(factory):
    async def scenario():
        started, cancelled = asyncio.Event(), asyncio.Event()
        async def slow(*args):
            try:
                yield {"type": "progress", "content": "查询中"}
                started.set()
                await asyncio.Event().wait()
            finally:
                cancelled.set()
        body = ChatRequest(user=USER.user, query="slow")
        with factory() as db:
            mid = chat.prepare_chat(db, body, USER)
            task_id = db.get(ChatBIMessage, mid).task_id
        consumer = asyncio.create_task(collect(mid, body, factory, slow))
        await started.wait()
        with factory() as db:
            with pytest.raises(APIError):
                chat.stop_chat(db, task_id, OTHER)
            chat.stop_chat(db, task_id, USER)
        events = await asyncio.wait_for(consumer, 3)
        assert cancelled.is_set()
        assert events[-1]["data"]["status"] == "stopped"
        with factory() as db:
            msg = db.get(ChatBIMessage, mid)
            assert msg.status == "stopped"
            assert db.get(ChatBIConversation, msg.conversation_id).active_task is None
    asyncio.run(scenario())


def test_error_never_becomes_success(factory):
    async def fail(*args):
        yield {"type": "progress", "content": "查询中"}
        raise RuntimeError("sensitive upstream failure")
    body = ChatRequest(user=USER.user, query="failure")
    with factory() as db:
        mid = chat.prepare_chat(db, body, USER)
    events = asyncio.run(collect(mid, body, factory, fail))
    assert events[-2]["event"] == "workflow_finished" and events[-2]["data"]["status"] == "failed"
    assert events[-1]["event"] == "error"
    assert "message_end" not in [e["event"] for e in events]
    assert any(e["event"] == "error" for e in events)
    assert "sensitive upstream" not in json.dumps(events)


def test_database_disconnect_and_failed_rollback_keep_terminal_sse(factory, monkeypatch):
    from sqlalchemy.exc import OperationalError

    async def disconnected(db, *args):
        yield {"type": "progress", "content": "查询数据"}
        def broken_rollback():
            raise RuntimeError("Lost connection during rollback")
        monkeypatch.setattr(db, "rollback", broken_rollback)
        raise OperationalError("SELECT 1", {}, Exception("connection lost"))

    body = ChatRequest(user=USER.user, query="database outage")
    with factory() as db:
        mid = chat.prepare_chat(db, body, USER)
    events = asyncio.run(collect(mid, body, factory, disconnected))
    assert events[-2]["event"] == "workflow_finished"
    assert events[-2]["data"]["status"] == "failed"
    assert events[-1]["event"] == "error"
    assert (events[-1]["status"], events[-1]["code"]) == (503, "service_unavailable")
    assert not any(e["event"] == "message_end" for e in events)
    with factory() as db:
        msg = db.get(ChatBIMessage, mid)
        assert msg.status == "failed"
        assert db.get(ChatBIConversation, msg.conversation_id).active_task is None


def test_terminal_persistence_outage_is_a_failed_sse_not_a_truncated_stream(factory):
    from sqlalchemy.exc import OperationalError

    def unavailable_for_updates():
        db = factory()
        execute = db.execute
        def checked_execute(statement, *args, **kwargs):
            if getattr(statement, "is_update", False):
                raise OperationalError("UPDATE", {}, Exception("connection lost"))
            return execute(statement, *args, **kwargs)
        db.execute = checked_execute
        return db

    async def completed(*args):
        yield {"type": "text", "content": "Some analysis"}

    body = ChatRequest(user=USER.user, query="persistence outage")
    with factory() as db:
        mid = chat.prepare_chat(db, body, USER)
    events = asyncio.run(collect(mid, body, unavailable_for_updates, completed))
    assert events[-2]["data"]["status"] == "failed"
    assert events[-1]["event"] == "error" and events[-1]["status"] == 503
    assert not any(e["event"] == "message_end" for e in events)


def test_stop_polling_does_not_query_database_for_every_text_chunk(factory):
    from sqlalchemy import event

    body = ChatRequest(user=USER.user, query="many tokens")
    with factory() as db:
        mid = chat.prepare_chat(db, body, USER)
        engine = db.get_bind()
    polls = []
    def record(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("SELECT chatbi_messages.stop_requested"):
            polls.append(statement)
    async def many_tokens(*args):
        for _ in range(100):
            yield {"type": "text", "content": "a"}
    event.listen(engine, "before_cursor_execute", record)
    try:
        events = asyncio.run(collect(mid, body, factory, many_tokens))
    finally:
        event.remove(engine, "before_cursor_execute", record)
    assert len([e for e in events if e["event"] == "message"]) == 100
    assert 1 <= len(polls) < 10
    assert events[-1]["data"]["status"] == "succeeded"


def test_failed_node_cannot_finish_as_success(factory):
    async def failed_node(*args):
        yield {"type": "step_started", "title": "查询数据", "step_id": "sql"}
        yield {"type": "step_finished", "step_id": "sql", "status": "failed", "error": "query failed"}
    body = ChatRequest(user=USER.user, query="failed node")
    with factory() as db:
        mid = chat.prepare_chat(db, body, USER)
    events = asyncio.run(collect(mid, body, factory, failed_node))
    assert events[-2]["event"] == "workflow_finished" and events[-2]["data"]["status"] == "failed"
    assert events[-1]["event"] == "error"
    assert "message_end" not in [event["event"] for event in events]


def test_sql_execution_does_not_block_stop_requests(factory, monkeypatch):
    import threading
    from app.services.autobi import lab_pipeline_runner as pipeline

    async def scenario():
        release = threading.Event()
        original_thread = threading.get_ident()
        with factory() as db:
            def query(worker_db, knowledge_base_id, sql):
                assert release.wait(1), "SQL blocked the event loop and prevented the stop timer from running"
                assert threading.get_ident() != original_thread
                assert worker_db is not db
                assert worker_db.get_bind() is db.get_bind()
                return {"columns": ["sales"], "rows": [{"sales": 120}], "row_count": 1}
            monkeypatch.setattr(pipeline, "execute_knowledge_base_sql_service", query)
            asyncio.get_running_loop().call_later(0.05, release.set)
            _, response = await pipeline._dispatch_step(db, 16, "query", {}, 1, {"generated_sql": "SELECT 120 AS sales"}, {})
            assert response["rows"] == [{"sales": 120}]
    asyncio.run(scenario())


def test_partial_to_full_reference_upgrade_and_multiple_tables(factory):
    with factory() as db:
        mid = chat.prepare_chat(db, ChatRequest(user=USER.user, query="x"), USER)
        builder = chat.EventBuilder(db, db.get(ChatBIMessage, mid))
        def table(key, rows, total):
            return {"type": "data_citations", "features": {"data_citations": [{"id": key, "data": rows, "total_count": total}]}}
        first = list(builder.accept(table(1, [{"a": 1}], 3)))[-1]["data"]["outputs"]
        last = list(builder.accept(table(1, [{"a": n} for n in range(3)], 3)))[-1]["data"]["outputs"]
        assert first["data_ref"] == last["data_ref"]
        assert not first["can_export"] and last["can_export"]
        list(builder.accept(table(2, [{"b": 8}], 1)))
        assert db.query(ChatBIResult).count() == 2
        assert len(builder.content) == 2


def create_xlsx(factory, key="xlsx1"):
    _, mid = analysis(factory)
    with factory() as db:
        result = db.query(ChatBIResult).filter_by(message_id=mid).one()
        body = XLSXRequest(user=USER.user, conversation_id=result.conversation_id, message_id=mid, data_ref=result.id, idempotency_key=key)
        job = exports.create_export(db, "xlsx", body, USER)
        return job.id, body


@pytest.mark.parametrize("app_env", ["dev", "uat", "prod"])
def test_shared_database_does_not_implicitly_enable_local_export_worker(monkeypatch, app_env):
    monkeypatch.setenv("APP_ENV", app_env)
    monkeypatch.setenv("CHATBI_API_KEY", "configured-service-key")
    monkeypatch.delenv("CHATBI_EXPORT_WORKER_ENABLED", raising=False)
    assert not exports.export_worker_enabled()
    monkeypatch.setenv("CHATBI_EXPORT_WORKER_ENABLED", "false")
    assert not exports.export_worker_enabled()
    monkeypatch.setenv("CHATBI_EXPORT_WORKER_ENABLED", "true")
    assert exports.export_worker_enabled()
    monkeypatch.delenv("CHATBI_API_KEY")
    monkeypatch.delenv("CHATBI_DOWNLOAD_SIGNING_KEY", raising=False)
    assert not exports.export_worker_enabled()
    monkeypatch.setenv("CHATBI_DOWNLOAD_SIGNING_KEY", "managed-keys-use-independent-signing-secret")
    assert exports.export_worker_enabled()


def test_export_releases_database_connections_while_generating_file(factory, monkeypatch):
    job_id, _ = create_xlsx(factory)
    engine = factory.kw["bind"]
    original = exports.generate_xlsx
    checked_out = []

    def generate(*args):
        checked_out.append(engine.pool.checkedout())
        return original(*args)

    monkeypatch.setattr(exports, "generate_xlsx", generate)
    asyncio.run(exports.process_export(job_id, factory=factory))
    assert checked_out == [0]
    with factory() as db:
        assert db.get(ChatBIExport, job_id).status == "succeeded"


def test_full_xlsx_without_watermarks_preserves_idempotency_and_signed_download(factory):
    job_id, body = create_xlsx(factory)
    with factory() as db:
        assert exports.create_export(db, "xlsx", body, USER).id == job_id
        with pytest.raises(APIError):
            exports.create_export(db, "xlsx", body, OTHER)
    assert exports.claim_export(factory) == job_id
    asyncio.run(exports.process_export(job_id, factory=factory))
    with factory() as db:
        job = db.get(ChatBIExport, job_id)
        assert job.status == "succeeded"
        data = exports.file_path(job).read_bytes()
        book = load_workbook(BytesIO(data))
        sheet = book.active
        assert sheet.max_row == 81 and sheet.cell(81, 2).value == 79
        assert all(cell.value is not None for cell in sheet[1])
        assert not sheet.merged_cells
        for section in (sheet.oddHeader, sheet.evenHeader, sheet.firstHeader,
                        sheet.oddFooter, sheet.evenFooter, sheet.firstFooter):
            assert not section.center.text
        with ZipFile(BytesIO(data)) as zipped:
            assert "xl/media/chatbi-user_id.png" not in zipped.namelist()
            assert b"picture" not in zipped.read("xl/worksheets/sheet1.xml")
            assert b"user-001" not in zipped.read("xl/worksheets/sheet1.xml")
        link = exports.download_url(db, job.file_id, USER, "https://ignored.test")
        query = parse_qs(urlparse(link["url"]).query)
        expires, sig = int(query["expires"][0]), query["signature"][0]
        assert exports.signed_file(db, job.file_id, expires, sig).id == job_id
        for attempt in [lambda: exports.signed_file(db, job.file_id, expires + 1, sig),
                        lambda: exports.download_url(db, job.file_id, OTHER, ""),
                        lambda: exports.get_job(db, job.id, OTHER)]:
            with pytest.raises(APIError): attempt()
        job.expires_at = int(time.time()) - 1
        db.commit()
        assert not exports.export_state(job)["downloadable"]
        with pytest.raises(APIError) as caught:
            exports.download_url(db, job.file_id, USER, "")
        assert caught.value.status == 410


@pytest.mark.parametrize("mode", ["FULL_SUMMARY", "AI_SUMMARY"])
def test_both_ppt_variants_export_without_watermarks(factory, monkeypatch, mode):
    async def summary(*args, **kwargs):
        return {"agenda": ["销售趋势", "总结"], "slides": [{"title": "销售趋势", "insights": ["华东销售 100，高于华北的 80。"]}, {"title": "总结", "insights": ["持续观察区域差异。"]}]}
    monkeypatch.setattr(AISummaryPPTService, "build_summary", summary)
    events, _ = analysis(factory)
    with factory() as db:
        body = PPTRequest(user=USER.user, conversation_id=events[0]["conversation_id"], summaryType=mode, idempotency_key=mode)
        job = exports.create_export(db, "ppt", body, USER)
        job_id = job.id
    exports.claim_export(factory)
    asyncio.run(exports.process_export(job_id, factory=factory))
    with factory() as db:
        job = db.get(ChatBIExport, job_id)
        assert job.status == "succeeded", job.error
        prs = Presentation(str(exports.file_path(job)))
        assert len(prs.slides) > 1
        for slide in prs.slides:
            assert all("user-001" not in shape.text for shape in slide.shapes if shape.has_text_frame)


def test_formula_like_cells_stay_text():
    data = exports.generate_xlsx([{"key": "value"}], [{"value": "=HYPERLINK(\"https://example.test\")"}])
    cell = load_workbook(BytesIO(data)).active["A2"]
    assert cell.data_type == "s" and cell.value.startswith("=")












def test_slow_export_queue_poll_does_not_block_http_event_loop(factory, monkeypatch):
    import threading
    release = threading.Event()
    worker_threads = []
    def slow_claim(_factory):
        worker_threads.append(threading.get_ident())
        assert release.wait(1), "Queue poll blocked the event loop"
        return None
    monkeypatch.setattr(exports, "claim_export", slow_claim)
    monkeypatch.setattr(exports, "cleanup_expired_files", lambda _: None)
    async def scenario():
        main_thread = threading.get_ident()
        worker = asyncio.create_task(exports.export_worker(factory=factory))
        asyncio.get_running_loop().call_later(0.05, release.set)
        try:
            await asyncio.sleep(0.1)
            assert worker_threads and all(thread != main_thread for thread in worker_threads)
        finally:
            release.set()
            worker.cancel()
            with pytest.raises(asyncio.CancelledError):
                await worker
    asyncio.run(scenario())


def test_real_workflow_stream_cancels_its_child_node(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import MagicMock
    from app.services.agent_app import workflow_engine as engine
    version = SimpleNamespace(id=1, workflow_json={"nodes": [
        {"id": "start", "data": {"kind": "start", "label": "开始"}},
        {"id": "out", "data": {"kind": "output", "label": "输出"}},
    ], "edges": [{"id": "edge", "source": "start", "target": "out"}]})
    monkeypatch.setattr(engine, "get_version_for_app", lambda *a: version)
    monkeypatch.setattr(engine, "agent_run_trace_set", lambda *a, **k: None)
    monkeypatch.setattr(engine, "save_workflow_trace", lambda *a, **k: None)
    async def scenario():
        started, cancelled = asyncio.Event(), asyncio.Event()
        async def slow(*args):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()
        monkeypatch.setitem(engine._KIND_HANDLERS, "start", slow)
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(name="test")
        iterator = engine.run_agent_workflow_stream(db, 1, 1, {})
        # A running progress event precedes starting the child node. Keep consuming
        # so cancellation actually exercises an in-flight node rather than a paused generator.
        async def consume():
            async for _ in iterator:
                pass
        consumer = asyncio.create_task(consume())
        await asyncio.wait_for(started.wait(), 2)
        consumer.cancel()
        with pytest.raises(asyncio.CancelledError): await consumer
        assert cancelled.is_set()
        await iterator.aclose()
    asyncio.run(scenario())


def test_claims_are_exclusive_and_expired_leases_recover(factory):
    job_id, _ = create_xlsx(factory)
    assert exports.claim_export(factory) == job_id
    assert exports.claim_export(factory) is None
    with factory() as db:
        db.get(ChatBIExport, job_id).lease_until = int(time.time()) - 1
        db.commit()
    assert exports.claim_export(factory) is None
    with factory() as db:
        assert db.get(ChatBIExport, job_id).status == "failed"


def test_http_auth_validation_and_unwrapped_dify_contract(factory, monkeypatch):
    import importlib
    module = importlib.import_module("app.routers.chatbi.router")
    from app.services.chatbi import request_context
    monkeypatch.setattr(module, "stream_chat", lambda mid, body, user, request: chat.stream_chat(mid, body, user, factory=factory, runner=sample_runner))
    app = FastAPI()
    app.include_router(router)
    app.add_middleware(ResponseEnvelopeMiddleware)
    def database():
        with factory() as db: yield db
    app.dependency_overrides[get_db] = database
    with TestClient(app) as client:
        body = {"user": USER.user, "query": "销售", "response_mode": "streaming", "inputs": {}, "conversation_id": ""}
        unauthorized = client.post("/api/service/chat-messages", json=body)
        assert unauthorized.status_code == 401 and unauthorized.json()["code"] == "unauthorized"
        headers = {"Authorization": "Bearer app-uat-ttttttttttttttttttttttttttttttttttttttttttt"}
        invalid = client.post("/api/service/chat-messages", headers=headers, json={**body, "user": " "})
        assert invalid.status_code == 400 and invalid.json()["code"] == "invalid_user"
        forged = client.post("/api/service/chat-messages", headers=headers, json={**body, "inputs": {"features": {"user_id": "user-002"}}})
        assert forged.status_code == 400 and forged.json()["code"] == "invalid_inputs"
        response = client.post("/api/service/chat-messages", headers=headers, json=body)
        assert response.status_code == 200 and "text/event-stream" in response.headers["content-type"]
        events = [json.loads(s[6:]) for s in response.text.split("\n\n") if s.startswith("data: ")]
        assert events[0]["event"] == "workflow_started" and events[-1]["data"]["status"] == "succeeded"
        assert client.post("/api/service/messages/x/feedbacks", headers=headers, json={}).status_code == 404
