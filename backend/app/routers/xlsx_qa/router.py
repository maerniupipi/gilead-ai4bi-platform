"""
XLSX 表格智能问答 · 路由

职责纯 controller：接收参数 → 调 service → 原样返回。
对话接口 `/conversations/{id}/ask` 返回 SSE（text/event-stream），由 service 生成 async generator。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import json

from pathlib import Path

from fastapi import APIRouter, Body, Depends, File, Form, Header, Query, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse
from sqlalchemy.orm import Session
from urllib.parse import quote

from ...core.database import get_db
from ...core.permissions import RequireSystemPermission
from ...schemas.xlsx_qa import (
    XlsxQaAskRequest,
    XlsxQaConversationCreate,
    XlsxQaConversationInfo,
    XlsxQaConversationSheetUpdate,
    XlsxQaDocumentInfo,
    XlsxQaDownloadOut,
    XlsxQaExportPptRequest,
    XlsxQaKnowledgeAppendRequest,
    XlsxQaKnowledgeAppendOut,
    XlsxQaMessageInfo,
    XlsxQaModuleCreate,
    XlsxQaModuleDetail,
    XlsxQaModuleSummary,
    XlsxQaModuleUpdate,
    XlsxQaPptExportAsyncResponse,
    XlsxQaPptTemplateOut,
    XlsxQaPreviewOut,
    XlsxQaPromptsConfig,
    XlsxQaPromptsConfigOut,
    XlsxQaShareIssueOut,
    XlsxQaShareIssueRequest,
    XlsxQaSheetInfo,
    XlsxQaSheetRegenerateOut,
    XlsxQaSheetUnderstandingUpdate,
)
from ...services.xlsx_qa import service as svc
from ...repositories.xlsx_qa import XlsxQaRepository
from ...repositories.user.repository import UserRepository

router = APIRouter()


# ---------------------------------------------------------------------------
# 模块
# ---------------------------------------------------------------------------

@router.get("/modules", response_model=List[XlsxQaModuleSummary])
def list_modules(
    keyword: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    return svc.list_modules_service(db, keyword=keyword, skip=skip, limit=limit)


@router.post("/modules", response_model=XlsxQaModuleDetail)
def create_module(
    body: XlsxQaModuleCreate,
    db: Session = Depends(get_db),
    operator_id: int = Depends(RequireSystemPermission("*")),
):
    return svc.create_module_service(db, body)


@router.get("/modules/{module_id}", response_model=XlsxQaModuleDetail)
def get_module(module_id: int, db: Session = Depends(get_db)):
    return svc.get_module_detail_service(db, module_id)


@router.put("/modules/{module_id}", response_model=XlsxQaModuleDetail)
def update_module(
    module_id: int,
    body: XlsxQaModuleUpdate,
    db: Session = Depends(get_db),
    operator_id: int = Depends(RequireSystemPermission("*")),
):
    return svc.update_module_service(db, module_id, body)


@router.delete("/modules/{module_id}")
def delete_module(
    module_id: int,
    db: Session = Depends(get_db),
    operator_id: int = Depends(RequireSystemPermission("*")),
) -> dict:
    svc.delete_module_service(db, module_id)
    return {"deleted": True}


@router.post("/modules/{module_id}/share", response_model=XlsxQaShareIssueOut)
def issue_module_share(
    module_id: int,
    body: XlsxQaShareIssueRequest = Body(default_factory=XlsxQaShareIssueRequest),
    db: Session = Depends(get_db),
    operator_id: int = Depends(RequireSystemPermission("*")),
):
    """生成或复用分享 token（与主站登录无关；勿把密码写进 URL，请只分发 token 链接）。"""
    return svc.issue_share_token_service(db, module_id, rotate=body.rotate)


@router.delete("/modules/{module_id}/share")
def revoke_module_share(
    module_id: int,
    db: Session = Depends(get_db),
    operator_id: int = Depends(RequireSystemPermission("*")),
) -> dict:
    svc.revoke_share_token_service(db, module_id)
    return {"revoked": True}


@router.get("/modules/{module_id}/insight")
def get_module_insight(module_id: int, db: Session = Depends(get_db)) -> Dict[str, Any]:
    """获取模块已保存的深度洞察报告（如果存在）。"""
    return svc.get_insight_report_service(db, module_id)


@router.post("/modules/{module_id}/insight")
async def module_insight(module_id: int, db: Session = Depends(get_db)):
    """SSE：生成模块级数据深度洞察报告（无需会话）。"""
    generator = await svc.insight_stream_service(db, module_id)
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# 高级设置：提示词
# ---------------------------------------------------------------------------

@router.get(
    "/modules/{module_id}/prompts",
    response_model=XlsxQaPromptsConfigOut,
)
def get_module_prompts(module_id: int, db: Session = Depends(get_db)):
    return svc.get_module_prompts_service(db, module_id)


@router.put(
    "/modules/{module_id}/prompts",
    response_model=XlsxQaPromptsConfigOut,
)
def update_module_prompts(
    module_id: int,
    body: XlsxQaPromptsConfig,
    db: Session = Depends(get_db),
    operator_id: int = Depends(RequireSystemPermission("*")),
):
    return svc.update_module_prompts_service(db, module_id, body)


# ---------------------------------------------------------------------------
# 文档：上传 / 下载 / 预览 / 删除
# ---------------------------------------------------------------------------

@router.post("/modules/{module_id}/documents", response_model=XlsxQaDocumentInfo)
async def upload_document(
    module_id: int,
    file: UploadFile = File(...),
    sheet_indices: Optional[str] = Query(None, description="逗号分隔的 Sheet 索引列表（0-based），如 0,2,4"),
    db: Session = Depends(get_db),
    operator_id: int = Depends(RequireSystemPermission("*")),
):
    """上传 xlsx 文件。可选 sheet_indices 指定要解析的 Sheet（逗号分隔，0-based）。"""
    indices: Optional[List[int]] = None
    if sheet_indices:
        try:
            indices = [int(x.strip()) for x in sheet_indices.split(",") if x.strip()]
        except ValueError:
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail="sheet_indices 格式错误，示例: 0,2,4")
    return await svc.upload_document_service(db, module_id, file, sheet_indices=indices)


@router.delete("/modules/{module_id}/documents/{doc_id}")
def delete_document(
    module_id: int,
    doc_id: int,
    db: Session = Depends(get_db),
    operator_id: int = Depends(RequireSystemPermission("*")),
) -> dict:
    svc.delete_document_service(db, module_id, doc_id)
    return {"deleted": True}


@router.get(
    "/modules/{module_id}/documents/{doc_id}/download",
    response_model=XlsxQaDownloadOut,
)
def download_document(module_id: int, doc_id: int, db: Session = Depends(get_db)):
    return svc.download_document_service(db, module_id, doc_id)


@router.post(
    "/modules/{module_id}/documents/{doc_id}/regenerate-understanding",
    response_model=XlsxQaDocumentInfo,
)
async def regenerate_understanding(
    module_id: int, doc_id: int, db: Session = Depends(get_db),
    operator_id: int = Depends(RequireSystemPermission("*")),
):
    return await svc.regenerate_understanding_service(db, module_id, doc_id)


# ---------------------------------------------------------------------------
# 知识追加（采纳知识卡片）
# ---------------------------------------------------------------------------

@router.post("/knowledge/append", response_model=XlsxQaKnowledgeAppendOut)
def append_knowledge(
    body: XlsxQaKnowledgeAppendRequest,
    db: Session = Depends(get_db),
    operator_id: int = Depends(RequireSystemPermission("*")),
):
    """将用户采纳的知识追加到文档的 understanding_md。"""
    return svc.append_knowledge_service(db, body)


@router.get(
    "/modules/{module_id}/documents/{doc_id}/preview",
    response_model=XlsxQaPreviewOut,
)
def preview_document(
    module_id: int,
    doc_id: int,
    limit: int = Query(20, ge=1, le=200),
    sheet_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    return svc.preview_document_service(db, module_id, doc_id, limit=limit, sheet_id=sheet_id)


# ---------------------------------------------------------------------------
# Sheet 级操作
# ---------------------------------------------------------------------------

@router.get(
    "/modules/{module_id}/documents/{doc_id}/sheets/{sheet_id}/preview",
    response_model=XlsxQaPreviewOut,
)
def preview_sheet(
    module_id: int,
    doc_id: int,
    sheet_id: int,
    limit: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
):
    return svc.preview_document_service(db, module_id, doc_id, limit=limit, sheet_id=sheet_id)


@router.post(
    "/modules/{module_id}/documents/{doc_id}/sheets/{sheet_id}/regenerate",
    response_model=XlsxQaSheetRegenerateOut,
)
async def regenerate_sheet_understanding(
    module_id: int,
    doc_id: int,
    sheet_id: int,
    db: Session = Depends(get_db),
    operator_id: int = Depends(RequireSystemPermission("*")),
):
    return await svc.regenerate_sheet_understanding_service(db, module_id, doc_id, sheet_id)


@router.patch(
    "/modules/{module_id}/documents/{doc_id}/sheets/{sheet_id}/understanding",
    response_model=XlsxQaSheetRegenerateOut,
)
def update_sheet_understanding(
    module_id: int,
    doc_id: int,
    sheet_id: int,
    body: XlsxQaSheetUnderstandingUpdate = Body(...),
    db: Session = Depends(get_db),
    operator_id: int = Depends(RequireSystemPermission("*")),
):
    return svc.update_sheet_understanding_service(db, module_id, doc_id, sheet_id, body.understanding_md)


# ---------------------------------------------------------------------------
# 模块级汇总理解
# ---------------------------------------------------------------------------

@router.post("/modules/{module_id}/regenerate-summary")
async def regenerate_module_summary(
    module_id: int,
    db: Session = Depends(get_db),
    operator_id: int = Depends(RequireSystemPermission("*")),
) -> Dict[str, Any]:
    md = await svc.regenerate_module_summary_service(db, module_id)
    return {"module_understanding_md": md}


# ---------------------------------------------------------------------------
# 会话 / 消息
# ---------------------------------------------------------------------------

@router.get(
    "/modules/{module_id}/conversations",
    response_model=List[XlsxQaConversationInfo],
)
def list_conversations(module_id: int, db: Session = Depends(get_db)):
    return svc.list_conversations_service(db, module_id)


@router.post(
    "/modules/{module_id}/conversations",
    response_model=XlsxQaConversationInfo,
)
def create_conversation(
    module_id: int,
    body: XlsxQaConversationCreate = Body(default_factory=XlsxQaConversationCreate),
    db: Session = Depends(get_db),
):
    return svc.create_conversation_service(db, module_id, body)


@router.delete("/conversations/{conv_id}")
def delete_conversation(conv_id: int, db: Session = Depends(get_db)) -> dict:
    svc.delete_conversation_service(db, conv_id)
    return {"deleted": True}


@router.get(
    "/conversations/{conv_id}/messages",
    response_model=List[XlsxQaMessageInfo],
)
def list_messages(conv_id: int, db: Session = Depends(get_db)):
    return svc.list_messages_service(db, conv_id)


@router.get("/ppt-templates", response_model=List[XlsxQaPptTemplateOut])
def list_ppt_templates(db: Session = Depends(get_db)):
    """获取所有 PPT 模板（内置 + 自定义）。"""
    rows = XlsxQaRepository.list_ppt_templates(db)
    return [
        XlsxQaPptTemplateOut(
            id=r.id,
            name=r.name,
            description=r.description or "",
            layout=r.layout,
            colors=r.colors or {},
            layout_config=r.layout_config or None,
            is_builtin=bool(r.is_builtin),
            sort_order=r.sort_order or 0,
        )
        for r in rows
    ]


@router.post("/conversations/{conv_id}/export-ppt", response_model=XlsxQaPptExportAsyncResponse)
def start_ppt_export(
    conv_id: int,
    body: XlsxQaExportPptRequest = Body(default_factory=XlsxQaExportPptRequest),
    db: Session = Depends(get_db),
    current_user_id: int = Header(default=1, alias="X-User-Id"),
):
    """启动异步 PPT 导出（自动导出全部 assistant 消息）。"""
    user = UserRepository.get_by_id(db, current_user_id)
    author = (user.display_name or user.username) if user else None
    history = svc.start_ppt_export_async(db, conv_id, body, author=author)
    return {"history_id": history.id, "status": "generating"}


@router.post("/conversations/{conv_id}/export-pdf")
def export_conversation_pdf(
    conv_id: int,
    body: XlsxQaExportPptRequest = Body(default_factory=XlsxQaExportPptRequest),
    db: Session = Depends(get_db),
    current_user_id: int = Header(default=1, alias="X-User-Id"),
):
    user = UserRepository.get_by_id(db, current_user_id)
    author = (user.display_name or user.username) if user else None
    data, filename = svc.export_conversation_pdf_service(db, conv_id, body, author=author)
    encoded = quote(filename)
    headers = {"Content-Disposition": f"attachment; filename*=UTF-8''{encoded}"}
    return Response(content=data, media_type="application/pdf", headers=headers)


@router.post("/modules/{module_id}/insight/export-pdf")
def export_insight_pdf(
    module_id: int,
    db: Session = Depends(get_db),
    current_user_id: int = Header(default=1, alias="X-User-Id"),
):
    user = UserRepository.get_by_id(db, current_user_id)
    author = (user.display_name or user.username) if user else None
    data, filename = svc.export_insight_pdf_service(db, module_id, author=author)
    encoded = quote(filename)
    headers = {"Content-Disposition": f"attachment; filename*=UTF-8''{encoded}"}
    return Response(content=data, media_type="application/pdf", headers=headers)


@router.post("/modules/{module_id}/insight/export-ppt", response_model=XlsxQaPptExportAsyncResponse)
def start_insight_ppt_export(
    module_id: int,
    db: Session = Depends(get_db),
    current_user_id: int = Header(default=1, alias="X-User-Id"),
):
    """启动异步数据深度洞察 PPT 导出。"""
    user = UserRepository.get_by_id(db, current_user_id)
    author = (user.display_name or user.username) if user else None
    history = svc.start_insight_ppt_export_async(db, module_id, author=author)
    return {"history_id": history.id, "status": "generating"}


@router.post("/conversations/{conv_id}/export-custom-ppt", response_model=XlsxQaPptExportAsyncResponse)
def start_custom_ppt_export(
    conv_id: int,
    payload: str = Form(...),
    logo: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    current_user_id: int = Header(default=1, alias="X-User-Id"),
):
    """启动异步专属定制 PPT 导出。"""
    try:
        body = XlsxQaExportPptRequest(**json.loads(payload or "{}"))
    except Exception:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="导出参数格式错误")

    logo_bytes = None
    if logo is not None:
        if logo.content_type and logo.content_type not in {"image/png", "image/jpeg", "image/jpg"}:
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail="Logo 仅支持 PNG/JPG")
        logo_bytes = logo.file.read()
        if len(logo_bytes) > 2 * 1024 * 1024:
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail="Logo 文件不能超过 2MB")

    user = UserRepository.get_by_id(db, current_user_id)
    author = (user.display_name or user.username) if user else None
    history = svc.start_ppt_export_async(db, conv_id, body, author=author, logo_bytes=logo_bytes, is_custom=True)
    return {"history_id": history.id, "status": "generating"}


# ---------------------------------------------------------------------------
# PPT 导出历史
# ---------------------------------------------------------------------------

@router.get("/modules/{module_id}/ppt-history")
def list_ppt_history(module_id: int, db: Session = Depends(get_db)):
    """列出模块的所有 PPT 导出历史。"""
    return svc.list_ppt_history_service(db, module_id)


@router.get("/ppt-history/{history_id}/download", response_model=XlsxQaDownloadOut)
def download_ppt_history(history_id: int, db: Session = Depends(get_db)):
    """获取 PPT 历史记录的下载 URL。"""
    return svc.ppt_history_download_service(db, history_id)


@router.delete("/ppt-history/{history_id}")
def delete_ppt_history(
    history_id: int,
    db: Session = Depends(get_db),
    _op: None = Depends(RequireSystemPermission("*")),
) -> Dict[str, Any]:
    """删除 PPT 导出历史记录及其 OSS 文件。"""
    svc.delete_ppt_history_service(db, history_id)
    return {"deleted": True}


# ---------------------------------------------------------------------------
# 模块 Logo
# ---------------------------------------------------------------------------

@router.post("/modules/{module_id}/logo")
def upload_module_logo(
    module_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _op: None = Depends(RequireSystemPermission("*")),
) -> Dict[str, Any]:
    """上传模块 Logo（存储到 OSS）。"""
    return svc.upload_module_logo_service(db, module_id, file)


@router.get("/modules/{module_id}/logo")
def get_module_logo(module_id: int, db: Session = Depends(get_db)):
    """获取模块 Logo 的预签名 URL。"""
    url = svc.get_module_logo_url_service(db, module_id)
    if not url:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="模块未设置 Logo")
    return {"url": url}


@router.delete("/modules/{module_id}/logo")
def delete_module_logo(
    module_id: int,
    db: Session = Depends(get_db),
    _op: None = Depends(RequireSystemPermission("*")),
) -> Dict[str, Any]:
    """删除模块 Logo。"""
    svc.delete_module_logo_service(db, module_id)
    return {"deleted": True}


# ---------------------------------------------------------------------------
# 自定义模板封面预览
# ---------------------------------------------------------------------------

@router.get("/ppt-templates/custom-cover")
def get_custom_ppt_cover():
    """返回专属定制模板的封面背景图（供前端预览）。"""
    cover_path = Path(__file__).resolve().parents[3] / "assets" / "cover_bg.png"
    if not cover_path.exists():
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="封面背景图不存在")
    return FileResponse(
        str(cover_path),
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.patch("/conversations/{conv_id}/sheets")
def update_conversation_sheets(
    conv_id: int,
    body: XlsxQaConversationSheetUpdate,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    return svc.update_conversation_sheets_service(db, conv_id, body)


@router.post("/conversations/{conv_id}/ask")
async def ask(
    conv_id: int,
    body: XlsxQaAskRequest,
    db: Session = Depends(get_db),
):
    """
    SSE 流式响应；事件序列：
      user_message_saved → plan → sql / sql_result(多次) → summary → done
    任一阶段失败会提前发 error 事件并关闭流。
    """
    generator = await svc.ask_stream_service(db, conv_id, body)
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )
