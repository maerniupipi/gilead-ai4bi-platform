"""实验室运行时编排：项目解析、配置合并、features 透传与核心流水线调用。

本模块是平台无关层。HTTP、MCP、工作流、百炼/Dify 等适配器都应先构造
``LabRunSpec``，再选择 native SSE、聚合 JSON 或平台协议包装。
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Dict, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ...schemas.autobi_gateway import LabGatewayV2Request, _effective_features
from .lab_config_merge import merge_lab_config
from .lab_features import apply_features_to_lab_config_prompts
from .lab_pipeline_runner import collect_autobi_lab_gateway_json, run_autobi_lab_gateway_sse
from .service import get_autobi_project_by_api_access_id_service, get_autobi_project_service


@dataclass(frozen=True)
class LabRunSpec:
    """一次实验室运行的稳定输入规格。"""

    content: str
    project_id: int
    project_name: Optional[str]
    api_access_id: Optional[str]
    knowledge_base_id: int
    lab_config: Dict[str, Any]
    features: Dict[str, Any]


@dataclass(frozen=True)
class LabTraceContext:
    trace_id: str
    started_at: int


def new_lab_trace_context() -> LabTraceContext:
    return LabTraceContext(trace_id=str(uuid.uuid4()), started_at=int(time.time() * 1000))


def _resolve_kb_id(row: Dict[str, Any], merged_config: Dict[str, Any]) -> int:
    kb_id: Optional[Any] = row.get("knowledge_base_id") or merged_config.get("knowledge_base_id")
    if kb_id is None:
        raise HTTPException(status_code=400, detail="项目未配置知识库")
    return int(kb_id)


def build_lab_run_spec_from_project_row(
    row: Dict[str, Any],
    *,
    content: str,
    features: Optional[Dict[str, Any]] = None,
) -> LabRunSpec:
    """从项目行构造平台无关运行规格，并完成 prompt features 预替换。"""
    user_message = (content or "").strip()
    if not user_message:
        raise HTTPException(status_code=400, detail="content 不能为空")

    from ..conversation_history import history_context_values
    feat = dict(features or {})
    feat.update(history_context_values(feat))
    merged = merge_lab_config(row["config_json"])
    merged = apply_features_to_lab_config_prompts(merged, feat)
    kb_id = _resolve_kb_id(row, merged)
    return LabRunSpec(
        content=user_message,
        project_id=int(row["id"]),
        project_name=row.get("name"),
        api_access_id=row.get("api_access_id"),
        knowledge_base_id=kb_id,
        lab_config=merged,
        features=feat,
    )




def build_lab_run_spec_from_api_request(db: Session, body: LabGatewayV2Request) -> LabRunSpec:
    row = get_autobi_project_by_api_access_id_service(db, body.id.strip())
    features = _effective_features(body)
    return build_lab_run_spec_from_project_row(
        row,
        content=body.content,
        features=features,
    )


def build_lab_run_spec_from_project_id(
    db: Session,
    project_id: int,
    *,
    content: str,
    features: Optional[Dict[str, Any]] = None,
) -> LabRunSpec:
    row = get_autobi_project_service(db, int(project_id))
    return build_lab_run_spec_from_project_row(row, content=content, features=features)


async def stream_lab_native_sse(
    db: Session,
    spec: LabRunSpec,
    *,
    trace: Optional[LabTraceContext] = None,
    bailian_compat: bool = False,
    emit_step_events: bool = False,
) -> AsyncGenerator[str, None]:
    t = trace or new_lab_trace_context()
    from ..chatbi.diagnostics import record_trace
    record_trace(t.trace_id, {'project_id':spec.project_id,'status':'running'}, kind='lab')
    async for chunk in run_autobi_lab_gateway_sse(
        db,
        user_message=spec.content,
        lab_config=spec.lab_config,
        kb_id=spec.knowledge_base_id,
        project_id=spec.project_id,
        project_name=spec.project_name,
        trace_id=t.trace_id,
        trace_started_at=t.started_at,
        bailian_compat=bailian_compat,
        emit_step_events=emit_step_events,
        features=spec.features,
    ):
        yield chunk


async def collect_lab_run_json(
    db: Session,
    spec: LabRunSpec,
    *,
    trace: Optional[LabTraceContext] = None,
) -> Dict[str, Any]:
    t = trace or new_lab_trace_context()
    return await collect_autobi_lab_gateway_json(
        db,
        user_message=spec.content,
        lab_config=spec.lab_config,
        kb_id=spec.knowledge_base_id,
        project_id=spec.project_id,
        project_name=spec.project_name,
        trace_id=t.trace_id,
        trace_started_at=t.started_at,
        features=spec.features,
    )
