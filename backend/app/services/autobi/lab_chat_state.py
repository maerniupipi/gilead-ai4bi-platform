"""实验室对话状态：读写字段表 autobi_lab_chat_state。"""

from __future__ import annotations

import json
from typing import Any, Dict

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ...models.autobi_lab_chat_state import AutobiLabChatState
from ...models.autobi_project import AutobiProject
from ...schemas.autobi_lab_chat import AutobiLabChatStateOut, AutobiLabChatStateUpsert


def _project_exists(db: Session, project_id: int) -> bool:
    row = (
        db.query(AutobiProject)
        .filter(AutobiProject.id == project_id, AutobiProject.is_deleted.is_(False))
        .first()
    )
    return row is not None


def get_lab_chat_state(db: Session, project_id: int) -> Dict[str, Any]:
    if not _project_exists(db, project_id):
        raise HTTPException(status_code=404, detail="项目不存在")
    row = db.query(AutobiLabChatState).filter(AutobiLabChatState.project_id == project_id).first()
    if not row or not row.payload_json:
        return AutobiLabChatStateOut().model_dump()
    try:
        data = json.loads(row.payload_json)
    except json.JSONDecodeError:
        return AutobiLabChatStateOut().model_dump()
    if not isinstance(data, dict):
        return AutobiLabChatStateOut().model_dump()
    conv = data.get("conversations")
    if not isinstance(conv, list):
        conv = []
    active = data.get("active_conversation_id")
    if active is not None and not isinstance(active, str):
        active = str(active)
    return AutobiLabChatStateOut(conversations=conv, active_conversation_id=active).model_dump()


def upsert_lab_chat_state(db: Session, project_id: int, body: AutobiLabChatStateUpsert) -> Dict[str, Any]:
    if not _project_exists(db, project_id):
        raise HTTPException(status_code=404, detail="项目不存在")
    payload = body.model_dump()
    text = json.dumps(payload, ensure_ascii=False)
    row = db.query(AutobiLabChatState).filter(AutobiLabChatState.project_id == project_id).first()
    if row:
        row.payload_json = text
    else:
        row = AutobiLabChatState(project_id=project_id, payload_json=text)
        db.add(row)
    db.commit()
    db.refresh(row)
    return {"saved": True, "updated_at": row.updated_at.isoformat() if row.updated_at else None}
