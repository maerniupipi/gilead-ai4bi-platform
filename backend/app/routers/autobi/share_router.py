"""
AutoBI 实验室 · 外链分享（免登录）

仅凭 `autobi_projects.share_token` 访问；包含实验室对话所需的读写操作。
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ...core.database import SessionLocal, get_db
from ...schemas.autobi_lab_chat import AutobiLabChatStateUpsert
from ...schemas.autobi_gateway import LabGatewayV2Request, _effective_features
from ...services.autobi.service import get_project_by_share_token
from ...services.autobi.lab_config_merge import merge_lab_config
from ...services.autobi.lab_features import apply_features_to_lab_config_prompts
from ...services.autobi.lab_pipeline_runner import run_autobi_lab_gateway_sse
from ...services.autobi.lab_chat_state import get_lab_chat_state, upsert_lab_chat_state
from ...services.autobi.lab_trace import get_lab_trace

router = APIRouter()


def _project_from_token(db: Session, token: str) -> Dict[str, Any]:
    """通过分享 token 获取项目，无效则 404。"""
    m = get_project_by_share_token(db, token)
    if not m:
        raise HTTPException(status_code=404, detail="分享链接无效或已失效")
    return m


# ---------------------------------------------------------------------------
# 项目信息
# ---------------------------------------------------------------------------

@router.get("/{token}/project")
def share_get_project(token: str, db: Session = Depends(get_db)):
    """获取项目详情（不含 config_json 中的敏感信息）。"""
    project = _project_from_token(db, token)
    return {
        "id": project["id"],
        "api_access_id": project["api_access_id"],
        "name": project["name"],
        "description": project["description"],
    }


# ---------------------------------------------------------------------------
# 对话状态
# ---------------------------------------------------------------------------

@router.get("/{token}/chat-state")
def share_get_chat_state(token: str, db: Session = Depends(get_db)):
    """获取实验室对话状态。"""
    project = _project_from_token(db, token)
    return get_lab_chat_state(db, project["id"])


@router.put("/{token}/chat-state")
def share_save_chat_state(
    token: str,
    body: AutobiLabChatStateUpsert,
    db: Session = Depends(get_db),
):
    """覆盖保存实验室对话状态。"""
    project = _project_from_token(db, token)
    return upsert_lab_chat_state(db, project["id"], body)


# ---------------------------------------------------------------------------
# SSE 网关
# ---------------------------------------------------------------------------

@router.post("/{token}/gateway")
async def share_lab_gateway(token: str, body: LabGatewayV2Request):
    """
    分享页 SSE 网关：复用与实验室相同的 18 步流水线。
    响应为 SSE：推送 trace_id、数据总结增量（delta），以及 done / error。
    """

    async def event_stream():
        db = SessionLocal()
        try:
            project = get_project_by_share_token(db, token)
            if not project:
                yield (
                    "data: "
                    + json.dumps({"type": "error", "message": "分享链接无效或已失效"}, ensure_ascii=False)
                    + "\n\n"
                )
                yield "data: " + json.dumps({"type": "done"}, ensure_ascii=False) + "\n\n"
                return

            feat = _effective_features(body)
            merged = merge_lab_config(project["config_json"])
            merged = apply_features_to_lab_config_prompts(merged, feat)
            kb_id = project["knowledge_base_id"] or merged.get("knowledge_base_id")
            if kb_id is None:
                yield (
                    "data: "
                    + json.dumps({"type": "error", "message": "项目未配置知识库"}, ensure_ascii=False)
                    + "\n\n"
                )
                yield "data: " + json.dumps({"type": "done"}, ensure_ascii=False) + "\n\n"
                return
            kb_id = int(kb_id)
            trace_id = str(uuid.uuid4())
            started = int(time.time() * 1000)
            async for chunk in run_autobi_lab_gateway_sse(
                db,
                user_message=body.content.strip(),
                lab_config=merged,
                kb_id=kb_id,
                project_id=int(project["id"]),
                project_name=project.get("name"),
                trace_id=trace_id,
                trace_started_at=started,
                features=feat,
            ):
                yield chunk
        finally:
            db.close()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# 追踪（Redis）
# ---------------------------------------------------------------------------

@router.get("/{token}/traces/{trace_id}")
def share_get_trace(token: str, trace_id: str, db: Session = Depends(get_db)):
    """获取流水线追踪详情（Redis）。"""
    _project_from_token(db, token)
    return get_lab_trace(trace_id)
