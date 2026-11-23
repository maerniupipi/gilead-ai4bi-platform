"""SQL, answer and trace reports; original SSE frames remain in the event log."""
import json

from app.sse import format_frame


def dump(value):
    return json.dumps(value, ensure_ascii=False, indent=2)


def readable(value):
    return value if isinstance(value, str) else dump(value)


def remainder(value, known):
    return {key: item for key, item in value.items() if key not in known}


class Report:
    def __init__(self):
        self.understanding = []
        self.stages = []
        self.sql = []
        self.data = []
        self.charts = []
        self.text = []
        self.statistics = []
        self.extra = []
        self.metadata = {}
        self.snapshot = ""
        self.ended = False
        self.lab_trace_ids = []
        self.workflow_trace_ids = []

    def collect_traces(self, value):
        for keys, target in [
                (("lab_trace_ids", "labTraceIds", "lab_trace_id", "labTraceId"), self.lab_trace_ids),
                (("workflow_trace_ids", "workflowTraceIds", "workflow_trace_id", "workflowTraceId"), self.workflow_trace_ids)]:
            for key in keys:
                values = value.get(key, [])
                for item in values if isinstance(values, list) else [values]:
                    if isinstance(item, str) and item.strip() and item.strip() != "stream":
                        item = item.strip()
                        if item not in target:
                            target.append(item)

    def supplement(self, number, value):
        self.extra.append(f"[{number:04d}] " + readable(value))

    def add(self, frame, number):
        if frame.partial or frame.parse_error or not isinstance(frame.payload, dict):
            self.extra.append(format_frame(frame, number))
            return
        payload = frame.payload
        body = payload.get("data")
        if not isinstance(body, dict):
            self.supplement(number, payload)
            return
        self.ended = self.ended or frame.is_end
        self.collect_traces(body)
        for key in ("questionId", "outSessionId", "role"):
            value = body.get(key)
            if value is not None:
                values = self.metadata.setdefault(key, [])
                if value not in values:
                    values.append(value)
        snapshot = body.get("rewriteQuestion")
        if isinstance(snapshot, str) and snapshot:
            self.snapshot = snapshot
        elif snapshot not in (None, ""):
            self.supplement(number, {"rewriteQuestion": snapshot})
        for value in (remainder(payload, {"data", "id", "event"}),
                      remainder(body, {"messages", "end", "questionId", "outSessionId",
                                       "role", "rewriteQuestion"})):
            if value:
                self.supplement(number, value)
        messages = body.get("messages", [])
        if not isinstance(messages, list):
            self.supplement(number, {"messages": messages})
            return
        for message in messages:
            if not isinstance(message, dict):
                self.supplement(number, message)
                continue
            kind = message.get("type")
            features = message.get("features", {})
            if not isinstance(kind, str) or not isinstance(features, dict):
                self.supplement(number, message)
                continue
            used = set()
            self.collect_traces(features)
            content_used = False
            if kind == "text" and isinstance(message.get("content", ""), str):
                self.text.append(message.get("content", ""))
                content_used = True
            elif kind in {"progress", "progress_result"} and "progress" in features:
                target = self.stages if kind == "progress" else self.understanding
                target.append(f"[{number:04d}] " + readable(features["progress"]))
                used.add("progress")
            elif kind in {"sql_citations", "data_citations", "chart_citations"}:
                values = features.get(kind)
                if isinstance(values, list):
                    target = {"sql_citations": self.sql, "data_citations": self.data,
                              "chart_citations": self.charts}[kind]
                    target.extend(values)
                    used.add(kind)
            elif kind == "statistics":
                self.statistics.append(features)
                used.update(features)
            elif kind == "trace":
                used.update({"lab_trace_ids", "labTraceIds", "lab_trace_id", "labTraceId",
                             "workflow_trace_ids", "workflowTraceIds", "workflow_trace_id", "workflowTraceId",
                             "lab_node_id", "lab_project_id"})
            else:
                self.supplement(number, message)
                continue
            extra = remainder(message, {"type", "features", "actionId", "content"})
            feature_extra = remainder(features, used)
            if feature_extra:
                extra["features"] = feature_extra
            if not content_used and message.get("content") not in (None, ""):
                extra["content"] = message["content"]
            if extra:
                self.supplement(number, {"type": kind, **extra})

    def _chart(self, item):
        if not isinstance(item, dict) or not isinstance(item.get("chart"), dict):
            return item
        chart = item["chart"]
        if "data" in chart:
            for index, result in enumerate(self.data, 1):
                if isinstance(result, dict) and "data" in result and chart["data"] == result["data"]:
                    return {**item, "chart": {**chart, "data": f"引用：查询数据 #{index}"}}
        return item

    def update_row(self, row):
        statements = []
        for index, item in enumerate(self.sql, 1):
            sql = item.get("sql") if isinstance(item, dict) else None
            if isinstance(sql, str):
                text = sql
            else:
                text = "[非标准 SQL 引用]\n" + dump(item)
            if len(self.sql) > 1:
                text = f"-- SQL #{index}\n" + text
            statements.append(text)
        row.sql = "\n\n".join(statements)
        row.answer = "".join(self.text)
        row.lab_trace_ids = list(self.lab_trace_ids)
        row.workflow_trace_ids = list(self.workflow_trace_ids)
        if not row.answer and self.snapshot:
            row.answer = "[备用快照：未收到 text 正文]\n" + self.snapshot
        row.output = self.render(row)

    def render(self, row):
        sections = []
        def section(title, content):
            if content:
                sections.append(f"【{title}】\n" + content)

        def numbered(items):
            return "\n\n".join(f"#{index}\n{dump(item)}" for index, item in enumerate(items, 1))

        section("问题理解", "\n".join(self.understanding))
        section("执行阶段", "\n".join(self.stages))
        section("SQL", numbered(self.sql))
        section("查询数据", numbered(self.data))
        answer = "".join(self.text)
        section("完整回答", answer)
        if not answer and self.snapshot:
            section("备用快照（rewriteQuestion，非改写问题）", self.snapshot)
        section("图表信息", numbered([self._chart(item) for item in self.charts]))
        status = {"running": "执行中", "success": "成功", "failed": "失败",
                  "interrupted": "已中断", "cancelled": "未执行", "pending": "待执行"}
        info = [f"状态: {status.get(row.status, row.status)}",
                f"结束标记: {'end=true' if self.ended else '未收到有效 end=true'}",
                f"本地耗时（秒）: {row.elapsed}", f"事件数: {row.event_count}",
                f"conversation_id: {row.conversation_id}"]
        for key, values in self.metadata.items():
            for value in values:
                info.append(f"{key}: {readable(value)}")
        for trace_id in self.workflow_trace_ids:
            info.append("workflow_trace_id: " + trace_id)
        for trace_id in self.lab_trace_ids:
            info.append("lab_trace_id: " + trace_id)
        if self.statistics:
            info.append("服务端统计（保持原始字段与单位）:\n" + numbered(self.statistics))
        if row.error:
            info.append("[error] " + row.error)
        section("执行信息", "\n".join(info))
        section("补充事件", "\n\n".join(self.extra))
        return "\n\n".join(sections)
