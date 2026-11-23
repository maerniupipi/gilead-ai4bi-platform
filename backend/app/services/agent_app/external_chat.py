"""External SSE wrapper for agent workflow execution."""
from __future__ import annotations

import json
import logging
import time
import uuid
from contextlib import aclosing
from ...core.execution import read_database
from typing import Any, AsyncGenerator, Dict, Optional

from sqlalchemy.orm import Session

from ...models.agent_app import AgentAppCallLog
from ...repositories.agent_app.repository import (
    get_agent_app_by_id,
    get_output_version_for_app,
    get_version_for_app,
)
from ...schemas.external_agent import ExternalAgentChatRequest
from .workflow_engine import run_agent_workflow_stream

logger = logging.getLogger(__name__)


def _sse(payload: Dict[str, Any]) -> str:
    return "data: " + json.dumps(payload, ensure_ascii=False) + "\n\n"


def _message(
    *,
    msg_type: str,
    content: str = "",
    features: Optional[Dict[str, Any]] = None,
    action_id: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "actionId": action_id or uuid.uuid4().hex,
        "content": content,
        "features": features or {},
        "type": msg_type,
    }


def _frame(
    *,
    seq: int,
    out_session_id: str,
    question_id: int,
    rewrite_question: str,
    message: Optional[Dict[str, Any]],
    end: bool = False,
) -> Dict[str, Any]:
    return {
        "data": {
            "end": end,
            "messages": [message],
            "outSessionId": out_session_id,
            "questionId": question_id,
            "rewriteQuestion": rewrite_question,
            "role": "assistant",
        },
        "id": str(seq),
        "event": "true" if end else "false",
    }


def _build_inputs(body: ExternalAgentChatRequest) -> Dict[str, Any]:
    inputs = dict(body.inputs or {})
    message = body.message.strip()
    for key in ("question", "input", "user_message", "message"):
        inputs.setdefault(key, message)
    inputs.setdefault("conversation_id", body.conversation_id)
    return inputs


def _extract_data_line(chunk: str) -> Optional[Dict[str, Any]]:
    for line in str(chunk or "").splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        raw = line[5:].strip()
        if not raw:
            continue
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None
    return None


def _json_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text:
        return ""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def _features_dict(value: Any) -> Dict[str, Any]:
    parsed = _json_payload(value)
    return parsed if isinstance(parsed, dict) else {}


def _has_axis(chart: Dict[str, Any], target: str) -> bool:
    columns = chart.get("columns") if isinstance(chart, dict) else None
    return isinstance(columns, list) and any(
        isinstance(item, dict) and item.get("target") == target and item.get("key")
        for item in columns
    )


def _valid_chart(chart: Any) -> bool:
    if not isinstance(chart, dict):
        return False
    data = chart.get("data")
    return (
        bool(chart.get("type"))
        and isinstance(data, list)
        and bool(data)
        and _has_axis(chart, "xaxis")
        and _has_axis(chart, "yaxis")
    )


def _chart_from_markdown(content: str) -> Optional[Dict[str, Any]]:
    text = str(content or "").strip()
    if not text:
        return None
    import re

    match = re.search(r"```[\w-]*\s*([\s\S]*?)```", text)
    raw = (match.group(1) if match else text).strip()
    if not raw.startswith("{"):
        return None
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    if _valid_chart(obj.get("chart")):
        return obj.get("chart")
    chart = {
        "type": obj.get("type"),
        "columns": obj.get("columns"),
        "data": obj.get("data") or obj.get("rows"),
    }
    return chart if _valid_chart(chart) else None


def _chart_citation_message(
    *,
    features: Dict[str, Any],
    content: str = "",
    action_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    if isinstance(features.get("chart_citations"), list) and features.get("chart_citations"):
        return _message(msg_type="chart_citations", features={"chart_citations": features["chart_citations"]}, action_id=action_id)

    chart = features.get("bootcamp_chart") or features.get("chart")
    if not _valid_chart(chart):
        chart = _chart_from_markdown(content)
    if not _valid_chart(chart):
        return None

    chart_spec = features.get("chart_spec") if isinstance(features.get("chart_spec"), dict) else {}
    markdown = features.get("markdown") if isinstance(features.get("markdown"), dict) else {}
    chart_intent = markdown.get("chart_intent") if isinstance(markdown.get("chart_intent"), dict) else {}
    return _message(
        msg_type="chart_citations",
        features={
            "chart_citations": [
                {
                    "id": action_id or uuid.uuid4().hex,
                    "query": str(chart_spec.get("title") or chart_intent.get("title") or chart.get("title") or ""),
                    "chart": chart,
                }
            ]
        },
        action_id=action_id,
    )


def _progress_text(features: Dict[str, Any], content: str = "") -> str:
    return str(features.get("progress") or content or "")


def _skip_progress(text: str) -> bool:
    lowered = str(text or "").lower()
    return any(keyword in lowered for keyword in ("sql验证", "验证sql", "校验sql", "sql校验"))


def _thought_to_message(event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    tag = str(event.get("tag") or "")
    payload = _json_payload(event.get("payload"))
    if tag == "路由日志":
        return None
    if isinstance(payload, dict):
        evt_type = payload.get("type")
        if evt_type == "lab_trace" and payload.get("trace_id"):
            return _message(msg_type="trace", features={
                "lab_trace_ids": [payload["trace_id"]],
                "lab_node_id": payload.get("node_id"),
                "lab_project_id": payload.get("project_id"),
            })
        if "message" in payload and isinstance(payload.get("message"), dict):
            msg = payload["message"]
            msg_type = str(msg.get("type") or "text")
            content = str(msg.get("content") or "")
            features = _features_dict(msg.get("features"))
            if msg_type in ("progress", "progress_result") and _skip_progress(_progress_text(features, content)):
                return None
            if msg_type == "text" and not content:
                return None
            if msg_type in ("lab_render", "markdown"):
                return _chart_citation_message(features=features, content=content, action_id=msg.get("action_id") or payload.get("id"))
            if msg_type == "chart_citations":
                chart_msg = _chart_citation_message(features=features, content=content, action_id=msg.get("action_id") or payload.get("id"))
                if chart_msg:
                    return chart_msg
            return _message(
                msg_type=msg_type,
                content=content,
                features=features,
                action_id=msg.get("action_id") or payload.get("id"),
            )
        if evt_type in ("bailian_progress", "progress"):
            features = payload.get("features") if isinstance(payload.get("features"), dict) else {}
            progress = str(payload.get("progress") or features.get("progress") or "")
            if _skip_progress(progress):
                return None
            return _message(
                msg_type="progress",
                content=str(payload.get("content") or ""),
                features={"progress": progress},
                action_id=payload.get("action_id"),
            )
        if evt_type in ("lab_render", "markdown", "chart_citations", "bailian_chart"):
            features = _features_dict(payload.get("features"))
            if evt_type == "bailian_chart":
                features = {
                    "chart_spec": payload.get("chart_spec") if isinstance(payload.get("chart_spec"), dict) else {},
                    "bootcamp_chart": payload.get("chart") or payload.get("bootcamp_chart"),
                }
            chart_msg = _chart_citation_message(
                features=features,
                content=str(payload.get("content") or ""),
                action_id=payload.get("action_id"),
            )
            return chart_msg
        if evt_type in ("text", "statistics", "sql_citations", "data_citations"):
            content = str(payload.get("content") or "")
            if evt_type == "text" and not content:
                return None
            return _message(
                msg_type=str(evt_type),
                content=content,
                features=_features_dict(payload.get("features")),
                action_id=payload.get("action_id"),
            )
        if evt_type == "summary":
            delta = str(payload.get("delta") or "")
            return _message(msg_type="text", content=delta) if delta else None
        if evt_type == "bailian_sql":
            query = str(payload.get("query") or "")
            sql = str(payload.get("sql") or "")
            return _message(
                msg_type="sql_citations",
                features={"sql_citations": [{"query": query, "sql": sql, "id": 1}]},
            )
        if evt_type == "bailian_data":
            query = str(payload.get("query") or "")
            rows = payload.get("data") if isinstance(payload.get("data"), list) else []
            return _message(
                msg_type="data_citations",
                content=f"```table|SQL Data - {query}\n{json.dumps({'data': rows}, ensure_ascii=False)}\n```",
                features={"data_citations": [{"query": query, "data": rows}]},
            )
        if evt_type == "error":
            return _message(msg_type="text", content=str(payload.get("message") or ""))
        if "type" in payload and "progress" in payload:
            return _message(
                msg_type=str(payload.get("type") or "progress"),
                features={"progress": str(payload.get("progress") or "")},
            )
    if tag == "进度" and payload:
        return _message(msg_type="progress", features={"progress": str(payload)})
    if tag == "复杂分类" and payload:
        return _message(msg_type="progress_result", features={"progress": f"当前问题分类为：{payload}"})
    return None


def _create_log(db: Session, body: ExternalAgentChatRequest, version_id: Optional[int]) -> AgentAppCallLog:
    row = AgentAppCallLog(
        agent_app_id=int(body.app_id),
        version_id=int(version_id) if version_id is not None else None,
        caller=(body.caller or "")[:64] or None,
        conversation_id=(body.conversation_id or "")[:128] or None,
        request_text=_log_text(body.message, 4000),
        status="running",
    )
    db.add(row)
    try:
        db.commit()
        db.refresh(row)
    except Exception:
        db.rollback()
        logger.exception("failed to create external agent call log")
    return row


def _log_text(value: str, limit: int) -> str:
    text = str(value or "")
    # Some local MySQL schemas are still utf8/utf8mb3. Keep the API response
    # intact, but avoid letting 4-byte characters break best-effort call logs.
    return "".join(ch for ch in text if ord(ch) <= 0xFFFF)[:limit]


def _finish_log(
    db: Session,
    row: AgentAppCallLog,
    *,
    status: str,
    started: float,
    output: str = "",
    error: str = "",
) -> None:
    if isinstance(row, AgentAppCallLog):
        db.add(row)
    row.status = status
    row.elapsed_ms = int((time.perf_counter() - started) * 1000)
    row.output_preview = _log_text(output, 4000) if output else None
    row.error_message = _log_text(error, 4000) if error else None
    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("failed to finish external agent call log")


async def external_agent_chat_stream(
    db: Session,
    body: ExternalAgentChatRequest,
) -> AsyncGenerator[str, None]:
    started = time.perf_counter()
    log_row: Optional[AgentAppCallLog] = None
    out_session_id = body.conversation_id or uuid.uuid4().hex
    question_id = int((body.inputs or {}).get("question_id") or int(time.time() * 1000))
    rewrite_question = ""
    seq = 0
    app = await read_database(db, get_agent_app_by_id, int(body.app_id))
    if app is None:
        yield _sse(_frame(
            seq=seq,
            out_session_id=out_session_id,
            question_id=question_id,
            rewrite_question=rewrite_question,
            message=_message(msg_type="text", content="智能体不存在"),
            end=True,
        )
        )
        return

    version_id = body.version_id
    if version_id is None:
        version = await read_database(db, get_output_version_for_app, int(body.app_id))
        version_id = int(version.id) if version else None
    else:
        version = await read_database(db, get_version_for_app, int(body.app_id), int(version_id))

    if version is None or version_id is None:
        yield _sse(_frame(
            seq=seq,
            out_session_id=out_session_id,
            question_id=question_id,
            rewrite_question=rewrite_question,
            message=_message(msg_type="text", content="智能体版本不存在"),
            end=True,
        )
        )
        return

    log_row = await read_database(db, _create_log, body, int(version_id))
    output_parts: list[str] = []
    try:
        yield _sse(_frame(
            seq=seq,
            out_session_id=out_session_id,
            question_id=question_id,
            rewrite_question=rewrite_question,
            message=_message(msg_type="progress", features={"progress": "智能体执行中..."}),
        )
        )
        seq += 1
        from .workflow_output import stream_workflow_output
        async with aclosing(stream_workflow_output(db, int(body.app_id), int(version_id),
                _build_inputs(body), runner=run_agent_workflow_stream)) as messages:
            async for msg in messages:
                if msg.get("type") == "trace_id":
                    msg = _message(msg_type="trace", features={"workflow_trace_id": msg.get("trace_id")})
                else:
                    msg = _message(msg_type=msg.get("type") or "text", content=msg.get("content") or "",
                        features=_features_dict(msg.get("features")),
                        action_id=msg.get("actionId") or msg.get("action_id"))
                if msg.get("type") == "text" and msg.get("content"):
                    output_parts.append(str(msg["content"]))
                    current_text = "".join(output_parts)
                    if current_text.startswith("【问题】"):
                        rewrite_question = current_text.split("【理解】", 1)[0]
                yield _sse(_frame(seq=seq, out_session_id=out_session_id, question_id=question_id,
                    rewrite_question=rewrite_question, message=msg))
                seq += 1

        output = "".join(output_parts)
        await read_database(db, _finish_log, log_row, status="success", started=started, output=output)
        yield _sse(_frame(
            seq=seq,
            out_session_id=out_session_id,
            question_id=question_id,
            rewrite_question=rewrite_question,
            message=_message(msg_type="text"),
            end=True,
        )
            )
    except Exception as exc:
        error = str(exc)
        if log_row is not None:
            await read_database(db, _finish_log, log_row, status="error", started=started, error=error)
        yield _sse(_frame(
            seq=seq,
            out_session_id=out_session_id,
            question_id=question_id,
            rewrite_question=rewrite_question,
            message=_message(msg_type="text", content=error),
            end=True,
        )
        )


async def external_agent_chat_non_stream(
    db: Session,
    body: ExternalAgentChatRequest,
) -> dict:
    """非流式调用外部智能体，返回完整结果"""
    started = time.perf_counter()
    log_row: Optional[AgentAppCallLog] = None
    out_session_id = body.conversation_id or uuid.uuid4().hex
    question_id = int((body.inputs or {}).get("question_id") or int(time.time() * 1000))
    output_parts: list[str] = []
    
    app = await read_database(db, get_agent_app_by_id, int(body.app_id))
    if app is None:
        return {"answer": "智能体不存在", "session_id": out_session_id}
    
    version_id = body.version_id
    if version_id is None:
        version = await read_database(db, get_output_version_for_app, int(body.app_id))
        version_id = int(version.id) if version else None
    else:
        version = await read_database(db, get_version_for_app, int(body.app_id), int(version_id))
    
    if version is None or version_id is None:
        return {"answer": "智能体版本不存在", "session_id": out_session_id}
    
    log_row = await read_database(db, _create_log, body, int(version_id))
    
    try:
        from ...services.agent_app.workflow_engine import run_agent_workflow
        result = await run_agent_workflow(
            db,
            agent_app_id=int(body.app_id),
            version_id=int(version_id),
            inputs=_build_inputs(body),
        )
        
        output = ""
        if isinstance(result, dict):
            output = result.get("output") or result.get("answer") or str(result)
        else:
            output = str(result)
        
        output_parts.append(output)
        final_output = "".join(output_parts)
        
        await read_database(db, _finish_log, log_row, status="success", started=started, output=final_output)
        
        return {
            "answer": final_output,
            "session_id": out_session_id,
            "question_id": question_id,
        }
    except Exception as exc:
        error = str(exc)
        if log_row is not None:
            await read_database(db, _finish_log, log_row, status="error", started=started, error=error)
        return {"answer": error, "session_id": out_session_id, "error": True}
