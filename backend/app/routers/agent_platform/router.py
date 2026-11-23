"""智能体平台 API"""
from typing import Any, Dict, List, Optional
import asyncio

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ...core.database import get_db
from ...core.permissions import RequireSystemPermission

from ...schemas.agent_app import (
    AgentAppCreate,
    AgentAppDetail,
    AgentAppSummary,
    AgentAppUpdate,
    AgentFolderCreate,
    AgentFolderItem,
    AgentFolderMoveBody,
    AgentFolderUpdate,
    AgentVersionCreate,
    AgentVersionParamsOut,
    AiChatRequest,
    AiChatResponse,
    AiCreatorBuildWorkflowBody,
    AiCreatorBuildWorkflowOut,
    SetOutputVersionBody,
    WorkflowGetOut,
    WorkflowPutBody,
    WorkflowRunBody,
    WorkflowRunOut,
)
from ...services.agent_app.ai_creator_service import run_ai_creator_chat
from ...services.agent_app.workflow_builder import build_workflow_from_design
from ...services.agent_app.service import (
    create_agent_app_folder_service,
    create_agent_app_service,
    create_version_service,
    delete_agent_app_folder_service,
    delete_agent_app_service,
    delete_version_service,
    get_agent_app_service,
    get_agent_run_trace_service,
    get_agent_version_params_service,
    get_workflow_version_service,
    go_offline_version_service,
    go_online_version_service,
    list_agent_app_folders_service,
    list_agent_apps_service,
    move_agent_app_folder_service,
    publish_version_service,
    put_workflow_version_service,
    run_workflow_version_service,
    set_output_version_service,
    to_detail,
    to_summary,
    update_agent_app_folder_service,
    update_agent_app_service,
)

router = APIRouter()


def get_space_id(space_id: Optional[int] = Query(None, description="空间ID")) -> Optional[int]:
    return space_id


@router.post("/ai-chat", response_model=AiChatResponse)
async def ai_creator_chat(
    body: AiChatRequest,
    db: Session = Depends(get_db),
    operator_id: int = Depends(RequireSystemPermission("*")),
):
    """AI 智能体创建助手：多轮对话 + 工具调用。"""
    return await run_ai_creator_chat(db, body)


@router.post("/ai-creator/build-workflow", response_model=AiCreatorBuildWorkflowOut)
def ai_creator_build_workflow(
    body: AiCreatorBuildWorkflowBody,
    operator_id: int = Depends(RequireSystemPermission("*")),
):
    """将 workflow_design + 已填参数转为画布 workflow_json。"""
    wf = build_workflow_from_design(body.workflow_design, body.filled_params)
    return AiCreatorBuildWorkflowOut(workflow=wf)


@router.get("/folders", response_model=List[AgentFolderItem])
def list_agent_folders(
    db: Session = Depends(get_db),
    space_id: Optional[int] = Depends(get_space_id),
):
    return list_agent_app_folders_service(db, space_id=space_id)


@router.post("/folders", response_model=AgentFolderItem)
def create_agent_folder(
    body: AgentFolderCreate,
    db: Session = Depends(get_db),
    space_id: Optional[int] = Depends(get_space_id),
    operator_id: int = Depends(RequireSystemPermission("*")),
):
    return create_agent_app_folder_service(db, body.name, space_id=space_id)


@router.put("/folders/{folder_id}", response_model=AgentFolderItem)
def update_agent_folder(
    folder_id: int,
    body: AgentFolderUpdate,
    db: Session = Depends(get_db),
    space_id: Optional[int] = Depends(get_space_id),
    operator_id: int = Depends(RequireSystemPermission("*")),
):
    return update_agent_app_folder_service(db, folder_id, body.name, space_id=space_id)


@router.delete("/folders/{folder_id}")
def delete_agent_folder(
    folder_id: int,
    db: Session = Depends(get_db),
    space_id: Optional[int] = Depends(get_space_id),
    operator_id: int = Depends(RequireSystemPermission("*")),
):
    return delete_agent_app_folder_service(db, folder_id, space_id=space_id)


@router.post("/folders/{folder_id}/move", response_model=List[AgentFolderItem])
def move_agent_folder(
    folder_id: int,
    body: AgentFolderMoveBody,
    db: Session = Depends(get_db),
    space_id: Optional[int] = Depends(get_space_id),
    operator_id: int = Depends(RequireSystemPermission("*")),
):
    return move_agent_app_folder_service(db, folder_id, body.direction, space_id=space_id)


@router.get("", response_model=List[AgentAppSummary])
def list_agent_apps(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    keyword: Optional[str] = Query(None, description="按名称/描述模糊搜索"),
    folder_id: Optional[int] = Query(None, description="按文件夹筛选"),
    db: Session = Depends(get_db),
    space_id: Optional[int] = Depends(get_space_id),
):
    rows = list_agent_apps_service(db, skip, limit, keyword, folder_id=folder_id, space_id=space_id)
    return [to_summary(r) for r in rows]


@router.post("", response_model=AgentAppDetail)
def create_agent_app(
    body: AgentAppCreate,
    db: Session = Depends(get_db),
    space_id: Optional[int] = Depends(get_space_id),
    operator_id: int = Depends(RequireSystemPermission("*")),
):
    row = create_agent_app_service(db, body, space_id=space_id)
    return to_detail(row)


@router.post("/{app_id}/versions", response_model=AgentAppDetail)
def create_version(
    app_id: int,
    body: AgentVersionCreate,
    db: Session = Depends(get_db),
    operator_id: int = Depends(RequireSystemPermission("*")),
):
    row = create_version_service(db, app_id, body)
    return to_detail(row)


@router.post("/{app_id}/versions/{version_id}/publish", response_model=AgentAppDetail)
def publish_version(
    app_id: int,
    version_id: int,
    db: Session = Depends(get_db),
    operator_id: int = Depends(RequireSystemPermission("*")),
):
    row = publish_version_service(db, app_id, version_id)
    return to_detail(row)


@router.post("/{app_id}/versions/{version_id}/online", response_model=AgentAppDetail)
def online_version(
    app_id: int,
    version_id: int,
    db: Session = Depends(get_db),
    operator_id: int = Depends(RequireSystemPermission("*")),
):
    row = go_online_version_service(db, app_id, version_id)
    return to_detail(row)


@router.post("/{app_id}/versions/{version_id}/offline", response_model=AgentAppDetail)
def offline_version(
    app_id: int,
    version_id: int,
    db: Session = Depends(get_db),
    operator_id: int = Depends(RequireSystemPermission("*")),
):
    row = go_offline_version_service(db, app_id, version_id)
    return to_detail(row)


@router.put("/{app_id}/output-version", response_model=AgentAppDetail)
def set_output_version(
    app_id: int,
    body: SetOutputVersionBody,
    db: Session = Depends(get_db),
    operator_id: int = Depends(RequireSystemPermission("*")),
):
    row = set_output_version_service(db, app_id, body)
    return to_detail(row)


@router.delete("/{app_id}/versions/{version_id}", response_model=AgentAppDetail)
def delete_version(
    app_id: int,
    version_id: int,
    db: Session = Depends(get_db),
    operator_id: int = Depends(RequireSystemPermission("*")),
):
    row = delete_version_service(db, app_id, version_id)
    return to_detail(row)


@router.get("/{app_id}/versions/{version_id}/workflow", response_model=WorkflowGetOut)
def get_workflow_version(
    app_id: int,
    version_id: int,
    db: Session = Depends(get_db),
):
    return get_workflow_version_service(db, app_id, version_id)


@router.put("/{app_id}/versions/{version_id}/workflow", response_model=WorkflowGetOut)
def put_workflow_version(
    app_id: int,
    version_id: int,
    body: WorkflowPutBody,
    db: Session = Depends(get_db),
    operator_id: int = Depends(RequireSystemPermission("*")),
):
    return put_workflow_version_service(db, app_id, version_id, body)


@router.post(
    "/{app_id}/versions/{version_id}/run",
    response_model=WorkflowRunOut,
)
async def run_workflow_version(
    app_id: int,
    version_id: int,
    body: WorkflowRunBody,
    db: Session = Depends(get_db),
    operator_id: int = Depends(RequireSystemPermission("*")),
):
    return await run_workflow_version_service(db, app_id, version_id, body)


@router.post(
    "/{app_id}/versions/{version_id}/run/stream",
)
async def run_workflow_version_stream(
    app_id: int,
    version_id: int,
    body: WorkflowRunBody,
    db: Session = Depends(get_db),
    operator_id: int = Depends(RequireSystemPermission("*")),
):
    from ...services.agent_app.workflow_engine import run_agent_workflow_stream
    return StreamingResponse(
        run_agent_workflow_stream(db, app_id, version_id, body.inputs or {}),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{app_id}/runs/{run_id}")
def get_agent_run_trace(
    app_id: int,
    run_id: str,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    return get_agent_run_trace_service(db, app_id, run_id)


# ---------------------------------------------------------------------------
# 工作流运行日志（trace 持久化查询）
# ---------------------------------------------------------------------------


@router.get("/traces")
def list_agent_traces(
    keyword: Optional[str] = Query(None, description="按 trace_id/app_name 模糊搜索"),
    app_name: Optional[str] = Query(None, description="按应用名精确筛选"),
    status: Optional[str] = Query(None, description="running|done|error"),
    date_from: Optional[str] = Query(None, description="开始日期 YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """工作流运行日志列表（含搜索/筛选）。"""
    from ...services.agent_app.trace_service import list_workflow_traces
    return list_workflow_traces(
        db,
        keyword=keyword,
        app_name=app_name,
        status=status,
        date_from=date_from,
        date_to=date_to,
        skip=skip,
        limit=limit,
    )


@router.get("/traces/{trace_id}")
def get_agent_trace_detail(
    trace_id: str,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """统一查询 trace：先查工作流表，再查实验室表，返回含 type 字段。"""
    from ...services.agent_app.trace_service import get_workflow_trace, get_child_traces

    # 1) 先查工作流 trace
    wf = get_workflow_trace(trace_id)
    if wf is not None:
        wf["type"] = "workflow"
        # 附加子 trace 摘要
        wf["child_traces"] = get_child_traces(trace_id)
        # 附加父 trace 摘要（用于调用链）
        if wf.get("parent_trace_id"):
            parent = get_workflow_trace(wf["parent_trace_id"])
            if parent:
                wf["parent_trace"] = {
                    "trace_id": parent["trace_id"],
                    "app_name": parent.get("app_name"),
                    "status": parent.get("status"),
                }
        return wf

    # 2) 再查实验室 trace
    from ...core.redis_client import trace_get

    lab = trace_get(trace_id)
    if lab is not None:
        # normalize lab steps to match frontend expectations
        steps = lab.get("steps") or []
        normalized = []
        for s in steps:
            if isinstance(s, dict):
                normalized.append({
                    "step_uuid": s.get("step_uuid"),
                    "step_id": s.get("step_id"),
                    "title": s.get("title"),
                    "api_key": s.get("api_key"),
                    "color": s.get("color"),
                    "status": s.get("status"),
                    "request": s.get("request"),
                    "response": s.get("response"),
                    "error": s.get("error"),
                    "duration_ms": s.get("duration_ms"),
                })
        lab["steps"] = normalized
        lab["type"] = "lab"
        return lab

    from fastapi import HTTPException
    raise HTTPException(status_code=404, detail="追踪记录不存在")


@router.get("/{app_id}/traces")
def list_app_traces(
    app_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=200),
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """按应用筛选的工作流运行日志。"""
    from ...services.agent_app.trace_service import list_workflow_traces
    return list_workflow_traces(
        db,
        app_id=app_id,
        status=status,
        skip=skip,
        limit=limit,
    )


@router.put("/{app_id}", response_model=AgentAppDetail)
def update_agent_app(
    app_id: int,
    body: AgentAppUpdate,
    db: Session = Depends(get_db),
    space_id: Optional[int] = Depends(get_space_id),
    operator_id: int = Depends(RequireSystemPermission("*")),
):
    row = update_agent_app_service(db, app_id, body, space_id=space_id)
    return to_detail(row)


@router.delete("/{app_id}")
def delete_agent_app(
    app_id: int,
    db: Session = Depends(get_db),
    operator_id: int = Depends(RequireSystemPermission("*")),
) -> dict:
    """软删除应用；返回 JSON 以便统一响应包装与前端 axios 解析。"""
    delete_agent_app_service(db, app_id)
    return {"deleted": True}


@router.get("/{app_id}", response_model=AgentAppDetail)
def get_agent_app(app_id: int, db: Session = Depends(get_db)):
    row = get_agent_app_service(db, app_id)
    return to_detail(row)


@router.get("/{app_id}/versions/{version_id}/params", response_model=AgentVersionParamsOut)
def get_agent_version_params(app_id: int, version_id: int, db: Session = Depends(get_db)):
    return get_agent_version_params_service(db, app_id, version_id)
