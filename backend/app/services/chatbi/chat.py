from app.core.execution import DATABASE_WORK
import asyncio
import contextlib
import json
import logging
import time
import uuid
import traceback

from sqlalchemy import update
from sqlalchemy.exc import SQLAlchemyError
from ...core.database import SessionLocal
from ...models.chatbi import ChatBIConversation, ChatBIMessage, ChatBIResult
from .config import APIError, positive_env, runtime_key, validate_inputs
from .runtime import features, run_analysis
from .conversation_metadata import record_conversation_context
from ..agent_app.workflow_output import chart_fingerprint
from .diagnostics import record_request, begin_capture, capture_execution, record_event, persist_capture, end_capture
from ...core.observability import bind_context

logger = logging.getLogger(__name__)


def uid():
    return str(uuid.uuid4())


def frame(event):
    return "data: " + json.dumps(event, ensure_ascii=False, default=str) + "\n\n"


def owned_conversation(db, conversation_id, user):
    conv = db.get(ChatBIConversation, str(conversation_id))
    if not conv or conv.owner != user.owner:
        raise APIError(404, "conversation_not_exists", "会话不存在")
    return conv


def prepare_chat(db, body, user, *, runtime=None, original_request=None):
    validate_inputs(body.inputs)
    runtime = runtime if runtime is not None else runtime_key()
    conv = owned_conversation(db, body.conversation_id, user) if body.conversation_id else None
    if conv and conv.runtime != runtime:
        raise APIError(409, "runtime_changed", "分析配置已变更，请开始新会话")
    if not conv:
        conv = ChatBIConversation(id=uid(), owner=user.owner, runtime=runtime)
        db.add(conv)
        db.flush()
    if conv.active_task:
        active = db.query(ChatBIMessage).filter_by(task_id=conv.active_task).first()
        if active and active.status == "running" and active.created_at + positive_env("CHATBI_CHAT_TIMEOUT", 600) > int(time.time()):
            raise APIError(409, "conversation_busy", "此会话仍在生成回答")
        if active and active.status == "running":
            active.status, active.error = "failed", "上次分析已超时或中断"
        db.execute(update(ChatBIConversation).where(ChatBIConversation.id == conv.id,
                   ChatBIConversation.active_task == conv.active_task).values(active_task=None))
        db.flush()
    task_id, message_id = uid(), uid()
    locked = db.execute(update(ChatBIConversation).where(ChatBIConversation.id == conv.id,
                        ChatBIConversation.active_task.is_(None)).values(active_task=task_id, turn_count=ChatBIConversation.turn_count + 1))
    if locked.rowcount != 1:
        raise APIError(409, "conversation_busy", "此会话仍在生成回答")
    db.refresh(conv)
    msg = ChatBIMessage(id=message_id, task_id=task_id, conversation_id=conv.id, owner=user.owner,
                        sequence=conv.turn_count, query=body.query, answer="", content=[], status="running", created_at=int(time.time()))
    db.add(msg)
    record_conversation_context(db, conv.id, user)
    record_request(db, msg, body, user, runtime, original_request)
    bind_context(message_id=msg.id,conversation_id=conv.id,user_id=user.user_id,task_id=msg.task_id)
    db.commit()
    return message_id


def stop_chat(db, task_id, user):
    msg = db.query(ChatBIMessage).filter_by(task_id=str(task_id), owner=user.owner).first()
    if not msg:
        raise APIError(404, "task_not_found", "任务不存在")
    if msg.status == "running":
        msg.stop_requested = True
        db.commit()
    return {"result": "success"}


def table_columns(item, rows):
    source = item.get("columns") or (list(rows[0]) if rows and isinstance(rows[0], dict) else [])
    cols = []
    for col in source:
        if isinstance(col, str):
            cols.append({"key": col, "name": col})
        elif isinstance(col, dict):
            key = str(col.get("key") or col.get("name") or "")
            if key:
                cols.append({**col, "key": key, "name": col.get("name") or key})
    return cols


class EventBuilder:
    def __init__(self, db, msg):
        self.db, self.msg = db, msg
        self.base = {"task_id": msg.task_id, "message_id": msg.id,
                     "conversation_id": msg.conversation_id, "created_at": msg.created_at}
        self.run_id, self.index = uid(), 0
        self.progress = None
        self.content, self.answer = [], []
        self.table_by_source = {}
        self.chart_sources = set()
        self.last_data_ref = None
        self.steps = {}

    def event(self, event, **values):
        return {"event": event, **self.base, **values}

    def node_start(self, typ, title, node_id=None):
        data = {"id": uid(), "node_id": node_id or uid(), "node_type": typ, "title": title,
                "index": self.index, "predecessor_node_id": None, "inputs": None,
                "created_at": int(time.time())}
        self.index += 1
        return self.event("node_started", workflow_run_id=self.run_id, data=data)

    def node_finish(self, start, status="succeeded", outputs=None, error=None):
        now = int(time.time())
        data = {**start["data"], "status": status, "outputs": outputs, "outputs_truncated": False,
                "process_data": None, "error": error, "elapsed_time": max(0, now - start["data"]["created_at"]),
                "finished_at": now, "execution_metadata": {}}
        return self.event("node_finished", workflow_run_id=self.run_id, data=data)

    def close_progress(self, status="succeeded", error=None):
        if not self.progress:
            return []
        result = self.node_finish(self.progress, status, error=error)
        self.progress = None
        return [result]

    def accept(self, message):
        typ, content = message.get("type"), str(message.get("content") or "")
        feat = features(message.get("features"))
        if typ == "trace_id":
            trace_id = message.get("trace_id")
            if isinstance(trace_id, str) and 0 < len(trace_id.strip()) <= 128:
                # Preserve the engine's persisted trace, independently of the SSE workflow ID.
                self.base.setdefault("trace_id", trace_id.strip())
            return
        if typ == "error":
            raise RuntimeError(content or "分析执行失败")
        if typ == "step_started":
            start = self.node_start("progress", message["title"], str(message["step_id"]))
            self.steps[str(message["step_id"])] = start
            yield start
        if typ == "step_finished":
            start = self.steps.pop(str(message["step_id"]), None)
            failed = message.get("status", "succeeded") != "succeeded"
            if start:
                yield self.node_finish(start, "failed" if failed else "succeeded",
                                       error="分析步骤执行失败，请重试或联系管理员" if failed else None)
            if failed:
                raise RuntimeError("分析节点执行失败")
        if typ == "text" and content:
            self.answer.append(content)
            self.content.append({"type": "text", "content": content})
            yield self.event("message", id=self.msg.id, answer=content)
        if typ in {"progress", "progress_result"}:
            title = str(feat.get("progress") or content).strip()
            if title and (not self.progress or self.progress["data"]["title"] != title):
                yield from self.close_progress()
                self.progress = self.node_start("progress", title)
                yield self.progress

        sql_items = feat.get("sql_citations") or []
        if isinstance(sql_items, dict):
            sql_items = [sql_items]
        for item in sql_items:
            sql = item.get("sql")
            if not isinstance(sql, str) or not sql.strip() or sql.strip().lower() == "none":
                continue
            # Preserve the engine's final SQL verbatim, including permission
            # rewriting. Do not regenerate it from the natural-language summary.
            title = str(item.get("query") or "查询 SQL")[:512]
            outputs = {"sql": sql, "schema_version": "1.0"}
            start = self.node_start("sql", title)
            yield start
            yield self.node_finish(start, outputs=outputs)
            self.content.append({"type": "sql", "node_id": start["data"]["node_id"],
                                 "title": title, "outputs": outputs})

        # Full rows remain in platform storage. Only the preview crosses the UI boundary.
        items = feat.get("full_data_citations") or feat.get("data_citations") or []
        if isinstance(items, dict):
            items = [items]
        for index, item in enumerate(items):
            rows = item.get("data") or []
            if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
                raise RuntimeError("表格结果格式错误")
            source = (str(message.get("actionId") or message.get("action_id") or "result"),
                      str(item.get("id", item.get("query") or item.get("title") or index)))
            previous = self.table_by_source.get(source)
            data_ref = previous[0] if previous else uid()
            self.last_data_ref = data_ref
            cols = table_columns(item, rows)
            total = int(item.get("total_count", item.get("total_rows", len(rows))))
            total = max(total, len(rows))
            complete = total == len(rows) and not item.get("truncated", False)
            title = str(item.get("query") or item.get("title") or "查询结果")[:512]
            result = self.db.get(ChatBIResult, data_ref) if previous else None
            if result and (result.complete or len(rows) < len(result.rows)):
                continue
            if result:
                result.columns, result.rows, result.total_rows, result.complete = cols, rows, total, complete
            else:
                result = ChatBIResult(id=data_ref, conversation_id=self.msg.conversation_id,
                                     message_id=self.msg.id, owner=self.msg.owner, title=title,
                                     columns=cols, rows=rows, total_rows=total, complete=complete)
                self.db.add(result)
            self.db.commit()
            outputs = {"columns": cols, "rows": rows[:50], "total_rows": total,
                       "truncated": total > len(rows[:50]) or not complete, "data_ref": data_ref, "can_export": complete,
                       "sortable": total <= 50 and complete, "schema_version": "1.0"}
            start = previous[1] if previous else self.node_start("table", title)
            self.table_by_source[source] = (data_ref, start)
            if not previous:
                yield start
            yield self.node_finish(start, outputs=outputs)
            record = {"type": "table", "node_id": start["data"]["node_id"], "title": title, "outputs": outputs}
            if previous:
                self.content = [record if c.get("node_id") == record["node_id"] else c for c in self.content]
            else:
                self.content.append(record)
        for item in feat.get("chart_citations") or []:
            chart = item.get("chart") or {}
            rows = chart.get("data") or []
            cols = table_columns(chart, rows)
            typemap = {"A": "bar", "B": "line", "C": "pie"}
            chart_type = typemap.get(chart.get("type"), chart.get("type", "bar"))
            dims = [c for c in cols if c.get("target") == "xaxis"]
            series = [c for c in cols if c.get("target") == "yaxis"]
            if not dims or not series:
                continue
            pie_values = [row.get(series[0]["key"]) for row in rows]
            pie_ok = (len(series) == 1 and len(dims) == 1 and bool(pie_values)
                      and all(isinstance(value, (int, float)) and value >= 0 for value in pie_values)
                      and sum(pie_values) > 0)
            available = ["bar", "line"] + (["pie"] if pie_ok else [])
            chart_source = (str(message.get("actionId") or message.get("action_id") or "result"),
                            str(item.get("table_id", item.get("data_id", item.get("id", item.get("query") or "")))))
            linked = self.table_by_source.get(chart_source)
            if linked is None:
                # A parallel result may have one table under its own execution ID.
                # Keep linkage internal; the public chart-citation shape stays unchanged.
                scoped_tables = [table for source, table in self.table_by_source.items()
                                 if source[0] == chart_source[0]]
                if len(scoped_tables) == 1:
                    linked = scoped_tables[0]
            # Never attach an arbitrary last table when a response contains several results.
            chart_ref = linked[0] if linked else self.last_data_ref if len(self.table_by_source) == 1 else None
            outputs = {"dimensions": dims, "series": series, "rows": rows, "unit": str(chart.get("unit") or ""),
                       "chart_type": chart_type if chart_type in available else "bar", "available_types": available,
                       "data_ref": chart_ref, "schema_version": "1.0"}
            chart_key = (chart_source, chart_fingerprint(outputs))
            if chart_key in self.chart_sources:
                continue
            self.chart_sources.add(chart_key)
            title = str(item.get("query") or chart.get("title") or "数据图表")
            start = self.node_start("chart", title)
            yield start
            yield self.node_finish(start, outputs=outputs)
            self.content.append({"type": "chart", "node_id": start["data"]["node_id"], "title": title, "outputs": outputs})


async def stream_chat(message_id, body, user, request=None, *, factory=None, runner=None):
    factory, runner = factory or SessionLocal, runner or run_analysis
    db = factory()
    def load_turn():
        with factory() as state_db:
            msg = state_db.get(ChatBIMessage, message_id)
            conv = state_db.get(ChatBIConversation, msg.conversation_id)
            history = []
            previous = state_db.query(ChatBIMessage).filter(ChatBIMessage.conversation_id == conv.id,
                ChatBIMessage.owner == msg.owner, ChatBIMessage.sequence < msg.sequence,
                ChatBIMessage.status == "succeeded").order_by(ChatBIMessage.sequence.desc()).limit(20).all()
            for old in reversed(previous):
                history.extend([{"role": "user", "content": old.query}, {"role": "assistant", "content": old.answer}])
            state_db.expunge(msg)
            return msg, conv.runtime, conv.id, history
    msg, runtime, conversation_id, history = await DATABASE_WORK.run(load_turn)
    builder = EventBuilder(db, msg)
    capture_token = begin_capture(message_id, conversation_id, msg.task_id)
    workflow_id = str(uuid.uuid5(uuid.NAMESPACE_URL, "chatbi:" + runtime))
    status, error, pending, iterator = "running", None, None, None
    error_event = None
    started, ping_at, control_at = time.monotonic(), time.monotonic(), 0.0
    try:
        yield frame(builder.event("workflow_started", workflow_run_id=builder.run_id,
                    data={"id": builder.run_id, "workflow_id": workflow_id, "inputs": {}, "created_at": msg.created_at}))
        iterator = runner(db, runtime, body.query, body.inputs, conversation_id, history, user).__aiter__()
        while True:
            # Poll independently of token frequency; each text chunk must not round-trip to MySQL.
            stopped = False
            if time.monotonic() >= control_at:
                def read_stop():
                    with factory() as control:
                        return control.query(ChatBIMessage.stop_requested).filter_by(id=message_id).scalar()
                stopped = await DATABASE_WORK.run(read_stop)
                control_at = time.monotonic() + 1.0
            if stopped or (request and await request.is_disconnected()):
                status = "stopped"
                break
            if time.monotonic() - started > positive_env("CHATBI_CHAT_TIMEOUT", 600):
                raise APIError(504, "timeout", "分析超时，请重试")
            if pending is None:
                pending = asyncio.create_task(anext(iterator))
            done, _ = await asyncio.wait({pending}, timeout=0.5)
            if not done:
                if time.monotonic() - ping_at >= 10:
                    yield "event: ping\n\n"
                    ping_at = time.monotonic()
                continue
            try:
                message = pending.result()
            except StopAsyncIteration:
                status = "succeeded"
                break
            pending = None
            record_event(message)
            payload_features = features(message.get("features"))
            if payload_features.get("full_data_citations") or payload_features.get("data_citations"):
                def persist_results():
                    with factory() as result_db:
                        builder.db = result_db
                        return list(builder.accept(message))
                events = await DATABASE_WORK.run(persist_results)
            else:
                events = builder.accept(message)
            for event in events:
                yield frame(event)
        for event in builder.close_progress("succeeded" if status == "succeeded" else "failed",
                                             "用户已停止" if status == "stopped" else None):
            yield frame(event)
        for start in builder.steps.values():
            yield frame(builder.node_finish(start, "succeeded" if status == "succeeded" else "failed", error="用户已停止" if status == "stopped" else None))
        builder.steps.clear()
    except (asyncio.CancelledError, GeneratorExit):
        status = "stopped"
        raise
    except Exception as exc:
        status = "failed"
        logger.exception("ChatBI analysis failed message_id=%s", message_id)
        capture_execution(original_error=str(exc), exception=traceback.format_exc())
        if isinstance(exc, SQLAlchemyError):
            exc = APIError(503, "service_unavailable", "数据库暂时不可用，请稍后重试")
        error = exc.message if isinstance(exc, APIError) else "分析执行失败，请重试或联系管理员"
        for event in builder.close_progress("failed", error):
            yield frame(event)
        for start in builder.steps.values():
            yield frame(builder.node_finish(start, "failed", error=error))
        builder.steps.clear()
        error_event = builder.event("error", status=exc.status if isinstance(exc, APIError) else 500,
                                    code=exc.code if isinstance(exc, APIError) else "internal_server_error", message=error)
    finally:
        if pending and not pending.done():
            pending.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await pending
        if iterator and hasattr(iterator, "aclose"):
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await iterator.aclose()
        # A broken analysis connection must not break the terminal SSE or retain the conversation lock.
        try:
            db.rollback()
        except Exception:
            logger.exception("ChatBI analysis rollback failed message_id=%s", message_id)
            with contextlib.suppress(Exception):
                db.invalidate()
        with contextlib.suppress(Exception):
            db.close()
        try:
            def finish_state():
                with factory() as state_db:
                    persist_capture(state_db, message_id, status=status if status != 'running' else 'failed',
                                    elapsed_ms=round((time.monotonic()-started)*1000),run_id=builder.run_id,
                                    total_steps=builder.index,finished_at=int(time.time()*1000),
                                    sql=[item.get('outputs',{}).get('sql') for item in builder.content if item.get('type')=='sql'],
                                    results=[{key:item.get('outputs',{}).get(key) for key in ('data_ref','total_rows','can_export','truncated')} for item in builder.content if item.get('type')=='table'])
                    state_db.execute(update(ChatBIMessage).where(ChatBIMessage.id == message_id).values(
                        status=status if status != "running" else "failed", answer="".join(builder.answer),
                        content=builder.content, error=error, finished_at=int(time.time())))
                    state_db.execute(update(ChatBIConversation).where(ChatBIConversation.id == conversation_id,
                               ChatBIConversation.active_task == builder.base["task_id"]).values(active_task=None))
                    state_db.commit()
            await DATABASE_WORK.run(finish_state)
        except Exception:
            logger.exception("ChatBI terminal state persistence failed message_id=%s", message_id)
            status, error = "failed", "分析状态保存失败，请稍后重试"
            error_event = builder.event("error", status=503, code="service_unavailable", message=error)
        finally:
            end_capture(capture_token)
    # Completion metadata explicitly distinguishes a stopped response from success.
    if status != "failed":
        yield frame(builder.event("message_end", id=message_id, metadata={"status": status}))
    yield frame(builder.event("workflow_finished", workflow_run_id=builder.run_id, data={
        "id": builder.run_id, "workflow_id": workflow_id, "status": status, "error": error,
        "outputs": {"answer": "".join(builder.answer)}, "elapsed_time": round(time.monotonic() - started, 3),
        # The upstream engines do not expose aggregate token usage; zero is the compatibility default.
        "total_tokens": 0, "total_steps": builder.index,
        "created_by": {}, "exceptions_count": 0,
        "created_at": builder.base["created_at"], "finished_at": int(time.time()),
    }))
    # Dify 1.15 sends workflow_finished(failed), then the terminal error event.
    if error_event:
        yield frame(error_event)
