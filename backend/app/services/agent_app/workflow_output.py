"""Stream final summaries and collect BI artifacts through existing API messages.

The collector is never included in node exports, SSE frames or trace snapshots.
Detailed thought events retain their existing debug contract.
"""
import asyncio
import contextlib
import hashlib
import json
from collections import deque

from ..autobi.analysis_events import decode, features, normalize
from .workflow_run_ctx import reachable_from


RESULT_TYPES = {"text", "sql_citations", "data_citations", "full_data_citations", "chart_citations"}


def thought_message(thought):
    # Lazy import avoids a dependency cycle with the external HTTP adapter.
    from .external_chat import _thought_to_message

    payload = features(thought.get("payload"))
    if str(payload.get("status_code") or "").upper() in {"FAILED", "ERROR"}:
        raise RuntimeError("分析引擎返回失败状态")
    if payload.get("type") == "error":
        raise RuntimeError(str(payload.get("message") or "分析执行失败"))
    if isinstance(payload.get("message"), dict) and payload["message"].get("type") not in {"lab_render", "markdown", "chart_citations"}:
        return normalize(payload)
    if payload.get("type") in {"bailian_sql", "bailian_chart", "bailian_data", "summary",
                               "bailian_progress", "progress", "progress_result", "full_data_citations"}:
        return normalize(payload)
    return _thought_to_message(thought)


def _items(value):
    if isinstance(value, dict):
        return [value]
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def chart_fingerprint(chart):
    return hashlib.sha256(json.dumps(chart, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


class WorkflowOutput:
    def __init__(self, on_text=None):
        self.groups = {}
        self.observed = {}
        self.selected = None
        self.error = None
        self.answer = None
        self._on_text = on_text
        self._pending_text = deque()
        self.text_available = asyncio.Event()
        self._emitted_parts = []
        self._text_parts = {}
        self._sent_parts = {}
        self._execution_order = []
        self._ctx = None
        self._edges = None
        self._downstream = {}

    def update_execution(self, ctx, edges, ready=()):
        """Only stream a result once downstream replacement has been ruled out."""
        self._ctx = ctx
        # Scripts can emit legacy result thoughts as well as progress events.
        candidates = {nid for nid, node in ctx.nodes_by_id.items()
                      if (node.get("data") or {}).get("kind") in {"lab", "agent", "script"}}
        if self._edges != edges:
            self._edges = list(edges)
            self._downstream = {nid: (reachable_from(nid, edges) & candidates) - {nid}
                                for nid in candidates}
        for nid in ready:
            if nid in candidates and nid not in self._execution_order:
                self._execution_order.append(nid)
        self._flush_text()

    def append_text(self, node_id, delta):
        if delta:
            self._text_parts.setdefault(node_id, []).append(str(delta))
            self._flush_text()

    def _emit_text(self, delta):
        if not delta:
            return
        self._emitted_parts.append(delta)
        if self._on_text is not None:
            self._on_text(delta)
        else:
            self._pending_text.append(delta)
            self.text_available.set()

    def drain_text(self):
        while self._pending_text:
            yield self._pending_text.popleft()
        self.text_available.clear()

    def _flush_text(self):
        if self._ctx is None or self.error:
            return
        completed = self._ctx.context
        known = self.groups.keys() | self.observed.keys() | self._text_parts.keys()
        for nid in self._execution_order:
            downstream = self._downstream.get(nid, set())
            if downstream & known:
                continue
            if nid in completed and nid not in known:
                continue
            # An unfinished downstream node may replace this result. Likewise,
            # an earlier parallel branch must resolve before later text is sent.
            if any(other not in completed for other in downstream):
                break
            data = self._ctx.nodes_by_id[nid].get("data") or {}
            config = data.get(str(data.get("kind")) + "_config") or {}
            if config.get("sse_output_results", True) is False:
                continue
            parts = self._text_parts.get(nid, [])
            sent = self._sent_parts.get(nid, 0)
            for part in parts[sent:]:
                if sent == 0 and self._emitted_parts:
                    part = "\n\n" + part
                self._emit_text(part)
                sent += 1
            self._sent_parts[nid] = sent
            if nid not in completed and nid not in self.groups:
                break

    def _remaining_text(self, answer):
        emitted = "".join(self._emitted_parts)
        text = str(answer or "")
        if not text.startswith(emitted):
            raise RuntimeError("工作流总结与已输出内容不一致")
        return text[len(emitted):]

    def record_lab(self, node_id, events, *, trace_id, query, summary, sql, error, output_enabled=True):
        messages = []
        self.error = self.error or error
        for event in events:
            try:
                message = thought_message({"tag": "实验室", "payload": event})
            except RuntimeError as exc:
                self.error = self.error or str(exc)
                continue
            if message and message.get("type") in RESULT_TYPES:
                messages.append(message)
        # The node's final SQL is the actual executed, permission-rewritten SQL.
        # Never derive it from a summary or a compatibility display alias.
        if sql and str(sql).strip().lower() != "none":
            messages = [message for message in messages if message.get("type") != "sql_citations"]
            messages.insert(0, {"type": "sql_citations", "features": {
                "sql_citations": [{"query": query, "sql": sql}]}})
        if summary and not any(message.get("type") == "text" for message in messages):
            messages.append({"type": "text", "content": summary})
        # Keep empty/hidden final groups so an earlier result cannot reappear.
        self.groups[node_id] = [{"scope": trace_id or node_id, "query": query,
                                 "summary": summary, "messages": messages, "visible": output_enabled}]
        if summary and node_id not in self._text_parts:
            self._text_parts[node_id] = [str(summary)]
        self._flush_text()

    def record_agent(self, node_id, child, *, output_enabled=True):
        self.error = self.error or child.error
        if child.selected:
            self.groups[node_id] = [{**group, "scope": str(node_id) + "/" + str(group["scope"]),
                                     "visible": output_enabled and group.get("visible", True)}
                                    for group in child.selected]
        self._flush_text()

    def observe(self, node_id, message):
        if message.get("type") in RESULT_TYPES:
            self.observed.setdefault(node_id or "workflow", []).append(message)

    def finish(self, ctx, edges=None):
        groups = dict(self.groups)
        for nid, messages in self.observed.items():
            groups.setdefault(nid, [{"scope": nid, "query": "", "summary": "".join(
                str(message.get("content") or "") for message in messages if message.get("type") == "text"),
                "messages": messages}])
        candidates = [nid for nid in ctx.context if nid in groups]
        children = {}
        active_edges = edges if edges is not None else self._edges
        for edge in active_edges if active_edges is not None else ctx.edges:
            source, target = edge.get("source"), edge.get("target")
            if source in ctx.context and target in ctx.context:
                children.setdefault(source, []).append(target)

        def reaches(source, target):
            pending, seen = [source], set()
            while pending:
                current = pending.pop()
                if current == target:
                    return True
                if current not in seen:
                    seen.add(current)
                    pending.extend(children.get(current, []))
            return False

        terminal = [nid for nid in candidates if not any(
            other != nid and reaches(nid, other) for other in candidates)]
        self.selected = [group for nid in terminal for group in groups[nid]]
        # BI presentation comes from the lab SSE results. Workflow output remains
        # available to callers through the engine's existing output/exports.
        self.answer = ctx.final_output
        if candidates:
            self.answer = "\n\n".join(group["summary"] for group in self.selected
                if group.get("visible", True) and group["summary"])
        if self._ctx is not None and not self.error and (candidates or self._on_text is None):
            self._emit_text(self._remaining_text(self.answer))

    def final_messages(self, answer):
        if self.error:
            raise RuntimeError("实验室执行失败: " + str(self.error))
        if self.selected is None:
            # Compatibility for custom runners that only yield legacy thought events.
            last = next(reversed(self.observed), None)
            self.selected = [{"scope": last, "query": "", "summary": "",
                              "messages": self.observed[last]}] if last is not None else []
            self.answer = "".join(str(message.get("content") or "") for message in self.observed[last]
                if message.get("type") == "text") if last is not None else answer
        if self.answer is not None:
            answer = self.answer
        remaining = self._remaining_text(answer)
        if remaining:
            yield {"type": "text", "content": remaining}

        sql_messages, table_messages, chart_messages = [], [], []
        for group in self.selected:
            if not group.get("visible", True):
                continue
            scope, query = group["scope"], group["query"]
            sqls, tables, charts = {}, {}, {}
            for message in group["messages"]:
                feat = features(message.get("features"))
                for item in _items(feat.get("sql_citations")):
                    if item.get("sql") and str(item["sql"]).strip().lower() != "none":
                        sqls.setdefault(str(item["sql"]), dict(item))
                for index, item in enumerate(_items(feat.get("full_data_citations") or feat.get("data_citations"))):
                    key = str(item.get("id", item.get("query") or item.get("title") or index))
                    old = tables.get(key)
                    if old is None or len(item.get("data") or []) >= len(old.get("data") or []):
                        tables[key] = dict(item)
                for item in _items(feat.get("chart_citations")):
                    chart = item.get("chart")
                    if not isinstance(chart, dict):
                        continue
                    key = chart_fingerprint(chart)
                    if key not in charts:
                        charts[key] = dict(item)
                    elif not charts[key].get("query") and item.get("query"):
                        charts[key]["query"] = item["query"]
            def result_message(typ, item, index):
                # Citation IDs already belong to the legacy contract. Native lab
                # events may omit them; fill them so parallel tables stay distinct.
                if item.get("id") is None:
                    item["id"] = str(scope) + ":" + typ + ":" + str(index)
                return {"type": typ, "content": "", "actionId": scope, "features": {typ: [item]}}
            for index, item in enumerate(sqls.values()):
                sql_messages.append(result_message("sql_citations", item, index))
            for index, item in enumerate(tables.values()):
                table_messages.append(result_message("data_citations", item, index))
            for index, item in enumerate(charts.values()):
                item["query"] = item.get("query") or query
                chart_messages.append(result_message("chart_citations", item, index))
        yield from sql_messages
        yield from table_messages
        yield from chart_messages


async def stream_workflow_output(db, app_id, version_id, inputs, *, runner):
    collector, completed = WorkflowOutput(), False
    iterator = runner(db, app_id, version_id, inputs, emit_trace=True, result_collector=collector).__aiter__()
    try:
        async for chunk in iterator:
            event = decode(chunk)
            if event.get("type") == "result_delta":
                yield {"type": "text", "content": event["content"]}
                continue
            if event.get("type") == "trace_id":
                yield event
                continue
            if event.get("error"):
                raise RuntimeError(str(event["error"]))
            output = event.get("output_snapshot") or event.get("output")
            if event.get("kind") == "lab" and isinstance(output, dict) and output.get("error"):
                raise RuntimeError("实验室执行失败")
            if event.get("type") == "thought":
                message = thought_message(event.get("thought") or {})
                if message:
                    collector.observe(event.get("node_id"), message)
                    if message.get("type") in {"progress", "progress_result", "trace", "statistics"}:
                        yield message
            if event.get("status") == "done" and not event.get("node_id"):
                completed = True
                for message in collector.final_messages(event.get("output")):
                    yield message
        if not completed:
            raise RuntimeError("分析执行中断，未收到完成事件")
    finally:
        if hasattr(iterator, "aclose"):
            with contextlib.suppress(Exception):
                await iterator.aclose()
