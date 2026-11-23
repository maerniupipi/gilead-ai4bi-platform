"""智能体应用业务"""
import asyncio
import logging
import time
import uuid
from copy import deepcopy
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ...models.agent_app import AgentApp
from ...models.agent_app_folder import AgentAppFolder
from ...core.redis_client import agent_run_trace_set, workflow_undo_get, workflow_undo_set
from ...utils.agent_app_icon import normalize_agent_app_icon
from ...repositories.agent_app.repository import (
    agent_folder_to_dict,
    clear_output_flags,
    create_agent_app_folder_row,
    create_agent_app_row,
    create_version_row,
    delete_agent_app_folder_row,
    get_agent_app_by_id,
    get_agent_app_folder,
    get_version_for_app,
    list_agent_app_folders,
    list_agent_apps,
    next_agent_folder_sort_order,
    reassign_agent_apps_folder,
    soft_delete_agent_app,
    touch_app_updated_at,
    update_agent_app_fields,
    update_version_workflow,
    version_name_exists,
)
from ...schemas.agent_app import (
    AgentAppCreate,
    AgentAppDetail,
    AgentAppSummary,
    AgentAppUpdate,
    AgentAppVersionOut,
    AgentVersionCreate,
    SetOutputVersionBody,
    WorkflowGetOut,
    WorkflowPutBody,
    WorkflowRunBody,
    WorkflowRunOut,
    WorkflowUndoStack,
)
from ...services.common import ensure_default_folder

logger = logging.getLogger(__name__)


# 兼容别名，保持向后兼容
def ensure_default_agent_folder(db: Session, space_id: int = None) -> int:
    """保证至少存在一个系统默认文件夹。"""
    return ensure_default_folder(db, AgentAppFolder, space_id)


def list_agent_app_folders_service(db: Session, space_id: int = None) -> List[Dict[str, Any]]:
    ensure_default_agent_folder(db, space_id)
    rows = list_agent_app_folders(db, space_id)
    return [agent_folder_to_dict(r) for r in rows]


def create_agent_app_folder_service(db: Session, name: str, space_id: int = None) -> Dict[str, Any]:
    ensure_default_agent_folder(db, space_id)
    nm = (name or "").strip()
    if not nm:
        raise HTTPException(status_code=400, detail="文件夹名称不能为空")
    nxt = next_agent_folder_sort_order(db)
    row = create_agent_app_folder_row(db, nm, nxt, space_id)
    db.commit()
    db.refresh(row)
    return agent_folder_to_dict(row)


def update_agent_app_folder_service(db: Session, folder_id: int, name: str, space_id: int = None) -> Dict[str, Any]:
    ensure_default_agent_folder(db, space_id)
    row = get_agent_app_folder(db, folder_id, space_id)
    if row is None:
        raise HTTPException(status_code=404, detail="文件夹不存在")
    nm = (name or "").strip()
    if not nm:
        raise HTTPException(status_code=400, detail="文件夹名称不能为空")
    row.name = nm
    db.commit()
    db.refresh(row)
    return agent_folder_to_dict(row)


def delete_agent_app_folder_service(db: Session, folder_id: int, space_id: int = None) -> Dict[str, Any]:
    ensure_default_agent_folder(db, space_id)
    row = get_agent_app_folder(db, folder_id, space_id)
    if row is None:
        raise HTTPException(status_code=404, detail="文件夹不存在")
    if bool(row.is_system):
        raise HTTPException(status_code=400, detail="系统默认文件夹不可删除")
    default_query = db.query(AgentAppFolder).filter(AgentAppFolder.is_system.is_(True))
    if space_id is not None:
        default_query = default_query.filter(AgentAppFolder.space_id == space_id)
    default_row = default_query.order_by(AgentAppFolder.id.asc()).first()
    if default_row is None:
        raise HTTPException(status_code=500, detail="未找到系统默认文件夹")
    default_id = int(default_row.id)
    if default_id == int(folder_id):
        raise HTTPException(status_code=400, detail="系统默认文件夹不可删除")
    reassign_agent_apps_folder(db, int(folder_id), default_id)
    delete_agent_app_folder_row(db, row)
    db.commit()
    return {"ok": True}


def move_agent_app_folder_service(db: Session, folder_id: int, direction: str, space_id: int = None) -> List[Dict[str, Any]]:
    ensure_default_agent_folder(db, space_id)
    rows = list(list_agent_app_folders(db, space_id))
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
    return [agent_folder_to_dict(r) for r in rows]


def list_agent_apps_service(
    db: Session, skip: int, limit: int, keyword: Optional[str], folder_id: Optional[int] = None, space_id: int = None
) -> List[AgentApp]:
    return list_agent_apps(db, skip, limit, keyword, folder_id=folder_id, space_id=space_id)


def get_agent_app_service(db: Session, app_id: int) -> AgentApp:
    row = get_agent_app_by_id(db, app_id)
    if row is None:
        raise HTTPException(status_code=404, detail="应用不存在")
    return row


def create_agent_app_service(db: Session, body: AgentAppCreate, space_id: int = None) -> AgentApp:
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="应用名称不能为空")
    desc = (body.description or "").strip() or None
    icon = normalize_agent_app_icon(body.icon)
    default_fid = ensure_default_agent_folder(db, space_id)
    fid = int(body.folder_id) if body.folder_id is not None else default_fid
    if get_agent_app_folder(db, fid, space_id) is None:
        raise HTTPException(status_code=400, detail="文件夹不存在")
    owner = (body.owner_display_name or "").strip() or None
    api_token = (body.api_token or "").strip() or None
    row = create_agent_app_row(
        db,
        name=name,
        icon=icon,
        description=desc,
        folder_id=fid,
        owner_display_name=owner,
        api_token=api_token,
        space_id=space_id,
    )
    db.commit()
    db.refresh(row)
    return get_agent_app_by_id(db, row.id)


def update_agent_app_service(db: Session, app_id: int, body: AgentAppUpdate, space_id: int = None) -> AgentApp:
    payload = body.model_dump(exclude_unset=True)
    if not payload:
        raise HTTPException(status_code=400, detail="无更新字段")
    fields: Dict[str, Any] = {}
    if "name" in payload:
        name = (payload["name"] or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="应用名称不能为空")
        fields["name"] = name
    if "icon" in payload:
        fields["icon"] = normalize_agent_app_icon(payload.get("icon"))
    if "description" in payload:
        fields["description"] = (payload["description"] or "").strip() or None
    if "api_token" in payload:
        token = (payload.get("api_token") or "").strip()
        if token:
            fields["api_token"] = token
    if "folder_id" in payload:
        fid = int(payload["folder_id"])
        if get_agent_app_folder(db, fid, space_id) is None:
            raise HTTPException(status_code=400, detail="文件夹不存在")
        fields["folder_id"] = fid
    get_agent_app_service(db, app_id)
    row = update_agent_app_fields(db, app_id, fields)
    if row is None:
        raise HTTPException(status_code=404, detail="应用不存在")
    db.commit()
    return _reload_app(db, app_id)


def delete_agent_app_service(db: Session, app_id: int) -> None:
    get_agent_app_service(db, app_id)
    if not soft_delete_agent_app(db, app_id):
        raise HTTPException(status_code=404, detail="应用不存在")
    db.commit()


def to_detail(row: AgentApp) -> AgentAppDetail:
    # 列表按创建时间倒序（新在前）
    vers = sorted(
        row.versions,
        key=lambda x: (x.created_at or datetime.min, x.id),
        reverse=True,
    )
    return AgentAppDetail(
        id=row.id,
        folder_id=int(row.folder_id),
        name=row.name,
        icon=row.icon,
        description=row.description,
        owner_display_name=getattr(row, "owner_display_name", None),
        api_token_configured=bool(getattr(row, "api_token", None)),
        created_at=row.created_at,
        updated_at=row.updated_at,
        versions=[AgentAppVersionOut.model_validate(v) for v in vers],
    )


def to_summary(row: AgentApp) -> AgentAppSummary:
    return AgentAppSummary(
        id=row.id,
        folder_id=int(row.folder_id),
        name=row.name,
        icon=row.icon,
        description=row.description,
        owner_display_name=getattr(row, "owner_display_name", None),
        api_token_configured=bool(getattr(row, "api_token", None)),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _reload_app(db: Session, app_id: int) -> AgentApp:
    return get_agent_app_service(db, app_id)


def create_version_service(db: Session, app_id: int, body: AgentVersionCreate) -> AgentApp:
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="版本名称不能为空")
    get_agent_app_service(db, app_id)
    if version_name_exists(db, app_id, name):
        raise HTTPException(status_code=400, detail="该版本名称已存在")
    clone_from = body.clone_from_version_id
    if clone_from is not None and body.workflow is not None:
        raise HTTPException(status_code=400, detail="不能同时导入画布和克隆版本")
    workflow_json = body.workflow.model_dump() if body.workflow is not None else None
    if clone_from is not None:
        src = get_version_for_app(db, app_id, int(clone_from))
        if src is None:
            raise HTTPException(status_code=404, detail="源版本不存在，无法克隆")
        workflow_json = deepcopy(src.workflow_json) if src.workflow_json is not None else None
    new_v = create_version_row(db, app_id, name)
    new_v.workflow_json = workflow_json
    new_v.workflow_rev = 0
    if body.workflow is not None:
        new_v.mode = "导入"
    touch_app_updated_at(db, app_id)
    db.commit()
    if body.workflow is not None and body.undo_stack is not None:
        try:
            workflow_undo_set(app_id, new_v.id, _normalize_undo_for_redis(body.undo_stack))
        except Exception:
            # The version and graph are already committed; a cache failure must
            # not report a failed import and encourage duplicate creation.
            logger.warning("导入版本已保存，撤销历史缓存写入失败 app_id=%s version_id=%s", app_id, new_v.id, exc_info=True)
    return _reload_app(db, app_id)


def publish_version_service(db: Session, app_id: int, version_id: int) -> AgentApp:
    v = get_version_for_app(db, app_id, version_id)
    if v is None:
        raise HTTPException(status_code=404, detail="版本不存在")
    if v.status != "designing":
        raise HTTPException(status_code=400, detail="仅「设计中」的版本可发布")
    v.status = "published"
    touch_app_updated_at(db, app_id)
    db.commit()
    return _reload_app(db, app_id)


def go_online_version_service(db: Session, app_id: int, version_id: int) -> AgentApp:
    """已发布 → 已上线；允许同一应用下多个版本同时处于已上线。"""
    v = get_version_for_app(db, app_id, version_id)
    if v is None:
        raise HTTPException(status_code=404, detail="版本不存在")
    if v.status != "published":
        raise HTTPException(status_code=400, detail="仅「已发布」的版本可上线")
    v.status = "online"
    touch_app_updated_at(db, app_id)
    db.commit()
    db.refresh(v)
    return _reload_app(db, app_id)


def go_offline_version_service(db: Session, app_id: int, version_id: int) -> AgentApp:
    v = get_version_for_app(db, app_id, version_id)
    if v is None:
        raise HTTPException(status_code=404, detail="版本不存在")
    if v.status != "online":
        raise HTTPException(status_code=400, detail="仅「已上线」的版本可下线")
    v.status = "published"
    touch_app_updated_at(db, app_id)
    db.commit()
    return _reload_app(db, app_id)


def delete_version_service(db: Session, app_id: int, version_id: int) -> AgentApp:
    """仅「设计中」「已发布」可删除；已上线、当前输出版本不可删。"""
    v = get_version_for_app(db, app_id, version_id)
    if v is None:
        raise HTTPException(status_code=404, detail="版本不存在")
    if getattr(v, "is_output", False):
        raise HTTPException(status_code=400, detail="输出版本不可删除，请先在「输出版本配置」中更换其它版本")
    if v.status == "online":
        raise HTTPException(status_code=400, detail="已上线版本不可删除，请先下线")
    if v.status not in ("designing", "published"):
        raise HTTPException(status_code=400, detail="当前状态不可删除")
    db.delete(v)
    touch_app_updated_at(db, app_id)
    db.commit()
    return _reload_app(db, app_id)


def _normalize_undo_for_redis(body: WorkflowUndoStack) -> dict:
    """截断为最近 10 步并校正 index。"""
    states = body.states or []
    if len(states) > 10:
        drop = len(states) - 10
        states = states[-10:]
        idx = max(0, body.index - drop)
    else:
        idx = body.index
    if not states:
        return {"states": [], "index": 0}
    if idx >= len(states):
        idx = len(states) - 1
    if idx < 0:
        idx = 0
    return {"states": states, "index": idx}


def get_workflow_version_service(db: Session, app_id: int, version_id: int) -> WorkflowGetOut:
    get_agent_app_service(db, app_id)
    v = get_version_for_app(db, app_id, version_id)
    if v is None:
        raise HTTPException(status_code=404, detail="版本不存在")
    rev = int(getattr(v, "workflow_rev", 0) or 0)
    raw = getattr(v, "workflow_json", None)
    workflow = raw if isinstance(raw, dict) else None
    undo_raw = workflow_undo_get(app_id, version_id)
    undo_stack: Optional[WorkflowUndoStack] = None
    if undo_raw and isinstance(undo_raw, dict) and "states" in undo_raw:
        try:
            undo_stack = WorkflowUndoStack.model_validate(undo_raw)
        except Exception:
            undo_stack = None
    return WorkflowGetOut(workflow=workflow, workflow_rev=rev, undo_stack=undo_stack)


def put_workflow_version_service(
    db: Session, app_id: int, version_id: int, body: WorkflowPutBody
) -> WorkflowGetOut:
    get_agent_app_service(db, app_id)
    v0 = get_version_for_app(db, app_id, version_id)
    if v0 is None:
        raise HTTPException(status_code=404, detail="版本不存在")
    workflow_json = {"nodes": body.nodes, "edges": body.edges}
    updated = update_version_workflow(
        db,
        app_id,
        version_id,
        workflow_json=workflow_json,
        expected_rev=body.expected_rev,
    )
    if updated is None:
        # Restart the read transaction as well as expiring the ORM cache, so
        # MySQL's repeatable-read isolation sees the request that won the race.
        db.rollback()
        db.refresh(v0)
        if v0.workflow_json == workflow_json:
            return get_workflow_version_service(db, app_id, version_id)
        raise HTTPException(status_code=409, detail="画布版本已过期，请刷新后重试")
    # Return this write's revision, even if a newer write commits immediately
    # after ours. Returning somebody else's revision could let a client overwrite
    # that newer graph on its next save without going through conflict recovery.
    rev = int(getattr(updated, "workflow_rev", 0) or 0)
    wf = deepcopy(getattr(updated, "workflow_json", None))
    workflow_out = wf if isinstance(wf, dict) else workflow_json
    touch_app_updated_at(db, app_id)
    db.commit()
    if body.undo_stack is not None:
        payload = _normalize_undo_for_redis(body.undo_stack)
        workflow_undo_set(app_id, version_id, payload)
    undo_raw = workflow_undo_get(app_id, version_id)
    undo_stack: Optional[WorkflowUndoStack] = None
    if undo_raw and isinstance(undo_raw, dict):
        try:
            undo_stack = WorkflowUndoStack.model_validate(undo_raw)
        except Exception:
            undo_stack = None
    return WorkflowGetOut(workflow=workflow_out, workflow_rev=rev, undo_stack=undo_stack)


async def run_workflow_version_service(
    db: Session, app_id: int, version_id: int, body: WorkflowRunBody
) -> WorkflowRunOut:
    from ...core.execution import read_database, TRACE_WORK
    await read_database(db, get_agent_app_service, app_id)
    v = await read_database(db, get_version_for_app, app_id, version_id)
    if v is None:
        raise HTTPException(status_code=404, detail="版本不存在")
    from .workflow_engine import assert_runnable_workflow, execute_agent_workflow_background

    try:
        assert_runnable_workflow(v)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    run_id = str(uuid.uuid4())

    # resolve app name for initial trace
    app_name = None
    try:
        from ...models.agent_app import AgentApp
        app_row = await read_database(db, lambda session: session.query(AgentApp).filter(AgentApp.id == app_id).first())
        if app_row:
            app_name = app_row.name
    except Exception:
        pass

    await TRACE_WORK.run(agent_run_trace_set,
        run_id,
        {
            "run_id": run_id,
            "trace_id": run_id,
            "app_id": app_id,
            "version_id": version_id,
            "app_name": app_name,
            "status": "running",
            "steps": [],
            "nodes": None,
            "edges": None,
            "output": None,
            "error": None,
            "elapsed_ms": 0,
            "parent_trace_id": None,
            "created_at": int(time.time() * 1000),
        },
    )
    asyncio.create_task(
        execute_agent_workflow_background(
            agent_app_id=app_id,
            version_id=version_id,
            inputs=dict(body.inputs or {}),
            run_id=run_id,
        )
    )
    return WorkflowRunOut(
        run_id=run_id,
        trace_id=run_id,
        status="running",
        output=None,
        error=None,
        elapsed_ms=0,
    )


def get_agent_run_trace_service(db: Session, app_id: int, run_id: str) -> Dict[str, Any]:
    get_agent_app_service(db, app_id)
    from .workflow_engine import get_agent_run_trace

    payload = get_agent_run_trace(run_id)
    if not payload:
        raise HTTPException(status_code=404, detail="执行记录不存在或已过期")
    if int(payload.get("app_id", -1)) != app_id:
        raise HTTPException(status_code=404, detail="执行记录不存在或已过期")
    return payload


def set_output_version_service(
    db: Session, app_id: int, body: SetOutputVersionBody
) -> AgentApp:
    """
    全局仅一条 is_output=True。选定后该版本自动变为「已上线」。
    后续若开放「上线版本号」API：未显式指定时可默认采用当前输出版本的版本号（name）。
    """
    get_agent_app_service(db, app_id)
    v = get_version_for_app(db, app_id, body.version_id)
    if v is None:
        raise HTTPException(status_code=404, detail="版本不存在")
    if v.status not in ("published", "online"):
        raise HTTPException(status_code=400, detail="仅「已发布」或「已上线」的版本可作为输出")
    clear_output_flags(db, app_id)
    v = get_version_for_app(db, app_id, body.version_id)
    if v is None:
        raise HTTPException(status_code=404, detail="版本不存在")
    v.is_output = True
    v.status = "online"
    touch_app_updated_at(db, app_id)
    db.commit()
    return _reload_app(db, app_id)


def get_agent_version_params_service(db: Session, app_id: int, version_id: int) -> Dict[str, Any]:
    from ...repositories.agent_app.repository import get_version_for_app

    v = get_version_for_app(db, app_id, version_id)
    if v is None:
        raise HTTPException(status_code=404, detail="版本不存在")

    wf = v.workflow_json or {}
    nodes = wf.get("nodes") or []

    input_params = []
    output_params = []

    for node in nodes:
        data = node.get("data") or {}
        if data.get("kind") == "userInput":
            for f in data.get("fields") or []:
                input_params.append(
                    {
                        "name": f.get("variable") or "",
                        "type": f.get("type", "STRING"),
                        "required": f.get("required", False),
                        "description": f.get("description") or "",
                        "default_value": f.get("default"),
                        "source_type": None,
                        "constant_value": f.get("default"),
                    }
                )
        elif data.get("kind") == "output":
            if output_params:
                continue
            output_params.append(
                {
                    "name": "content",
                    "type": "STRING",
                    "description": "输出内容",
                }
            )
            output_params.append(
                {
                    "name": "metadata",
                    "type": "OBJECT",
                    "description": "扩展字段",
                }
            )

    return {"input_params": input_params, "output_params": output_params}
