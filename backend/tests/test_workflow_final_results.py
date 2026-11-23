from unittest.mock import AsyncMock
"""Final BI results use the existing wire contract, independently of debug thoughts."""
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.models.chatbi import ChatBIMessage, ChatBIResult
from app.repositories.agent_app import repository
from app.schemas.chatbi import ChatRequest
from app.schemas.external_agent import ExternalAgentChatRequest
from app.services.agent_app import external_chat, workflow_engine
from app.services.agent_app.executors import agent, lab
from app.services.autobi.lab_bailian_gateway import _bailian_markdown_from_lab_chart
from app.services.chatbi import chat, runtime
from test_chatbi_integration import USER, collect, factory


SQL = "SELECT city, sales FROM facts WHERE user_id = 'TEST'"
ROWS = [{"city": f"城市{i}", "sales": i} for i in range(80)]


def frame(value):
    return "data: " + json.dumps(value, ensure_ascii=False) + "\n\n"


def node(nid, kind, **config):
    return {"id": nid, "data": {"kind": kind, "label": nid, **config}}


def lab_node(nid, hidden):
    return node(nid, "lab", lab_config={"project_id": 1, "sse_output_thoughts": not hidden,
        "input_mapping": [{"target_field": "content", "source_mode": "const", "const_value": nid}],
        "output_vars": ["trace_id", "summary", "sql", "error"]})


def graph(hidden=False, merged=True):
    nodes = [node("start", "start"), lab_node("bp", hidden), lab_node("qty", hidden)]
    links = [("start", "bp"), ("start", "qty")]
    if merged:
        nodes.append(lab_node("final", hidden))
        links += [("bp", "final"), ("qty", "final"), ("final", "out")]
        refs = ["final.summary"]
    else:
        links += [("bp", "out"), ("qty", "out")]
        refs = ["bp.summary", "qty.summary"]
    nodes.append(node("out", "output", output_config={
        "content_fields": [{"source_ref": ref} for ref in refs]}))
    return {"nodes": nodes, "edges": [{"source": s, "target": t} for s, t in links]}


def native_events(query):
    rows = ROWS if query == "final" else [{"city": query, "sales": 1}]
    return [
        {"type": "bailian_progress", "progress": "查询数据中"},
        {"type": "bailian_sql", "query": query, "sql": SQL + " /* " + query + " */"},
        {"type": "bailian_data", "query": query, "data": rows, "columns": ["city", "sales"], "total_count": len(rows)},
        {"type": "summary", "delta": "总结:" + query},
        {"type": "bailian_chart", "chart_spec": {"type": "A", "title": "图表:" + query,
            "xaxis": ["city"], "yaxis": ["sales"]}, "sql_data": {"columns": ["city", "sales"], "rows": rows}},
        {"type": "done"},
    ]


def install_workflows(monkeypatch, workflows):
    def version(db, app_id, version_id):
        return SimpleNamespace(id=version_id, workflow_json=workflows[app_id], status="published", workflow_rev=1)
    monkeypatch.setattr(repository, "get_version_for_app", version)
    monkeypatch.setattr(workflow_engine, "get_version_for_app", version)
    monkeypatch.setattr(agent, "get_version_for_app", version)
    monkeypatch.setattr(workflow_engine, "save_workflow_trace", lambda *a, **kw: None)
    monkeypatch.setattr(workflow_engine, "agent_run_trace_set", lambda *a, **kw: None)
    monkeypatch.setattr(lab, "build_lab_run_spec_from_project_id", lambda db, pid, **kw: SimpleNamespace(content=kw["content"]))

    async def collect_lab(db, spec, **kwargs):
        return {"trace_id": kwargs["trace"].trace_id, "summary": "总结:" + spec.content,
                "sql": SQL + " /* " + spec.content + " */", "error": None, "events": native_events(spec.content)}

    async def stream_lab(db, spec, **kwargs):
        action_id = kwargs["trace"].trace_id
        for event in native_events(spec.content):
            if event["type"] == "bailian_chart":
                chart_spec, data = event["chart_spec"], event["sql_data"]
                markdown, features, chart = _bailian_markdown_from_lab_chart(chart_spec, data["columns"], data["rows"])
                for typ, content, feature in [
                    ("lab_render", "", {"chart_spec": chart_spec, "bootcamp_chart": chart}),
                    ("markdown", markdown, features),
                ]:
                    yield frame({"message": {"type": typ, "content": content, "features": feature, "action_id": action_id}})
            elif event["type"] != "done":
                message = runtime.normalize(event)
                message["action_id"] = action_id
                yield frame({"message": message})

    monkeypatch.setattr(lab, "collect_lab_run_json", collect_lab)
    monkeypatch.setattr(lab, "stream_lab_bailian_sse", stream_lab)


async def analyze():
    return [msg async for msg in runtime.run_analysis(MagicMock(), "agent:1:1", "销售", {}, "cid", [], USER)]


@pytest.mark.parametrize("hidden", [False, True])
@pytest.mark.parametrize("workflow_shape", ["direct", "nested", "nested_then_final"])
@pytest.mark.parametrize("entrypoint", ["runtime", "external"])
@pytest.mark.parametrize("hide_intermediate", [False, True])
def test_summary_reaches_consumer_before_model_finishes(monkeypatch, hidden, workflow_shape, entrypoint, hide_intermediate):
    workflow = graph(hidden)
    if hide_intermediate:
        for item in workflow["nodes"]:
            if item["id"] in {"bp", "qty"}:
                item["data"]["lab_config"]["sse_output_results"] = False
    workflows = {1: workflow}
    if workflow_shape != "direct":
        workflows = {2: workflow, 1: {
            "nodes": [node("start", "start"), node("child", "agent", agent_config={
                "target_app_id": 2, "target_version_id": 2, "sse_output_thoughts": not hidden}),
                node("out", "output", output_config={"content_template": "内部输出"})],
            "edges": [{"source": "start", "target": "child"}, {"source": "child", "target": "out"}],
        }}
        if workflow_shape == "nested_then_final":
            for item in workflow["nodes"]:
                if item["id"] == "final":
                    item["data"]["lab_config"]["input_mapping"][0]["const_value"] = "中间总结"
            parent = workflows[1]
            parent["nodes"][1]["data"]["agent_config"]["sse_output_results"] = not hide_intermediate
            parent["nodes"].insert(-1, lab_node("final", hidden))
            parent["edges"] = [{"source": "start", "target": "child"},
                               {"source": "child", "target": "final"}, {"source": "final", "target": "out"}]
    install_workflows(monkeypatch, workflows)
    monkeypatch.setattr(external_chat, "get_agent_app_by_id", lambda *a: SimpleNamespace(id=1))
    monkeypatch.setattr(external_chat, "get_version_for_app", lambda *a: SimpleNamespace(id=1))
    monkeypatch.setattr(external_chat, "_create_log", lambda *a: SimpleNamespace())
    monkeypatch.setattr(external_chat, "_finish_log", lambda *a, **kw: None)

    async def scenario():
        release, started, finished, received = (asyncio.Event() for _ in range(4))
        original_stream = lab.stream_lab_bailian_sse

        async def stream(db, spec, **kwargs):
            if spec.content != "final":
                async for chunk in original_stream(db, spec, **kwargs):
                    yield chunk
                return
            started.set()
            yield frame({"message": {"type": "text", "content": "第一段"}})
            await release.wait()
            yield frame({"message": {"type": "text", "content": "第二段"}})
            finished.set()

        async def collect_lab(db, spec, **kwargs):
            parts = []
            async for chunk in stream(db, spec, **kwargs):
                message = json.loads(chunk[6:])["message"]
                if message.get("type") == "text":
                    parts.append(message["content"])
            return {"summary": "".join(parts), "sql": "", "error": None, "events": []}

        monkeypatch.setattr(lab, "stream_lab_bailian_sse", stream)
        monkeypatch.setattr(lab, "collect_lab_run_json", collect_lab)
        messages = []

        async def response_messages():
            if entrypoint == "runtime":
                async for message in runtime.run_analysis(MagicMock(), "agent:1:1", "销售", {}, "cid", [], USER):
                    yield message
            else:
                async for chunk in external_chat.external_agent_chat_stream(
                    MagicMock(), ExternalAgentChatRequest(app_id=1, version_id=1, message="销售")
                ):
                    for message in json.loads(chunk[6:])["data"]["messages"]:
                        yield message

        async def consume():
            async for message in response_messages():
                messages.append(message)
                if message.get("type") == "text":
                    received.set()

        task = asyncio.create_task(consume())
        try:
            await asyncio.wait_for(started.wait(), timeout=2)
            await asyncio.wait_for(received.wait(), timeout=1)
            assert not finished.is_set()
            assert [msg["content"] for msg in messages if msg.get("type") == "text"] == ["第一段"]
        finally:
            release.set()
            await asyncio.wait_for(task, timeout=2)
        assert [msg["content"] for msg in messages if msg.get("type") == "text" and msg.get("content")] == ["第一段", "第二段"]

    asyncio.run(scenario())


@pytest.mark.parametrize("hidden", [False, True])
def test_nested_parallel_summaries_stream_in_result_order(monkeypatch, hidden):
    parent = {"nodes": [node("start", "start"), node("child", "agent", agent_config={
        "target_app_id": 2, "target_version_id": 2, "sse_output_thoughts": not hidden}),
        node("out", "output", output_config={"content_template": "内部输出"})],
        "edges": [{"source": "start", "target": "child"}, {"source": "child", "target": "out"}]}
    install_workflows(monkeypatch, {1: parent, 2: graph(hidden, merged=False)})

    async def scenario():
        release, later_finished, received = (asyncio.Event() for _ in range(3))

        async def stream(db, spec, **kwargs):
            yield frame({"message": {"type": "text", "content": spec.content + "1"}})
            if spec.content == "bp":
                await release.wait()
            yield frame({"message": {"type": "text", "content": spec.content + "2"}})
            if spec.content == "qty":
                later_finished.set()

        monkeypatch.setattr(lab, "stream_lab_bailian_sse", stream)
        messages = []

        async def consume():
            async for message in runtime.run_analysis(MagicMock(), "agent:1:1", "销售", {}, "cid", [], USER):
                if message.get("type") == "text":
                    messages.append(message["content"])
                    received.set()

        task = asyncio.create_task(consume())
        try:
            await asyncio.wait_for(later_finished.wait(), timeout=2)
            await asyncio.wait_for(received.wait(), timeout=1)
            assert messages == ["bp1"]
        finally:
            release.set()
            await asyncio.wait_for(task, timeout=2)
        assert "".join(messages) == "bp1bp2\n\nqty1qty2"

    asyncio.run(scenario())


@pytest.mark.parametrize("hidden", [False, True])
@pytest.mark.parametrize("failure", [False, True])
def test_partial_summary_can_be_stopped_or_failed_without_replaying(monkeypatch, hidden, failure):
    install_workflows(monkeypatch, {1: graph(hidden)})

    async def scenario():
        release, closed = asyncio.Event(), asyncio.Event()
        original = lab.stream_lab_bailian_sse
        final_calls = []

        async def stream(db, spec, **kwargs):
            if spec.content != "final":
                async for chunk in original(db, spec, **kwargs):
                    yield chunk
                return
            final_calls.append(spec.content)
            try:
                yield frame({"message": {"type": "text", "content": "首段"}})
                await release.wait()
                raise RuntimeError("总结连接中断")
            finally:
                closed.set()

        monkeypatch.setattr(lab, "stream_lab_bailian_sse", stream)
        iterator = runtime.run_analysis(MagicMock(), "agent:1:1", "销售", {}, "cid", [], USER)

        async def first_text():
            async for message in iterator:
                if message.get("type") == "text":
                    return message["content"]

        assert await asyncio.wait_for(first_text(), timeout=2) == "首段"
        if failure:
            release.set()
            with pytest.raises(RuntimeError, match="总结连接中断"):
                async for message in iterator:
                    assert message.get("type") != "text"
        await iterator.aclose()
        await asyncio.wait_for(closed.wait(), timeout=1)
        assert final_calls == ["final"]

    asyncio.run(scenario())


def test_empty_downstream_agent_preserves_earlier_final_results(monkeypatch):
    workflow = graph(hidden=True, merged=False)
    workflow["nodes"].insert(-1, node("child", "agent", agent_config={
        "target_app_id": 2, "target_version_id": 2, "sse_output_thoughts": False}))
    workflow["edges"] = [edge for edge in workflow["edges"] if edge["source"] != "bp"]
    workflow["edges"] += [{"source": "bp", "target": "child"}, {"source": "child", "target": "out"}]
    empty_child = {"nodes": [node("start", "start"), node("out", "output",
        output_config={"content_template": "内部处理结果"})], "edges": [{"source": "start", "target": "out"}]}
    install_workflows(monkeypatch, {1: workflow, 2: empty_child})
    messages = asyncio.run(analyze())
    assert "".join(msg["content"] for msg in messages if msg.get("type") == "text") == "总结:bp\n\n总结:qty"


def citations(messages, kind):
    return [item for message in messages for item in (message.get("features") or {}).get(kind, [])]


@pytest.mark.parametrize("hidden", [False, True])
def test_merged_workflow_only_delivers_final_summary_sql_table_and_one_chart(monkeypatch, hidden):
    install_workflows(monkeypatch, {1: graph(hidden)})
    messages = asyncio.run(analyze())
    assert "".join(msg.get("content", "") for msg in messages if msg.get("type") == "text") == "总结:final"
    assert [item["query"] for item in citations(messages, "sql_citations")] == ["final"]
    assert [item["query"] for item in citations(messages, "data_citations")] == ["final"]
    charts = citations(messages, "chart_citations")
    assert len(charts) == 1 and charts[0]["query"] == "图表:final"
    assert charts[0]["chart"]["data"] == ROWS


@pytest.mark.parametrize("hidden", [False, True])
def test_independent_parallel_final_results_are_all_kept(monkeypatch, hidden):
    install_workflows(monkeypatch, {1: graph(hidden, merged=False)})
    messages = asyncio.run(analyze())
    assert [item["query"] for item in citations(messages, "data_citations")] == ["bp", "qty"]
    assert len({item["id"] for item in citations(messages, "data_citations")}) == 2
    assert [item["query"] for item in citations(messages, "chart_citations")] == ["图表:bp", "图表:qty"]
    assert "".join(msg.get("content", "") for msg in messages if msg.get("type") == "text") == "总结:bp\n\n总结:qty"


@pytest.mark.parametrize("hidden", [False, True])
@pytest.mark.parametrize("parent_merge", [False, True])
def test_nested_final_results_survive_hidden_parent_and_can_be_replaced_by_parent_merge(monkeypatch, hidden, parent_merge):
    parent = [node("start", "start"), node("child", "agent", agent_config={
        "target_app_id": 2, "target_version_id": 2, "sse_output_thoughts": not hidden})]
    links = [("start", "child")]
    if parent_merge:
        parent.append(lab_node("final", hidden))
        links += [("child", "final"), ("final", "out")]
        refs = ["final.summary"]
    else:
        links.append(("child", "out"))
        refs = ["child.output"]
    parent.append(node("out", "output", output_config={"content_fields": [{"source_ref": ref} for ref in refs]}))
    install_workflows(monkeypatch, {1: {"nodes": parent, "edges": [{"source": s, "target": t} for s, t in links]},
                                   2: graph(hidden, merged=False)})
    messages = asyncio.run(analyze())
    expected = ["final"] if parent_merge else ["bp", "qty"]
    assert [item["query"] for item in citations(messages, "data_citations")] == expected
    assert len(citations(messages, "chart_citations")) == len(expected)


def test_output_bindings_do_not_filter_parallel_sse_results(monkeypatch):
    workflow = graph(hidden=True, merged=False)
    workflow["nodes"][-1]["data"]["output_config"]["content_fields"] = [{"source_ref": "bp.summary"}]
    install_workflows(monkeypatch, {1: workflow})
    messages = asyncio.run(analyze())
    assert [item["query"] for item in citations(messages, "data_citations")] == ["bp", "qty"]
    assert "".join(msg.get("content", "") for msg in messages if msg.get("type") == "text") == "总结:bp\n\n总结:qty"


def test_final_sse_summary_is_independent_of_output_node_text(monkeypatch):
    workflow = graph()
    workflow["nodes"][-1]["data"]["output_config"] = {"content_fields": [
        {"source_mode": "const", "const_value": "输出节点确认的最终总结"}]}
    install_workflows(monkeypatch, {1: workflow})
    messages = asyncio.run(analyze())
    assert "".join(msg.get("content", "") for msg in messages if msg.get("type") == "text") == "总结:final"


@pytest.mark.parametrize("explicit_empty", [False, True])
def test_empty_output_does_not_suppress_final_sse_summary(monkeypatch, explicit_empty):
    workflow = graph(hidden=True)
    config = {"content_fields": [{"source_mode": "const", "const_value": ""}]} if explicit_empty else {}
    workflow["nodes"][-1]["data"]["output_config"] = config
    install_workflows(monkeypatch, {1: workflow})
    messages = asyncio.run(analyze())
    text = "".join(msg.get("content", "") for msg in messages if msg.get("type") == "text")
    assert text == "总结:final"
    assert len(citations(messages, "data_citations")) == len(citations(messages, "chart_citations")) == 1


@pytest.mark.parametrize("hidden", [False, True])
@pytest.mark.parametrize("output_ref", ["final.trace_id", "bp.trace_id", "final.sql"])
def test_internal_output_fields_do_not_replace_final_sse_results(monkeypatch, hidden, output_ref):
    workflow = graph(hidden)
    workflow["nodes"][-1]["data"]["output_config"] = {"content_template": "{{" + output_ref + "}}"}
    install_workflows(monkeypatch, {1: workflow})
    messages = asyncio.run(analyze())
    assert "".join(msg.get("content", "") for msg in messages if msg.get("type") == "text") == "总结:final"
    for kind in ("sql_citations", "data_citations"):
        assert [item["query"] for item in citations(messages, kind)] == ["final"]
    assert [item["query"] for item in citations(messages, "chart_citations")] == ["图表:final"]


@pytest.mark.parametrize("hidden", [False, True])
def test_nested_trace_output_keeps_workflow_output_and_sse_summary_separate(monkeypatch, hidden):
    from uuid import UUID

    child = graph(hidden)
    child["nodes"][-1]["data"]["output_config"]["content_fields"] = [{"source_ref": "final.trace_id"}]
    parent = {"nodes": [node("start", "start"), node("child", "agent", agent_config={
        "target_app_id": 2, "target_version_id": 2, "sse_output_thoughts": not hidden}),
        node("out", "output", output_config={"content_fields": [{"source_ref": "child.output"}]})],
        "edges": [{"source": "start", "target": "child"}, {"source": "child", "target": "out"}]}
    install_workflows(monkeypatch, {1: parent, 2: child})

    async def raw_run():
        return [json.loads(chunk[6:]) async for chunk in workflow_engine.run_agent_workflow_stream(MagicMock(), 1, 1, {})]

    raw_events = asyncio.run(raw_run())
    assert str(UUID(raw_events[-1]["output"])) == raw_events[-1]["output"]
    messages = asyncio.run(analyze())
    assert "".join(msg.get("content", "") for msg in messages if msg.get("type") == "text") == "总结:final"
    assert [item["query"] for item in citations(messages, "data_citations")] == ["final"]


@pytest.mark.parametrize("content", ["普通对话的回复", ""])
def test_workflow_without_lab_results_keeps_existing_output(monkeypatch, content):
    workflow = {"nodes": [node("start", "start"), node("out", "output", output_config={"content_template": content})],
                "edges": [{"source": "start", "target": "out"}]}
    install_workflows(monkeypatch, {1: workflow})
    messages = asyncio.run(analyze())
    assert "".join(msg.get("content", "") for msg in messages if msg.get("type") == "text") == content


def test_legacy_thought_runner_uses_sse_summary_for_display():
    from app.services.agent_app.workflow_output import stream_workflow_output

    async def runner(*args, **kwargs):
        yield frame({"type": "thought", "node_id": "lab", "thought": {
            "tag": "实验室", "payload": {"type": "summary", "delta": "SSE 总结"}}})
        yield frame({"status": "done", "output": "内部输出"})

    async def run():
        return [message async for message in stream_workflow_output(MagicMock(), 1, 1, {}, runner=runner)]

    assert asyncio.run(run()) == [{"type": "text", "content": "SSE 总结"}]


@pytest.mark.parametrize("hidden", [False, True])
@pytest.mark.parametrize("merged", [False, True])
def test_result_switch_hides_results_without_hiding_execution_traces(monkeypatch, hidden, merged):
    workflow = graph(hidden, merged)
    disabled_node = "final" if merged else "bp"
    for item in workflow["nodes"]:
        if item["id"] == disabled_node:
            item["data"]["lab_config"]["sse_output_results"] = False
    install_workflows(monkeypatch, {1: workflow})
    messages = asyncio.run(analyze())
    assert any(message.get("type") == "trace" for message in messages)
    text = "".join(message.get("content", "") for message in messages if message.get("type") == "text")
    assert text == ("" if merged else "总结:qty")
    for kind in ("sql_citations", "data_citations", "chart_citations"):
        assert len(citations(messages, kind)) == (0 if merged else 1)
    if not merged:
        assert citations(messages, "data_citations")[0]["query"] == "qty"


@pytest.mark.parametrize("hidden", [False, True])
@pytest.mark.parametrize("parent_enabled,lab_enabled", [(False, True), (True, False), (True, True)])
def test_nested_result_switches_compose_without_restoring_hidden_results(monkeypatch, hidden, parent_enabled, lab_enabled):
    child = graph(hidden)
    child["nodes"][-2]["data"]["lab_config"]["sse_output_results"] = lab_enabled
    workflows = {3: child}
    for app_id, child_id in [(2, 3), (1, 2)]:
        workflows[app_id] = {"nodes": [node("start", "start"), node("child", "agent", agent_config={
            "target_app_id": child_id, "target_version_id": child_id,
            "sse_output_thoughts": not hidden, "sse_output_results": parent_enabled}),
            node("out", "output", output_config={"content_template": "内部输出"})],
            "edges": [{"source": "start", "target": "child"}, {"source": "child", "target": "out"}]}
    install_workflows(monkeypatch, workflows)
    messages = asyncio.run(analyze())
    text = "".join(message.get("content", "") for message in messages if message.get("type") == "text")
    assert text == ("总结:final" if parent_enabled and lab_enabled else "")
    assert len(citations(messages, "data_citations")) == int(parent_enabled and lab_enabled)


def test_empty_final_lab_results_do_not_restore_intermediate_results_or_workflow_output(monkeypatch):
    workflow = graph(hidden=True)
    workflow["nodes"][-1]["data"]["output_config"] = {"content_template": "内部输出"}
    install_workflows(monkeypatch, {1: workflow})
    original = lab.stream_lab_bailian_sse

    async def empty_final(db, spec, **kwargs):
        if spec.content == "final":
            return
        async for chunk in original(db, spec, **kwargs):
            yield chunk

    monkeypatch.setattr(lab, "stream_lab_bailian_sse", empty_final)
    messages = asyncio.run(analyze())
    assert not any(message.get("type") in {"text", "sql_citations", "data_citations", "chart_citations"}
                   for message in messages)


@pytest.mark.parametrize("hidden", [False, True])
@pytest.mark.parametrize("summary_enabled", [False, True])
@pytest.mark.parametrize("chart_enabled", [False, True])
def test_lab_generation_options_control_final_sse_content(monkeypatch, hidden, summary_enabled, chart_enabled):
    from app.services.autobi import lab_bailian_gateway, lab_pipeline_runner as pipeline, lab_runtime

    workflow = {"nodes": [node("start", "start"), lab_node("final", hidden), node("out", "output",
        output_config={"content_fields": [{"source_ref": "final.trace_id"}]})],
        "edges": [{"source": "start", "target": "final"}, {"source": "final", "target": "out"}]}
    install_workflows(monkeypatch, {1: workflow})
    rows = [{"city": "上海", "sales": "-9.53115899825276645300"}, {"city": "北京", "sales": "0.00000000000001"}]
    config = {"model_bindings": {"bi_summary": {"provider_id": 1, "model_name": "test"}},
        "request": {"advanced_config": {
            "bi_summary_config": {"enable": summary_enabled, "prompt": "Summarize {{sql_data}}"},
            "chart_drawing_config": {"enable": chart_enabled, "prompt": "Draw {{sql_result_json}}"}}}}
    monkeypatch.setattr(lab, "build_lab_run_spec_from_project_id", lambda *a, **kw: SimpleNamespace(
        content=kw["content"], lab_config=config, project_id=1, project_name="lab", knowledge_base_id=1, features={}))
    monkeypatch.setattr(lab, "collect_lab_run_json", lab_runtime.collect_lab_run_json)
    monkeypatch.setattr(lab, "stream_lab_bailian_sse", lab_bailian_gateway.stream_lab_bailian_sse)
    monkeypatch.setattr(lab_bailian_gateway, "trace_get", lambda *a: {})
    monkeypatch.setattr(pipeline, "_persist_trace", AsyncMock(side_effect=lambda *a: None))
    original_dispatch = pipeline._dispatch_step
    model_calls = []

    async def dispatch(db, sid, query, cfg, kb_id, acc, by_step, **kwargs):
        if sid == 15:
            acc["generated_sql"] = SQL
            return {}, {"sql": SQL}
        if sid == 16:
            return {}, {"columns": ["city", "sales"], "rows": rows, "row_count": 2}
        if sid in (17, 18):
            return await original_dispatch(db, sid, query, cfg, kb_id, acc, by_step, **kwargs)
        return {}, {"skipped": True}

    async def summary(*args, **kwargs):
        model_calls.append("summary")
        yield "实验室总"
        yield "结原文"

    async def chart(*args, **kwargs):
        model_calls.append("chart")
        return '{"type":"A","xaxis":["city"],"yaxis":["sales"],"title":"销售"}'

    monkeypatch.setattr(pipeline, "_dispatch_step", dispatch)
    monkeypatch.setattr(pipeline.ChatService, "stream_chat_text_deltas", summary)
    monkeypatch.setattr(pipeline, "_call_llm", chart)
    messages = asyncio.run(analyze())
    assert "".join(message.get("content", "") for message in messages if message.get("type") == "text") == (
        "实验室总结原文" if summary_enabled else "")
    assert ("summary" in model_calls) is summary_enabled
    assert ("chart" in model_calls) is chart_enabled
    assert citations(messages, "sql_citations")[0]["sql"] == SQL
    assert citations(messages, "data_citations")[0]["data"] == rows
    assert len(citations(messages, "chart_citations")) == int(chart_enabled)


@pytest.mark.parametrize("hidden", [False, True])
@pytest.mark.parametrize("output_field", ["summary", "trace_id"])
def test_legacy_api_keeps_final_chart_and_existing_envelope(monkeypatch, hidden, output_field):
    workflow = graph(hidden)
    workflow["nodes"][-1]["data"]["output_config"]["content_fields"] = [{"source_ref": "final." + output_field}]
    install_workflows(monkeypatch, {1: workflow})
    monkeypatch.setattr(external_chat, "get_agent_app_by_id", lambda *a: SimpleNamespace(id=1))
    monkeypatch.setattr(external_chat, "get_version_for_app", lambda *a: SimpleNamespace(id=1))
    monkeypatch.setattr(external_chat, "_create_log", lambda *a: SimpleNamespace())
    monkeypatch.setattr(external_chat, "_finish_log", lambda *a, **kw: None)
    async def run():
        return [json.loads(chunk[6:]) async for chunk in external_chat.external_agent_chat_stream(
            MagicMock(), ExternalAgentChatRequest(app_id=1, version_id=1, message="销售"))]
    frames = asyncio.run(run())
    for payload in frames:
        assert set(payload) == {"data", "id", "event"}
        assert set(payload["data"]) == {"end", "messages", "outSessionId", "questionId", "rewriteQuestion", "role"}
    messages = [message for payload in frames for message in payload["data"]["messages"] if message]
    assert all(set(message) == {"actionId", "type", "content", "features"} for message in messages)
    assert all(set(item) <= {"id", "query", "chart"} for item in citations(messages, "chart_citations"))
    assert [item["query"] for item in citations(messages, "chart_citations")] == ["图表:final"]
    assert "".join(msg.get("content", "") for msg in messages if msg.get("type") == "text") == "总结:final"
    assert frames[-1]["data"]["end"] is True


@pytest.mark.parametrize("hidden", [False, True])
def test_stream_persistence_and_full_export_storage_share_final_results(factory, monkeypatch, hidden):
    install_workflows(monkeypatch, {1: graph(hidden)})
    body = ChatRequest(user=USER.user, query="销售")
    with factory() as db:
        mid = chat.prepare_chat(db, body, USER)
    async def runner(*args):
        for msg in await analyze():
            yield msg
    events = asyncio.run(collect(mid, body, factory, runner))
    result_nodes = [event["data"] for event in events if event["event"] == "node_finished"
                    and event["data"]["node_type"] in {"sql", "table", "chart"}]
    assert [item["node_type"] for item in result_nodes] == ["sql", "table", "chart"]
    table = next(item["outputs"] for item in result_nodes if item["node_type"] == "table")
    chart = next(item["outputs"] for item in result_nodes if item["node_type"] == "chart")
    assert table["total_rows"] == 80 and len(table["rows"]) == 50 and table["can_export"]
    assert chart["data_ref"] == table["data_ref"]
    schemas = Path(__file__).resolve().parents[2] / "docs/api/schemas"
    for kind, outputs in [("table", table), ("chart", chart)]:
        schema = json.loads((schemas / (kind + ".schema.json")).read_text())
        assert set(outputs) == set(schema["properties"])
    with factory() as db:
        message = db.get(ChatBIMessage, mid)
        assert message.answer == "总结:final"
        assert [item["type"] for item in message.content] == ["text", "sql", "table", "chart"]
        results = db.query(ChatBIResult).filter_by(message_id=mid).all()
        assert len(results) == 1 and results[0].rows == ROWS and results[0].complete
    terminal = next(event for event in events if event["event"] == "workflow_finished")
    assert terminal["data"]["outputs"] == {"answer": "总结:final"}


def test_parallel_charts_link_to_their_own_tables_without_new_wire_fields(factory, monkeypatch):
    install_workflows(monkeypatch, {1: graph(hidden=True, merged=False)})
    body = ChatRequest(user=USER.user, query="销售")
    with factory() as db:
        mid = chat.prepare_chat(db, body, USER)
    async def runner(*args):
        for message in await analyze():
            yield message
    events = asyncio.run(collect(mid, body, factory, runner))
    finished = [event["data"] for event in events if event["event"] == "node_finished"]
    tables = [item["outputs"] for item in finished if item["node_type"] == "table"]
    charts = [item["outputs"] for item in finished if item["node_type"] == "chart"]
    assert len(tables) == len(charts) == 2
    assert [chart["data_ref"] for chart in charts] == [table["data_ref"] for table in tables]
    assert len({chart["data_ref"] for chart in charts}) == 2


@pytest.mark.parametrize("hidden", [False, True])
def test_identical_results_from_independent_branches_are_not_deduplicated(monkeypatch, hidden):
    workflow = graph(hidden, merged=False)
    for item in workflow["nodes"]:
        if item["data"]["kind"] == "lab":
            item["data"]["lab_config"]["input_mapping"][0]["const_value"] = "相同的问题"
    install_workflows(monkeypatch, {1: workflow})
    messages = asyncio.run(analyze())
    tables, charts = citations(messages, "data_citations"), citations(messages, "chart_citations")
    assert len(tables) == len(charts) == 2
    assert tables[0]["data"] == tables[1]["data"]
    sources = [msg["actionId"] for msg in messages if msg.get("type") == "data_citations"]
    assert len(set(sources)) == 2


@pytest.mark.parametrize("hidden", [False, True])
def test_empty_parallel_branch_does_not_hide_the_nonempty_final_result(monkeypatch, hidden):
    workflow = graph(hidden, merged=False)
    workflow["nodes"][2]["data"]["lab_config"]["input_mapping"][0]["const_value"] = ""
    install_workflows(monkeypatch, {1: workflow})
    messages = asyncio.run(analyze())
    assert [item["query"] for item in citations(messages, "data_citations")] == ["bp"]
    assert len(citations(messages, "chart_citations")) == 1


def test_hidden_lab_failure_is_not_masked_by_filtered_output_vars(monkeypatch):
    workflow = graph(hidden=True)
    for item in workflow["nodes"]:
        if item["data"]["kind"] == "lab":
            item["data"]["lab_config"]["output_vars"] = ["summary"]
    install_workflows(monkeypatch, {1: workflow})
    async def failed(db, spec, **kwargs):
        yield frame({"status_code": "FAILED", "message": {"type": "text", "content": "查询失败"}})
    monkeypatch.setattr(lab, "stream_lab_bailian_sse", failed)
    seen = []
    async def run():
        async for message in runtime.run_analysis(MagicMock(), "agent:1:1", "销售", {}, "cid", [], USER):
            seen.append(message)
    with pytest.raises(RuntimeError, match="实验室执行失败"):
        asyncio.run(run())
    assert not any(message.get("type") in {"text", "sql_citations", "data_citations", "chart_citations"} for message in seen)


@pytest.mark.parametrize("hidden", [False, True])
def test_client_stop_cancels_an_active_workflow_without_delivering_partial_results(monkeypatch, hidden):
    install_workflows(monkeypatch, {1: graph(hidden)})
    async def scenario():
        started, cancelled = asyncio.Event(), asyncio.Event()
        async def slow_stream(*args, **kwargs):
            try:
                started.set()
                yield frame({"message": {"type": "progress", "features": {"progress": "等待查询"}}})
                await asyncio.Event().wait()
            finally:
                cancelled.set()
        async def slow_collect(*args, **kwargs):
            try:
                started.set()
                await asyncio.Event().wait()
            finally:
                cancelled.set()
        monkeypatch.setattr(lab, "stream_lab_bailian_sse", slow_stream)
        monkeypatch.setattr(lab, "collect_lab_run_json", slow_collect)
        iterator = runtime.run_analysis(MagicMock(), "agent:1:1", "销售", {}, "cid", [], USER)
        assert (await anext(iterator))["type"] == "trace_id"
        request = asyncio.create_task(anext(iterator))
        await asyncio.wait_for(started.wait(), timeout=1)
        if hidden:
            request.cancel()
            with pytest.raises(asyncio.CancelledError):
                await request
        else:
            assert (await request)["type"] in {"trace", "progress"}
        await iterator.aclose()
        await asyncio.wait_for(cancelled.wait(), timeout=1)
    asyncio.run(scenario())


@pytest.mark.parametrize("hidden", [False, True])
def test_debug_node_snapshots_keep_existing_fields_and_thought_switch(monkeypatch, hidden):
    install_workflows(monkeypatch, {1: graph(hidden)})
    async def run():
        return [json.loads(chunk[6:]) async for chunk in workflow_engine.run_agent_workflow_stream(MagicMock(), 1, 1, {})]
    events = asyncio.run(run())
    snapshots = [event["output_snapshot"] for event in events if event.get("kind") == "lab" and event.get("status") == "done"]
    assert all(set(snapshot) == {"trace_id", "summary", "sql", "error"} for snapshot in snapshots)
    payloads = [event["thought"]["payload"] for event in events if event.get("type") == "thought"]
    assert any(payload.get("type") == "lab_trace" for payload in payloads)
    assert any(isinstance(payload.get("message"), dict) for payload in payloads) is (not hidden)
    assert set(events[-1]) == {"status", "output", "trace_id", "steps", "elapsed_ms"}


def test_full_data_upgrade_is_preserved_in_final_table(monkeypatch):
    install_workflows(monkeypatch, {1: graph()})
    original = lab.stream_lab_bailian_sse
    async def with_preview(db, spec, **kwargs):
        async for chunk in original(db, spec, **kwargs):
            event = json.loads(chunk[6:])
            message = event["message"]
            if message.get("type") == "data_citations":
                item = message["features"]["data_citations"][0]
                preview = {**item, "id": 1, "data": item["data"][:10], "truncated": True}
                yield frame({"message": {**message, "features": {"data_citations": [preview]}}})
                full = {**item, "id": 1}
                yield frame({"message": {**message, "type": "full_data_citations", "features": {"full_data_citations": [full]}}})
            else:
                yield chunk
    monkeypatch.setattr(lab, "stream_lab_bailian_sse", with_preview)
    messages = asyncio.run(analyze())
    tables = citations(messages, "data_citations")
    assert len(tables) == 1 and tables[0]["data"] == ROWS and not tables[0].get("truncated")


def test_distinct_charts_in_one_final_result_are_preserved(monkeypatch):
    install_workflows(monkeypatch, {1: graph()})
    original = lab.stream_lab_bailian_sse
    async def with_second_chart(db, spec, **kwargs):
        async for chunk in original(db, spec, **kwargs):
            yield chunk
        chart = {"type": "A", "columns": [{"key": "city", "target": "xaxis"}, {"key": "sales", "target": "yaxis"}],
                 "data": [{"city": "额外分组", "sales": 99}]}
        yield frame({"message": {"type": "chart_citations", "features": {"chart_citations": [
            {"id": "second", "query": "另一张最终图表", "chart": chart}]}}})
    monkeypatch.setattr(lab, "stream_lab_bailian_sse", with_second_chart)
    charts = citations(asyncio.run(analyze()), "chart_citations")
    assert [item["query"] for item in charts] == ["图表:final", "另一张最终图表"]


def test_repeated_chart_event_is_not_duplicated_in_stream_or_history(factory):
    body = ChatRequest(user=USER.user, query="销售")
    with factory() as db:
        mid = chat.prepare_chat(db, body, USER)
    chart = {"type": "A", "columns": [{"key": "city", "target": "xaxis"}, {"key": "sales", "target": "yaxis"}], "data": ROWS}
    async def runner(*args):
        message = {"type": "chart_citations", "actionId": "same-run", "features": {"chart_citations": [
            {"id": "same-chart", "query": "城市销售", "chart": chart}]}}
        yield message
        yield message
    events = asyncio.run(collect(mid, body, factory, runner))
    assert sum(event["event"] == "node_finished" and event["data"]["node_type"] == "chart" for event in events if "data" in event) == 1
    with factory() as db:
        assert sum(item["type"] == "chart" for item in db.get(ChatBIMessage, mid).content) == 1


@pytest.mark.parametrize("hidden", [False, True])
@pytest.mark.parametrize("output_field", ["summary", "trace_id"])
def test_http_stream_and_exports_keep_the_published_contract(factory, monkeypatch, hidden, output_field):
    import importlib
    from io import BytesIO
    from urllib.parse import urlparse
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from openpyxl import load_workbook
    from app.core.database import get_db
    from app.models.chatbi import ChatBIExport
    from app.services.chatbi import exports

    module = importlib.import_module("app.routers.chatbi.router")
    workflow = graph(hidden)
    workflow["nodes"][-1]["data"]["output_config"]["content_fields"] = [{"source_ref": "final." + output_field}]
    install_workflows(monkeypatch, {1: workflow})
    real_runner = workflow_engine.run_agent_workflow_stream
    async def isolated_runner(db, *args, **kwargs):
        async for chunk in real_runner(MagicMock(), *args, **kwargs):
            yield chunk
    monkeypatch.setattr(workflow_engine, "run_agent_workflow_stream", isolated_runner)
    monkeypatch.setattr(chat, "SessionLocal", factory)
    from app.services.chatbi import request_context
    app = FastAPI()
    app.include_router(module.router)
    def database():
        with factory() as db:
            yield db
    app.dependency_overrides[get_db] = database
    app.dependency_overrides[module.service_auth] = lambda: SimpleNamespace(
        user=lambda value: USER, chat_runtime=lambda db: "agent:1:1")
    with TestClient(app) as client:
        response = client.post("/api/service/chat-messages", json={"user": USER.user, "query": "销售", "inputs": {},
            "conversation_id": "", "response_mode": "streaming", "auto_generate_name": False})
        assert response.status_code == 200 and "text/event-stream" in response.headers["content-type"]
        events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
        assert {event["event"] for event in events} <= {
            "workflow_started", "node_started", "node_finished", "message", "message_end", "workflow_finished"}
        assert not any("collector" in json.dumps(event, ensure_ascii=False) for event in events)
        assert events[-1]["data"]["outputs"] == {"answer": "总结:final"}
        tables = [event for event in events if event["event"] == "node_finished" and event["data"]["node_type"] == "table"]
        assert len(tables) == 1
        table = tables[0]
        exported = client.post("/api/service/exports/xlsx", json={"user": USER.user,
            "conversation_id": table["conversation_id"], "message_id": table["message_id"],
            "data_ref": table["data"]["outputs"]["data_ref"]})
        assert exported.status_code == 202
        task = exported.json()
        assert set(task) == {"task_id", "file_id", "file_type", "summaryType", "status", "error", "file_name",
                             "file_size", "created_at", "finished_at", "expires_at", "downloadable", "expired", "files"}
        asyncio.run(exports.process_export(task["task_id"], factory=factory))
        state = client.get("/api/service/export-tasks/" + task["task_id"], params={"user": USER.user}).json()
        assert state["status"] == "succeeded"
        link = client.get("/api/service/files/" + state["file_id"] + "/download-url", params={"user": USER.user}).json()
        assert set(link) == {"file_id", "file_name", "downloadable", "url", "expires_at", "file_expires_at"}
        parsed = urlparse(link["url"])
        download = client.get(parsed.path + "?" + parsed.query)
        assert download.status_code == 200
        sheet = load_workbook(BytesIO(download.content)).active
        assert sheet.max_row == 81 and sheet.cell(81, 2).value == 79
        ppt = client.post("/api/service/exports/ppt", json={"user": USER.user, "conversation_id": table["conversation_id"],
            "message_ids": [table["message_id"]], "summaryType": "FULL_SUMMARY"})
        assert ppt.status_code == 202
        with factory() as db:
            models = exports.ppt_models(db, db.get(ChatBIExport, ppt.json()["task_id"]))
            assert len(models) == 1
            answer_model = models[0]["ppt_answer_models"][0]
            assert answer_model["answer"] == "总结:final"
            assert len(answer_model["excel_data"]) == len(answer_model["chart_data"]) == 1
            assert answer_model["excel_data"][0]["data"] == ROWS
