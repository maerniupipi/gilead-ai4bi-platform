"""智能体应用仓储"""
from typing import Any, Dict, List, Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from ...models.agent_app import AgentApp, AgentAppVersion
from ...models.agent_app_folder import AgentAppFolder
from ...utils.agent_app_icon import normalize_agent_app_icon


def agent_folder_to_dict(row: AgentAppFolder) -> Dict[str, Any]:
    """将 AgentAppFolder 转为字典"""
    return {
        "id": row.id,
        "name": row.name,
        "sort_order": int(row.sort_order or 0),
        "is_system": bool(row.is_system),
        "created_at": row.created_at,
        "space_id": row.space_id,
    }


def list_agent_app_folders(db: Session, space_id: int = None) -> List[AgentAppFolder]:
    q = db.query(AgentAppFolder)
    if space_id is not None:
        q = q.filter(AgentAppFolder.space_id == space_id)
    return (
        q.order_by(AgentAppFolder.sort_order.asc(), AgentAppFolder.id.asc())
        .all()
    )


def next_agent_folder_sort_order(db: Session) -> int:
    m = db.query(func.max(AgentAppFolder.sort_order)).scalar()
    return int(m or -1) + 1


def get_agent_app_folder(db: Session, folder_id: int, space_id: int = None) -> Optional[AgentAppFolder]:
    q = db.query(AgentAppFolder).filter(AgentAppFolder.id == folder_id)
    if space_id is not None:
        q = q.filter(AgentAppFolder.space_id == space_id)
    return q.first()


def create_agent_app_folder_row(db: Session, name: str, sort_order: int, space_id: int = None) -> AgentAppFolder:
    row = AgentAppFolder(name=name.strip(), sort_order=sort_order, is_system=False, space_id=space_id or 1)
    db.add(row)
    db.flush()
    return row


def delete_agent_app_folder_row(db: Session, row: AgentAppFolder) -> None:
    db.delete(row)


def reassign_agent_apps_folder(db: Session, from_folder_id: int, to_folder_id: int) -> int:
    q = (
        db.query(AgentApp)
        .filter(AgentApp.folder_id == from_folder_id, AgentApp.is_deleted == False)  # noqa: E712
        .all()
    )
    n = 0
    for p in q:
        p.folder_id = to_folder_id
        n += 1
    return n


def list_agent_apps(
    db: Session,
    skip: int,
    limit: int,
    keyword: Optional[str],
    folder_id: Optional[int] = None,
    space_id: int = None,
) -> List[AgentApp]:
    q = (
        db.query(AgentApp)
        .filter(AgentApp.is_deleted == False)  # noqa: E712
        .order_by(AgentApp.updated_at.desc())
    )
    if space_id is not None:
        q = q.filter(AgentApp.space_id == space_id)
    if folder_id is not None:
        q = q.filter(AgentApp.folder_id == folder_id)
    if keyword and keyword.strip():
        kw = f"%{keyword.strip()}%"
        q = q.filter(or_(AgentApp.name.like(kw), AgentApp.description.like(kw)))
    return q.offset(skip).limit(limit).all()


def get_agent_app_by_id(db: Session, app_id: int) -> Optional[AgentApp]:
    return (
        db.query(AgentApp)
        .options(joinedload(AgentApp.versions))
        .filter(AgentApp.id == app_id, AgentApp.is_deleted == False)  # noqa: E712
        .first()
    )


def get_version_for_app(
    db: Session, app_id: int, version_id: int
) -> Optional[AgentAppVersion]:
    return (
        db.query(AgentAppVersion)
        .filter(
            AgentAppVersion.id == version_id,
            AgentAppVersion.agent_app_id == app_id,
        )
        .first()
    )


def get_output_version_for_app(db: Session, app_id: int) -> Optional[AgentAppVersion]:
    """当前应用下 is_output=True 的版本（智能体节点未指定版本时使用）。"""
    return (
        db.query(AgentAppVersion)
        .filter(
            AgentAppVersion.agent_app_id == app_id,
            AgentAppVersion.is_output == True,  # noqa: E712
        )
        .first()
    )


def version_name_exists(db: Session, app_id: int, name: str) -> bool:
    return (
        db.query(AgentAppVersion)
        .filter(
            AgentAppVersion.agent_app_id == app_id,
            AgentAppVersion.name == name,
        )
        .first()
        is not None
    )


def create_agent_app_row(
    db: Session,
    *,
    name: str,
    icon: str,
    description: Optional[str],
    folder_id: int,
    owner_display_name: Optional[str] = None,
    api_token: Optional[str] = None,
    space_id: int = None,
) -> AgentApp:
    row = AgentApp(
        name=name,
        icon=normalize_agent_app_icon(icon),
        description=description,
        folder_id=int(folder_id),
        owner_display_name=owner_display_name,
        api_token=(api_token or "").strip() or None,
        space_id=space_id or 1,
    )
    db.add(row)
    db.flush()
    v = AgentAppVersion(
        agent_app_id=row.id,
        name="v1.0",
        status="designing",
        mode="融合编排",
        is_output=False,
    )
    db.add(v)
    return row


def create_version_row(
    db: Session, app_id: int, name: str
) -> AgentAppVersion:
    v = AgentAppVersion(
        agent_app_id=app_id,
        name=name,
        status="designing",
        mode="融合编排",
        is_output=False,
    )
    db.add(v)
    return v


def clear_output_flags(db: Session, app_id: int) -> None:
    db.query(AgentAppVersion).filter(AgentAppVersion.agent_app_id == app_id).update(
        {AgentAppVersion.is_output: False}, synchronize_session=False
    )


def touch_app_updated_at(db: Session, app_id: int) -> None:
    db.query(AgentApp).filter(AgentApp.id == app_id).update(
        {AgentApp.updated_at: func.current_timestamp()},
        synchronize_session=False,
    )


def update_agent_app_fields(
    db: Session,
    app_id: int,
    fields: Dict[str, Any],
) -> Optional[AgentApp]:
    if not fields:
        return get_agent_app_by_id(db, app_id)
    row = get_agent_app_by_id(db, app_id)
    if row is None:
        return None
    for key, val in fields.items():
        setattr(row, key, val)
    touch_app_updated_at(db, app_id)
    db.flush()
    return row


def soft_delete_agent_app(db: Session, app_id: int) -> bool:
    row = (
        db.query(AgentApp)
        .filter(AgentApp.id == app_id, AgentApp.is_deleted == False)  # noqa: E712
        .first()
    )
    if row is None:
        return False
    row.is_deleted = True
    touch_app_updated_at(db, app_id)
    db.flush()
    return True


def update_version_workflow(
    db: Session,
    app_id: int,
    version_id: int,
    *,
    workflow_json: dict,
    expected_rev: int,
) -> Optional[AgentAppVersion]:
    """
    乐观锁更新工作流。expected_rev 与库中 workflow_rev 不一致时返回 None（冲突）。
    成功时 workflow_rev 自增 1。
    """
    # Check and update in one SQL statement; an ORM instance may cache an old
    # revision while another request commits a newer graph.
    changed = (
        db.query(AgentAppVersion)
        .filter(
            AgentAppVersion.id == version_id,
            AgentAppVersion.agent_app_id == app_id,
            AgentAppVersion.workflow_rev == expected_rev,
        )
        .update(
            {AgentAppVersion.workflow_json: workflow_json,
             AgentAppVersion.workflow_rev: AgentAppVersion.workflow_rev + 1},
            synchronize_session=False,
        )
    )
    if not changed:
        return None
    v = get_version_for_app(db, app_id, version_id)
    db.refresh(v)
    return v

