import json
import os
import secrets
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ...models.autobi_folder import AutobiFolder
from ...models.autobi_project import AutobiProject
from ...repositories.autobi import repository as repo
from ...repositories.knowledge.knowledge_base.repository import get_knowledge_base_active
from ...schemas.autobi import AutobiProjectCreate, AutobiProjectUpdate, AutobiShareIssueOut
from ...services.common import ensure_default_folder
from .default_prompts import build_default_advanced_config
from .lab_config_merge import expand_legacy_config
from .api_access_id import ensure_row_has_api_access_id, allocate_unique_api_access_id


def _default_config_dict() -> Dict[str, Any]:
    return {
        "knowledge_base_id": None,
        "model_bindings": {},
        "request": {
            "messages": [{"role": "user", "content": ""}],
            "stream": False,
            "advanced_config": {},
        },
    }


def _new_project_config_dict() -> Dict[str, Any]:
    """新建项目：写入《默认提示词》中的四类 prompt 及对齐 OpenTrek 的 advanced_config 默认值。"""
    cfg = _default_config_dict()
    cfg["request"]["advanced_config"] = build_default_advanced_config()
    return cfg


def _dump_config(data: Dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False)


def _load_config(raw: Optional[str]) -> Dict[str, Any]:
    if not raw:
        return _default_config_dict()
    try:
        decoded = json.loads(raw)
        return expand_legacy_config(decoded) if isinstance(decoded, dict) else _default_config_dict()
    except (json.JSONDecodeError, TypeError):
        return _default_config_dict()


def _validate_kb(db: Session, kb_id: Optional[int], space_id: int = None) -> None:
    if kb_id is None:
        return
    if get_knowledge_base_active(db, kb_id, space_id) is None:
        raise HTTPException(status_code=404, detail="Knowledge base not found")


# 兼容别名，保持向后兼容
def ensure_default_autobi_folder(db: Session, space_id: int = None) -> int:
    """保证至少存在一个系统默认文件夹。"""
    return ensure_default_folder(db, AutobiFolder, space_id)


def list_autobi_folders_service(db: Session, space_id: int = None) -> List[Dict[str, Any]]:
    ensure_default_autobi_folder(db, space_id)
    rows = repo.list_autobi_folders(db, space_id)
    return [repo.autobi_folder_to_dict(r) for r in rows]


def create_autobi_folder_service(db: Session, name: str, space_id: int = None) -> Dict[str, Any]:
    ensure_default_autobi_folder(db, space_id)
    nm = (name or "").strip()
    if not nm:
        raise HTTPException(status_code=400, detail="文件夹名称不能为空")
    nxt = repo.next_folder_sort_order(db)
    row = repo.create_autobi_folder(db, nm, nxt, space_id)
    db.commit()
    db.refresh(row)
    return repo.autobi_folder_to_dict(row)


def update_autobi_folder_service(db: Session, folder_id: int, name: str, space_id: int = None) -> Dict[str, Any]:
    ensure_default_autobi_folder(db, space_id)
    row = repo.get_autobi_folder(db, folder_id, space_id)
    if row is None:
        raise HTTPException(status_code=404, detail="文件夹不存在")
    nm = (name or "").strip()
    if not nm:
        raise HTTPException(status_code=400, detail="文件夹名称不能为空")
    row.name = nm
    db.commit()
    db.refresh(row)
    return repo.autobi_folder_to_dict(row)


def delete_autobi_folder_service(db: Session, folder_id: int, space_id: int = None) -> Dict[str, Any]:
    ensure_default_autobi_folder(db, space_id)
    row = repo.get_autobi_folder(db, folder_id, space_id)
    if row is None:
        raise HTTPException(status_code=404, detail="文件夹不存在")
    if bool(row.is_system):
        raise HTTPException(status_code=400, detail="系统默认文件夹不可删除")
    default_query = db.query(AutobiFolder).filter(AutobiFolder.is_system.is_(True))
    if space_id is not None:
        default_query = default_query.filter(AutobiFolder.space_id == space_id)
    default_row = default_query.order_by(AutobiFolder.id.asc()).first()
    if default_row is None:
        raise HTTPException(status_code=500, detail="未找到系统默认文件夹")
    default_id = int(default_row.id)
    if default_id == int(folder_id):
        raise HTTPException(status_code=400, detail="系统默认文件夹不可删除")
    repo.reassign_folder_for_projects(db, int(folder_id), default_id)
    repo.delete_autobi_folder_row(db, row)
    db.commit()
    return {"ok": True}


def move_autobi_folder_service(db: Session, folder_id: int, direction: str, space_id: int = None) -> List[Dict[str, Any]]:
    ensure_default_autobi_folder(db, space_id)
    rows = list(repo.list_autobi_folders(db, space_id))
    ids = [int(r.id) for r in rows]
    try:
        i = ids.index(int(folder_id))
    except ValueError:
        raise HTTPException(status_code=404, detail="文件夹不存在")
    if direction == "up":
        if i == 0:
            raise HTTPException(status_code=400, detail="已在最上方")
        rows[i], rows[i - 1] = rows[i - 1], rows[i]
    elif direction == "down":
        if i == len(rows) - 1:
            raise HTTPException(status_code=400, detail="已在最下方")
        rows[i], rows[i + 1] = rows[i + 1], rows[i]
    else:
        raise HTTPException(status_code=400, detail="direction 须为 up 或 down")
    for idx, r in enumerate(rows):
        r.sort_order = idx
    db.commit()
    for r in rows:
        db.refresh(r)
    return [repo.autobi_folder_to_dict(r) for r in rows]


def list_autobi_projects_service(
    db: Session, skip: int = 0, limit: int = 200, folder_id: Optional[int] = None, space_id: int = None
):
    rows = repo.list_autobi_projects_active(db, skip, limit, folder_id=folder_id, space_id=space_id)
    changed = False
    for row in rows:
        if ensure_row_has_api_access_id(db, row):
            changed = True
    if changed:
        db.commit()
        for row in rows:
            db.refresh(row)
    return rows


def get_autobi_project_service(db: Session, project_id: int, space_id: int = None) -> Dict[str, Any]:
    row = repo.get_autobi_project_active(db, project_id, space_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Autobi project not found")
    if ensure_row_has_api_access_id(db, row):
        db.commit()
        db.refresh(row)
    cfg = _load_config(row.config_json)
    return {
        "id": row.id,
        "api_access_id": row.api_access_id,
        "name": row.name,
        "description": row.description,
        "knowledge_base_id": row.knowledge_base_id,
        "folder_id": int(row.folder_id),
        "config_json": cfg,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def get_autobi_project_by_api_access_id_service(db: Session, api_access_id: str, space_id: int = None) -> Dict[str, Any]:
    aid = (api_access_id or "").strip()
    if not aid:
        raise HTTPException(status_code=400, detail="缺少 API ID")
    row = repo.get_autobi_project_by_api_access_id(db, aid, space_id)
    if row is None:
        raise HTTPException(status_code=404, detail="API ID 无效或未找到项目")
    if ensure_row_has_api_access_id(db, row):
        db.commit()
        db.refresh(row)
    cfg = _load_config(row.config_json)
    return {
        "id": row.id,
        "api_access_id": row.api_access_id,
        "name": row.name,
        "description": row.description,
        "knowledge_base_id": row.knowledge_base_id,
        "folder_id": int(row.folder_id),
        "config_json": cfg,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def create_autobi_project_service(db: Session, body: AutobiProjectCreate, space_id: int = None):
    default_fid = ensure_default_autobi_folder(db, space_id)
    fid = int(body.folder_id) if body.folder_id is not None else default_fid
    if repo.get_autobi_folder(db, fid, space_id) is None:
        raise HTTPException(status_code=404, detail="文件夹不存在")
    default_cfg = _new_project_config_dict()
    cfg_str = _dump_config(default_cfg)
    api_id = allocate_unique_api_access_id(db)
    row = repo.create_autobi_project(db, body.name, body.description, cfg_str, None, api_id, fid, space_id)
    db.commit()
    db.refresh(row)
    return get_autobi_project_service(db, row.id, space_id)


def update_autobi_project_service(db: Session, project_id: int, body: AutobiProjectUpdate, space_id: int = None):
    row = repo.get_autobi_project_active(db, project_id, space_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Autobi project not found")

    if body.name is not None:
        row.name = body.name
    if body.description is not None:
        row.description = body.description
    if body.folder_id is not None:
        if repo.get_autobi_folder(db, int(body.folder_id), space_id) is None:
            raise HTTPException(status_code=404, detail="文件夹不存在")
        row.folder_id = int(body.folder_id)

    if body.config_json is not None:
        kb_id = body.config_json.get("knowledge_base_id")
        _validate_kb(db, kb_id, space_id)
        row.knowledge_base_id = kb_id
        row.config_json = _dump_config(body.config_json)

    db.commit()
    db.refresh(row)
    return get_autobi_project_service(db, row.id, space_id)


def delete_autobi_project_service(db: Session, project_id: int, space_id: int = None):
    row = repo.get_autobi_project_active(db, project_id, space_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Autobi project not found")
    repo.soft_delete_autobi_project(db, row)
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# 外链分享
# ---------------------------------------------------------------------------

def get_project_by_share_token(db: Session, token: str):
    """通过 share_token 获取项目（免登录）。"""
    t = (token or "").strip()
    if not t:
        return None
    row = (
        db.query(AutobiProject)
        .filter(AutobiProject.share_token == t, AutobiProject.is_deleted == False)
        .first()
    )
    if row is None:
        return None
    cfg = _load_config(row.config_json)
    return {
        "id": row.id,
        "api_access_id": row.api_access_id,
        "name": row.name,
        "description": row.description,
        "knowledge_base_id": row.knowledge_base_id,
        "folder_id": int(row.folder_id),
        "config_json": cfg,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def issue_share_token_service(
    db: Session,
    project_id: int,
    *,
    rotate: bool = False,
    space_id: int = None,
) -> AutobiShareIssueOut:
    """为项目生成或复用 share_token（opaque），用于免登录外链。"""
    row = repo.get_autobi_project_active(db, project_id, space_id)
    if row is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    if rotate or not row.share_token:
        row.share_token = secrets.token_urlsafe(32)
        db.commit()
        db.refresh(row)
    token = (row.share_token or "").strip()
    if not token:
        row.share_token = secrets.token_urlsafe(32)
        db.commit()
        db.refresh(row)
        token = row.share_token or ""
    base = (os.getenv("AUTOBI_LAB_SHARE_PUBLIC_BASE_URL") or "").strip() or None
    return AutobiShareIssueOut(token=token, share_public_base_url=base)


def revoke_share_token_service(db: Session, project_id: int, space_id: int = None) -> None:
    """撤销项目的分享 token。"""
    row = repo.get_autobi_project_active(db, project_id, space_id)
    if row is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    row.share_token = None
    db.commit()
