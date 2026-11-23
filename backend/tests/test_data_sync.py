"""Offline synchronization queue, cron, ingestion and authorization regressions."""
import asyncio
from dataclasses import replace
from datetime import datetime, timezone
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi import FastAPI, HTTPException
import httpx
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.models.data_sync import DataSyncTask, DataSyncRun, DataSyncEvent
from app.schemas.data_sync import SyncTaskUpdate
from app.services.data_sync import cron, loader, pipeline, service, settings
from app.services.data_sync.scheduler import execute_claimed


TASKS = {
    "catalog": {"name": "产品目录", "base_url": "https://source.example.test/records", "target_table": "catalog",
                "headers_env": "DATA_SYNC_HEADERS", "min_rows": 1, "page_size": 2},
    "orders": {"name": "订单", "base_url": "https://source.example.test/orders", "target_table": "orders"},
}


@pytest.fixture
def config(tmp_path):
    return settings.SyncConfig.from_env("catalog", {
        "DATA_SYNC_TASKS": json.dumps(TASKS),
        "DATA_SYNC_DATABASE_URL": "postgresql+psycopg2://sync:secret@db.example/test",
        "DATA_SYNC_HEADERS": '{"Authorization":"Bearer private-token"}',
        "DATA_SYNC_TMP_DIR": str(tmp_path),
    })


@pytest.fixture
def factory(tmp_path, monkeypatch, config):
    monkeypatch.setenv("DATA_SYNC_TASKS", json.dumps(TASKS))
    engine = create_engine(f"sqlite:///{tmp_path / 'sync.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine, tables=[DataSyncTask.__table__, DataSyncRun.__table__, DataSyncEvent.__table__])
    factory = sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(settings.SyncConfig, "from_env", classmethod(lambda cls, key, env=None: replace(config, table_key=key)))
    with factory() as db:
        service.ensure_tasks(db)
    yield factory
    engine.dispose()


def stamp(value):
    return int(datetime.fromisoformat(value).timestamp())


@pytest.mark.parametrize("expression,zone,after,expected", [
    ("0 2 * * *", "Asia/Shanghai", "2026-10-22T17:59:00+00:00", "2026-10-22T18:00:00+00:00"),
    ("*/15 * * * *", "UTC", "2026-10-22T01:15:00+00:00", "2026-10-22T01:30:00+00:00"),
    ("0 0 29 2 *", "UTC", "2026-10-22T00:00:00+00:00", "2028-02-29T00:00:00+00:00"),
    ("0 0 1 * 0", "UTC", "2026-10-22T00:00:00+00:00", "2026-10-25T00:00:00+00:00"),
    ("30 2 * * *", "America/New_York", "2026-03-08T05:00:00+00:00", "2026-03-09T06:30:00+00:00"),
    ("30 1 * * *", "America/New_York", "2026-11-01T05:40:00+00:00", "2026-11-01T06:30:00+00:00"),
    ("0 2 * * 7", "UTC", "2026-10-22T00:00:00+00:00", "2026-10-25T02:00:00+00:00"),
])
def test_cron(expression, zone, after, expected):
    assert cron.next_run(expression, zone, stamp(after)) == stamp(expected)


@pytest.mark.parametrize("value", ["* * *", "60 2 * * *", "*/0 * * * *", "0 0 31 2 *", "0 0 * * 9", "x * * * *"])
def test_invalid_cron(value):
    with pytest.raises(ValueError):
        cron.next_run(value)


def test_configuration_no_credentials_in_status_or_repr(monkeypatch, config):
    assert "secret" not in repr(config) and "private-token" not in repr(config)
    monkeypatch.setenv("DATA_SYNC_TASKS", json.dumps(TASKS))
    monkeypatch.delenv("DATA_SYNC_DATABASE_URL", raising=False)
    status = settings.configuration_status("catalog")
    assert not status["ready"] and "DATA_SYNC_DATABASE_URL" in status["message"]
    for url in ["mysql://u:p@db/test", "not a URL"]:
        with pytest.raises(ValueError, match="psycopg2"):
            settings.SyncConfig.from_env("catalog", {"DATA_SYNC_DATABASE_URL": url, "DATA_SYNC_TASKS": json.dumps(TASKS)})


def test_manual_run_single_ownership_progress_finish(factory):
    with factory() as db:
        run = service.enqueue(db, "catalog", requested_by=42)
    with factory() as db, pytest.raises(HTTPException) as error:
        service.enqueue(db, "catalog")
    assert error.value.status_code == 409
    assert service.claim_next(factory, "worker1") == run["id"]
    assert service.claim_next(factory, "worker2") is None
    service.record_progress(factory, run["id"], "worker1", stage="fetching", page_no=2, fetched_rows=100, message="第2页")
    assert service.finish_run(factory, run["id"], "worker1", "succeeded", count=100)
    with factory() as db:
        detail = service.run_detail(db, run["id"])
        assert detail["run"]["progress_percent"] == 100
        assert detail["run"]["requested_by"] == 42
        assert len(detail["events"]) == 2
        assert db.get(DataSyncTask, "catalog").active_run_id is None
    assert not service.finish_run(factory, run["id"], "worker2", "failed", error="stale")


def test_two_sessions_cannot_enqueue_same_table(factory):
    # Hold a stale task object in one session to exercise CAS rather than identity-map checks.
    with factory() as first, factory() as second:
        service.get_task(first, "catalog")
        service.get_task(second, "catalog")
        service.enqueue(first, "catalog")
        with pytest.raises(HTTPException):
            service.enqueue(second, "catalog")
    with factory() as db:
        assert db.query(DataSyncRun).count() == 1


def test_concurrent_enqueue_and_claim_have_one_winner(factory):
    from concurrent.futures import ThreadPoolExecutor
    def enqueue():
        with factory() as db:
            try:
                return service.enqueue(db, "catalog")["id"]
            except HTTPException as error:
                assert error.status_code == 409
                return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(lambda _: enqueue(), range(2)))
    assert sum(value is not None for value in ids) == 1
    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(lambda owner: service.claim_next(factory, owner), ["first", "second"]))
    assert sum(value is not None for value in claims) == 1
    assert next(value for value in claims if value) == next(value for value in ids if value)


def test_schedule_defaults_disabled_and_enabling_validated(factory):
    with factory() as db:
        assert all(not task["schedule_enabled"] for task in service.list_tasks(db))
        updated = service.update_task(db, "catalog", SyncTaskUpdate(name="组织同步", schedule_enabled=True,
            cron_expression="*/15 * * * *", timezone="Asia/Shanghai"))
        assert updated["next_run_at"]
        with pytest.raises(HTTPException):
            service.update_task(db, "catalog", SyncTaskUpdate(name="组织", schedule_enabled=True, cron_expression="bad"))


def test_due_schedule_once_and_busy_skip_once(factory):
    now = stamp("2026-10-22T01:00:00+00:00")
    with factory() as db:
        task = db.get(DataSyncTask, "catalog")
        task.schedule_enabled, task.next_run_at = True, now
        db.commit()
    service.enqueue_due(factory, now)
    service.enqueue_due(factory, now)
    with factory() as db:
        assert db.query(DataSyncRun).count() == 1
        task = db.get(DataSyncTask, "catalog")
        assert task.next_run_at > now
        active = task.active_run_id
        task.next_run_at = now
        db.commit()
    service.enqueue_due(factory, now)
    service.enqueue_due(factory, now)
    with factory() as db:
        assert db.query(DataSyncRun).count() == 2
        assert db.query(DataSyncRun).filter_by(status="skipped").count() == 1
        assert db.get(DataSyncTask, "catalog").active_run_id == active


def test_dispatcher_keeps_due_snapshot_when_other_worker_advances_schedule(factory, monkeypatch):
    now = stamp("2026-10-22T01:00:00+00:00")
    expiring_factory = sessionmaker(factory.kw["bind"], expire_on_commit=True)
    with factory() as db:
        for key in ["catalog", "orders"]:
            task = db.get(DataSyncTask, key)
            task.schedule_enabled, task.next_run_at = True, now
        db.commit()
    original = service.enqueue
    calls = []
    def competing_dispatcher(db, key, **kwargs):
        if not calls:
            from sqlalchemy import update
            db.execute(update(DataSyncTask).where(DataSyncTask.id != key).values(next_run_at=now + 86400)
                       .execution_options(synchronize_session=False))
            db.commit()
        calls.append(key)
        return original(db, key, **kwargs)
    monkeypatch.setattr(service, "enqueue", competing_dispatcher)
    service.enqueue_due(expiring_factory, now)
    with factory() as db:
        assert db.query(DataSyncRun).count() == 1
        assert len(calls) == 2


def test_future_schedule_cannot_be_enqueued_early(factory):
    with factory() as db:
        assert service.enqueue(db, "catalog", scheduled_for=1001, now=1000) is None
        assert db.query(DataSyncRun).count() == 0


def test_expired_run_never_resurrects_or_releases_new_owner(factory):
    now = stamp("2026-10-22T01:00:00+00:00")
    with factory() as db:
        run = service.enqueue(db, "catalog", now=now)
    service.claim_next(factory, "old", now=now)
    assert service.renew_lease(factory, run["id"], "old", now=now + 10)
    service.expire_runs(factory, now=now + 200)
    with factory() as db:
        next_job = service.enqueue(db, "catalog", now=now + 201)
        assert db.get(DataSyncRun, run["id"]).status == "interrupted"
    assert not service.finish_run(factory, run["id"], "old", "succeeded", count=1, now=now + 202)
    with factory() as db:
        assert db.get(DataSyncTask, "catalog").active_run_id == next_job["id"]


def test_lost_worker_cannot_write_progress(factory):
    with factory() as db:
        job = service.enqueue(db, "catalog")
    service.claim_next(factory, "worker")
    with pytest.raises(RuntimeError, match="租约"):
        service.record_progress(factory, job["id"], "intruder", stage="fetching", fetched_rows=1)


def test_worker_outcome_and_secrets(factory, config):
    with factory() as db:
        job = service.enqueue(db, "catalog")
    service.claim_next(factory, "worker")
    def failing(cfg, progress, run_id):
        progress(stage="fetching", page_no=1, fetched_rows=2, message="已校验")
        raise RuntimeError("bad " + cfg.headers["Authorization"] + " " + cfg.database_url + " secret")
    execute_claimed(factory, job["id"], "worker", failing)
    with factory() as db:
        run = service.run_detail(db, job["id"])["run"]
        assert run["status"] == "failed" and run["fetched_rows"] == 2
        assert "secret" not in run["error"] and "private-token" not in run["error"]
        assert db.get(DataSyncTask, "catalog").active_run_id is None


def test_run_events_pagination_and_filters(factory):
    with factory() as db:
        job = service.enqueue(db, "catalog")
    service.claim_next(factory, "worker")
    for page in range(1, 4):
        service.record_progress(factory, job["id"], "worker", stage="fetching", page_no=page, message=f"page {page}")
    with factory() as db:
        first = service.run_detail(db, job["id"], limit=2)
        second = service.run_detail(db, job["id"], after_event_id=first["events"][-1]["id"], limit=2)
        assert first["has_more_events"] and not second["has_more_events"]
        assert second["events"][0]["page_no"] == 3
        assert service.list_runs(db, status="running")["total"] == 1
        assert service.list_runs(db, task_id="orders")["total"] == 0
        assert first["run"]["progress_percent"] is None


def test_api_uses_normal_platform_login(factory):
    from app.routers.data_sync import router
    app = FastAPI()
    app.include_router(router)
    def database():
        with factory() as db:
            yield db
    app.dependency_overrides[get_db] = database
    async def check():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            for path in ["/tasks", "/runs", "/runs/missing"]:
                response = await client.get("/api/chatbi/data-sync" + path)
                assert response.status_code == 401
            response = await client.post("/api/chatbi/data-sync/tasks/catalog/run")
            assert response.status_code == 401
    asyncio.run(check())


def test_paging_uses_short_page_not_total_count(config):
    seen = []
    def respond(request):
        page = int(request.url.params["page"]); seen.append(page)
        return httpx.Response(200, json={"success": "true", "totalCount": 1,
            "data": [{"id": page * 2}, {"id": page * 2 + 1}] if page == 1 else [{"id": 4}]})
    client = pipeline.ApiClient(config, transport=httpx.MockTransport(respond))
    assert [(page, len(records)) for page, records in client.pages()] == [(1, 2), (2, 1)]
    assert seen == [1, 2]


def test_api_retry_failure_never_exposes_remote_body(config):
    calls = []
    def respond(request):
        calls.append(1)
        return httpx.Response(500, text="private-token secret")
    client = pipeline.ApiClient(config, transport=httpx.MockTransport(respond), sleeper=lambda _: None)
    with pytest.raises(RuntimeError, match="第 1 页") as error:
        list(client.pages())
    assert len(calls) == config.retry_times
    assert "private-token" not in str(error.value)


@pytest.mark.parametrize("data", [None, {}, [1], "rows"])
def test_invalid_api_payload_cannot_reach_target(config, data):
    client = pipeline.ApiClient(config, transport=httpx.MockTransport(lambda req: httpx.Response(200,
        json={"success": "true", "data": data})), sleeper=lambda _: None)
    with pytest.raises(RuntimeError):
        list(client.pages())


def test_quality_failure_never_truncates_small_table(config, monkeypatch):
    engine = MagicMock()
    client = SimpleNamespace(pages=lambda: iter([(1, [{"ID": 1}])]))
    monkeypatch.setattr(pipeline.schema, "validate_records_against_table", lambda *a: None)
    with pytest.raises(RuntimeError, match="门禁"):
        pipeline._small_table(engine, replace(config, min_rows=10), client, lambda **v: None)
    engine.begin.assert_not_called()


@pytest.mark.parametrize("future_row", [False, True])
def test_large_table_parts_progress_and_transaction_order(config, monkeypatch, tmp_path, future_row):
    config = replace(config, table_key="orders", part_rows=3, min_rows=1)
    calls, progress = [], []
    expected_count = 6 if future_row else 5
    monkeypatch.setattr(pipeline.schema, "get_ordered_table_column_names", lambda *a: ["id", "yyyymm"])
    monkeypatch.setattr(pipeline.schema, "validate_records_against_table", lambda *a: None)
    def copy(engine, table, columns, files, count, on_part):
        assert count == expected_count
        sizes = [len(open(file).read().splitlines()) - 1 for file in files]
        assert sizes == [3, expected_count - 3]
        calls.append("copy")
        for index in range(len(files)):
            on_part(index + 1, len(files))
    monkeypatch.setattr(loader, "copy_parts_to_stage", copy)
    monkeypatch.setattr(loader, "replace_table_from_stage", lambda *a: calls.append("replace"))
    client = SimpleNamespace(pages=lambda: iter([(1, [{"ID": 1, "yyyymm": "202601"}, {"ID": 2, "yyyymm": "202601"}]), (2, [{"ID": 3, "yyyymm": "202601"}, {"ID": 4, "yyyymm": "202601"}]), (3, [{"ID": 5, "yyyymm": "202601"}])]))
    if future_row:
        original_pages = client.pages
        client.pages = lambda: iter([*original_pages(), (4, [{"ID": 99, "yyyymm": "202801"}])])
    assert pipeline._large_table(None, config, client, lambda **v: progress.append(v), "run") == expected_count
    if future_row:
        assert next(event["fetched_rows"] for event in progress if event.get("page_no") == 4) == 6
    assert calls == ["copy", "replace"]
    assert [event["loaded_rows"] for event in progress if "loaded_rows" in event] == [3, expected_count]
    assert list(tmp_path.iterdir()) == []


def test_failed_copy_rolls_back_stage_and_never_replaces(config, monkeypatch, tmp_path):
    config = replace(config, table_key="orders", part_rows=2)
    monkeypatch.setattr(pipeline.schema, "get_ordered_table_column_names", lambda *a: ["id"])
    monkeypatch.setattr(pipeline.schema, "validate_records_against_table", lambda *a: None)
    replace_table = MagicMock()
    monkeypatch.setattr(loader, "replace_table_from_stage", replace_table)
    monkeypatch.setattr(loader, "copy_parts_to_stage", MagicMock(side_effect=RuntimeError("COPY failed")))
    client = SimpleNamespace(pages=lambda: iter([(1, [{"id": 1, "yyyymm": "202601"}])]))
    with pytest.raises(RuntimeError, match="COPY"):
        pipeline._large_table(None, config, client, lambda **v: None, "failed-run")
    replace_table.assert_not_called()
    assert len(list(tmp_path.iterdir())) == 1


def test_copy_transaction_rollback_and_tsv_nulls(monkeypatch, tmp_path):
    file, _ = loader.write_tsv_part(str(tmp_path), "orders", 1, ["id", "value"], [{"id": None, "value": r"\N"}])
    assert open(file).read().splitlines()[1] == '\\N\t"\\N"'
    monkeypatch.setattr(loader, "create_stage_table_if_missing", lambda *a: "bp_stage")
    monkeypatch.setattr(loader, "validate_table_structures_match", lambda *a: None)
    engine = MagicMock()
    connection = engine.raw_connection.return_value
    connection.cursor.return_value.copy_expert.side_effect = RuntimeError("COPY failed")
    with pytest.raises(RuntimeError):
        loader.copy_parts_to_stage(engine, "orders", ["id", "value"], [file], 1)
    connection.rollback.assert_called_once()
    connection.commit.assert_not_called()
    connection.close.assert_called_once()


def test_advisory_lock_released_on_failure(config, monkeypatch):
    engine = MagicMock()
    guard = engine.connect.return_value.__enter__.return_value
    guard.execute.return_value.scalar_one.return_value = True
    monkeypatch.setattr(pipeline.schema, "ensure_table_exists", lambda *a: None)
    monkeypatch.setattr(pipeline, "_large_table", MagicMock(side_effect=RuntimeError("failed")))
    with pytest.raises(RuntimeError):
        pipeline.run_pipeline(config, lambda **v: None, "run", engine=engine)
    sql = [str(call.args[0]) for call in guard.execute.call_args_list]
    assert any("pg_advisory_unlock" in query for query in sql)
    engine.begin.assert_not_called()


def test_no_preconfigured_tasks(monkeypatch, factory):
    monkeypatch.delenv("DATA_SYNC_TASKS", raising=False)
    with factory() as db:
        assert service.list_tasks(db) == []
        assert all(not task.schedule_enabled for task in db.query(DataSyncTask).all())


@pytest.mark.parametrize("method,path", [("GET", "payload.items"), ("POST", "")])
def test_configurable_method_and_record_path(config, method, path):
    seen = []
    def respond(request):
        seen.append(request)
        return httpx.Response(200, json={"payload":{"items":[{"id":1}]}} if path else [{"id":1}])
    client = pipeline.ApiClient(replace(config, method=method, records_path=path), transport=httpx.MockTransport(respond))
    assert list(client.pages()) == [(1, [{"id":1}])]
    assert seen[0].headers["Authorization"] == "Bearer private-token"
    if method == "POST":
        assert json.loads(seen[0].content) == {"page":1,"page_size":2}
