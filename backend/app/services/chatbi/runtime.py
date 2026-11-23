"""Translate existing analysis engines into content events, independently of HTTP/UI."""
from contextlib import aclosing
from ...core.execution import read_database
from .config import model_bindings, positive_env
from ..autobi.analysis_events import decode, features, normalize
from .diagnostics import capture_invocation, persist_capture, _capture
from .request_context import build_runtime_inputs


def _persist_execution(db, message_id):
    persist_capture(db, message_id)
    db.commit()


async def run_analysis(db, runtime, query, inputs, conversation_id, history, user):
    parts = runtime.split(":")
    trusted = build_runtime_inputs(query, inputs, conversation_id, history, user,
                                   workflow=parts[0] != 'autobi')
    if parts[0] == "autobi":
        from ..autobi.lab_runtime import build_lab_run_spec_from_project_id, stream_lab_native_sse
        spec = await read_database(db, build_lab_run_spec_from_project_id, int(parts[1]), content=query, features=trusted)
        capture_invocation('lab', {'content':query,'features':trusted}, project_id=int(parts[1]),runtime=runtime)
        capture = _capture.get()
        if capture is not None:
            await read_database(db, _persist_execution, capture['message_id'])
        # The merged config belongs to this run. Shared project settings stay untouched.
        spec.lab_config["model_bindings"] = {**spec.lab_config.get("model_bindings", {}), **model_bindings()}
        # Model calls share the deployment's question timeout instead of ending
        # early at a project's old per-model limit. The outer stream enforces the
        # total deadline, including time spent in earlier steps.
        request_config = spec.lab_config.setdefault("request", {})
        advanced = request_config.setdefault("advanced_config", {})
        for key in ("knowledge_rewrite", "nl2sql", "ner_retrieval", "bi_summary", "chart_drawing"):
            advanced[f"{key}_config"] = {
                **(advanced.get(f"{key}_config") or {}),
                "timeout_seconds": positive_env("CHATBI_CHAT_TIMEOUT", 600),
            }
        completed = False
        async for chunk in stream_lab_native_sse(db, spec, bailian_compat=True, emit_step_events=True):
            event = decode(chunk)
            if event.get("type") == "done":
                completed = True
            if event.get("type") != "bailian_progress":
                yield normalize(event)
        if not completed:
            raise RuntimeError("分析执行中断，未收到完成事件")
        return

    from ..agent_app.workflow_engine import run_agent_workflow_stream
    from ...repositories.agent_app.repository import get_output_version_for_app, get_version_for_app
    from ..agent_app.workflow_output import stream_workflow_output
    app_id = int(parts[1])
    version = await read_database(db, get_version_for_app, app_id, int(parts[2])) if parts[2] else await read_database(db, get_output_version_for_app, app_id)
    if version is None:
        raise RuntimeError("未找到已发布的智能体版本")
    if len(parts) >= 4 and (version.status not in {"published", "online"} or int(parts[3]) != (version.workflow_rev or 0)):
        from .config import APIError
        raise APIError(503, "workflow_unavailable", "绑定的工作流版本不可用或已修改，请管理员重新绑定")
    capture_invocation('agent', trusted, app_id=app_id, version_id=int(version.id),
                       workflow_rev=getattr(version,'workflow_rev',None),runtime=runtime)
    capture = _capture.get()
    if capture is not None:
        await read_database(db, _persist_execution, capture['message_id'])
    async with aclosing(stream_workflow_output(db, app_id, int(version.id), trusted,
                                              runner=run_agent_workflow_stream)) as messages:
        async for message in messages:
            yield message
