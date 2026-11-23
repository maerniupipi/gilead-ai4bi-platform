from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ...core.database import SessionLocal, get_db
from ...core.execution import read_database
from ...core.permissions import RequireSystemPermission
from ...schemas.autobi import (
    AutobiFolderCreate,
    AutobiFolderItem,
    AutobiFolderMoveBody,
    AutobiFolderUpdate,
    AutobiProjectCreate,
    AutobiProjectImport,
    AutobiProjectListItem,
    AutobiProjectUpdate,
)
from ...schemas.autobi_gateway import LabGatewayV2Request
from ...schemas.autobi_lab_chat import AutobiLabChatStateUpsert
from ...schemas.autobi_lab_trace import AutobiLabTraceUpsert
from ...services.autobi import (
    list_autobi_projects_service,
    get_autobi_project_service,
    create_autobi_project_service,
    update_autobi_project_service,
    delete_autobi_project_service,
    list_autobi_folders_service,
    create_autobi_folder_service,
    update_autobi_folder_service,
    delete_autobi_folder_service,
    move_autobi_folder_service,
    issue_share_token_service,
    revoke_share_token_service,
)
from ...services.autobi.lab_bailian_gateway import stream_lab_bailian_sse
from ...services.autobi.project_transfer import export_autobi_project_service, import_autobi_project_service
from ...services.autobi.lab_runtime import (
    build_lab_run_spec_from_api_request,
    new_lab_trace_context,
    stream_lab_native_sse,
)
from ...services.autobi.lab_chat_state import get_lab_chat_state, upsert_lab_chat_state
from ...services.autobi.lab_trace import get_lab_trace, upsert_lab_trace

router = APIRouter(prefix="/api/autobi", tags=["autobi"])


def get_space_id(space_id: Optional[int] = Query(None, description="空间ID")) -> Optional[int]:
    return space_id


@router.get("/folders", response_model=List[AutobiFolderItem])
def list_folders(
    db: Session = Depends(get_db),
    space_id: Optional[int] = Depends(get_space_id)
):
    rows = list_autobi_folders_service(db, space_id)
    return [AutobiFolderItem(**r) for r in rows]


@router.post("/folders", response_model=AutobiFolderItem)
def create_folder(
    body: AutobiFolderCreate,
    db: Session = Depends(get_db),
    space_id: Optional[int] = Depends(get_space_id),
    operator_id: int = Depends(RequireSystemPermission("*")),
):
    r = create_autobi_folder_service(db, body.name, space_id)
    return AutobiFolderItem(**r)


@router.put("/folders/{folder_id}", response_model=AutobiFolderItem)
def update_folder(
    folder_id: int,
    body: AutobiFolderUpdate,
    db: Session = Depends(get_db),
    space_id: Optional[int] = Depends(get_space_id),
    operator_id: int = Depends(RequireSystemPermission("*")),
):
    r = update_autobi_folder_service(db, folder_id, body.name, space_id)
    return AutobiFolderItem(**r)


@router.delete("/folders/{folder_id}")
def delete_folder(
    folder_id: int,
    db: Session = Depends(get_db),
    space_id: Optional[int] = Depends(get_space_id),
    operator_id: int = Depends(RequireSystemPermission("*")),
):
    return delete_autobi_folder_service(db, folder_id, space_id)


@router.post("/folders/{folder_id}/move", response_model=List[AutobiFolderItem])
def move_folder(
    folder_id: int,
    body: AutobiFolderMoveBody,
    db: Session = Depends(get_db),
    space_id: Optional[int] = Depends(get_space_id),
    operator_id: int = Depends(RequireSystemPermission("*")),
):
    rows = move_autobi_folder_service(db, folder_id, body.direction, space_id)
    return [AutobiFolderItem(**r) for r in rows]


@router.get("/projects", response_model=List[AutobiProjectListItem])
def list_projects(
    skip: int = 0,
    limit: int = 200,
    folder_id: Optional[int] = Query(None, description="按文件夹筛选；不传则返回全部项目"),
    db: Session = Depends(get_db),
    space_id: Optional[int] = Depends(get_space_id)
):
    rows = list_autobi_projects_service(db, skip, limit, folder_id=folder_id, space_id=space_id)
    return [
        AutobiProjectListItem(
            id=r.id,
            api_access_id=r.api_access_id,
            name=r.name,
            description=r.description,
            knowledge_base_id=r.knowledge_base_id,
            folder_id=int(r.folder_id),
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
        for r in rows
    ]


@router.post("/projects/import", response_model=Dict[str, Any])
def import_project(
    body: AutobiProjectImport,
    db: Session = Depends(get_db),
    space_id: Optional[int] = Depends(get_space_id),
    operator_id: int = Depends(RequireSystemPermission("*")),
):
    return import_autobi_project_service(db, body, space_id)


@router.get("/projects/{project_id}/export", response_model=Dict[str, Any])
def export_project(
    project_id: int,
    db: Session = Depends(get_db),
    space_id: Optional[int] = Depends(get_space_id),
):
    return export_autobi_project_service(db, project_id, space_id)


@router.get("/projects/{project_id}")
def get_project(
    project_id: int,
    db: Session = Depends(get_db),
    space_id: Optional[int] = Depends(get_space_id)
) -> Dict[str, Any]:
    return get_autobi_project_service(db, project_id, space_id)


@router.post("/projects", response_model=Dict[str, Any])
def create_project(
    body: AutobiProjectCreate,
    db: Session = Depends(get_db),
    space_id: Optional[int] = Depends(get_space_id),
    operator_id: int = Depends(RequireSystemPermission("*")),
):
    return create_autobi_project_service(db, body, space_id)


@router.put("/projects/{project_id}", response_model=Dict[str, Any])
def update_project(
    project_id: int,
    body: AutobiProjectUpdate,
    db: Session = Depends(get_db),
    space_id: Optional[int] = Depends(get_space_id),
    operator_id: int = Depends(RequireSystemPermission("*")),
):
    return update_autobi_project_service(db, project_id, body, space_id)


@router.delete("/projects/{project_id}")
def delete_project(
    project_id: int,
    db: Session = Depends(get_db),
    space_id: Optional[int] = Depends(get_space_id),
    operator_id: int = Depends(RequireSystemPermission("*")),
):
    return delete_autobi_project_service(db, project_id, space_id)


@router.post("/projects/{project_id}/share")
def issue_share(
    project_id: int,
    rotate: bool = Query(False),
    db: Session = Depends(get_db),
    space_id: Optional[int] = Depends(get_space_id),
    operator_id: int = Depends(RequireSystemPermission("*")),
):
    """生成（或复用）外链分享 token。"""
    return issue_share_token_service(db, project_id, rotate=rotate, space_id=space_id)


@router.delete("/projects/{project_id}/share")
def revoke_share(
    project_id: int,
    db: Session = Depends(get_db),
    space_id: Optional[int] = Depends(get_space_id),
    operator_id: int = Depends(RequireSystemPermission("*")),
):
    """撤销外链分享 token。"""
    revoke_share_token_service(db, project_id, space_id)
    return {"ok": True}


@router.get("/projects/{project_id}/lab/chat-state")
def fetch_lab_chat_state(
    project_id: int,
    db: Session = Depends(get_db),
    space_id: Optional[int] = Depends(get_space_id)
):
    """实验室左侧对话与中间聊天内容（MySQL）；不含流水线步骤，步骤见 Redis trace。"""
    return get_lab_chat_state(db, project_id)


@router.put("/projects/{project_id}/lab/chat-state")
def save_lab_chat_state(
    project_id: int,
    body: AutobiLabChatStateUpsert,
    db: Session = Depends(get_db),
    space_id: Optional[int] = Depends(get_space_id)
):
    """覆盖保存当前项目的实验室对话状态。"""
    return upsert_lab_chat_state(db, project_id, body)


@router.put("/lab/traces/{trace_id}")
def put_lab_trace(trace_id: str, body: AutobiLabTraceUpsert):
    """单次提问流水线追踪日志（MySQL autobi_lab_traces 表）。对话正文见 chat-state。"""
    return upsert_lab_trace(trace_id, body)


@router.get("/lab/traces/{trace_id}")
def fetch_lab_trace(trace_id: str):
    """按 trace_id 读取流水线调试日志（MySQL）。"""
    return get_lab_trace(trace_id)


@router.post("/gateway/v2/lab")
async def lab_gateway_v2(body: LabGatewayV2Request):
    """
    与实验室 Chat 同序执行 18 步；全量步骤写入 MySQL trace（trace_id）。
    响应为 SSE：仅推送本次 trace_id、数据总结增量（delta），以及 done / error。
    """
    preflight_db = SessionLocal()
    try:
        spec = await read_database(preflight_db, build_lab_run_spec_from_api_request, body)
        trace = new_lab_trace_context()
    finally:
        preflight_db.close()

    async def event_stream():
        db = SessionLocal()
        try:
            async for chunk in stream_lab_native_sse(db, spec, trace=trace):
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


@router.post("/gateway/v2/lab-bailian")
async def lab_gateway_v2_bailian(body: LabGatewayV2Request):
    """
    新增百炼风格接口：复用实验室同源流水线，但将 SSE 事件包装为百炼 data 流格式。
    不改动原有 /gateway/v2/lab。
    """
    preflight_db = SessionLocal()
    try:
        spec = await read_database(preflight_db, build_lab_run_spec_from_api_request, body)
    finally:
        preflight_db.close()

    async def event_stream():
        db = SessionLocal()
        try:
            async for chunk in stream_lab_bailian_sse(db, spec):
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
