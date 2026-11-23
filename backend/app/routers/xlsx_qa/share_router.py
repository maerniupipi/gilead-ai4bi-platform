"""
XLSX 表格智能问答 · 外链分享（免登录）

仅凭 `xlsx_qa_module.share_token` 访问；不包含改提示词 / 删文档等高危操作。
"""
from __future__ import annotations

from typing import List
from urllib.parse import quote

from fastapi import APIRouter, Body, Depends, File, Query, UploadFile
from fastapi import HTTPException
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.orm import Session

from ...core.database import get_db
from ...repositories.xlsx_qa import XlsxQaRepository
from ...schemas.xlsx_qa import (
    XlsxQaAskRequest,
    XlsxQaConversationCreate,
    XlsxQaConversationInfo,
    XlsxQaDocumentInfo,
    XlsxQaDownloadOut,
    XlsxQaExportPptRequest,
    XlsxQaMessageInfo,
    XlsxQaModuleDetail,
    XlsxQaPptExportAsyncResponse,
    XlsxQaPptHistoryOut,
    XlsxQaPreviewOut,
)
from ...services.xlsx_qa import service as svc

router = APIRouter()


def _module_id_from_token(db: Session, token: str) -> int:
    m = XlsxQaRepository.get_module_by_share_token(db, token)
    if not m:
        raise HTTPException(status_code=404, detail="分享链接无效或已失效")
    return m.id


def _assert_conv_in_share(db: Session, token: str, conv_id: int) -> int:
    mid = _module_id_from_token(db, token)
    conv = XlsxQaRepository.get_conversation(db, conv_id)
    if not conv or conv.module_id != mid:
        raise HTTPException(status_code=404, detail="会话不存在")
    return mid


def _assert_doc_in_share(db: Session, token: str, doc_id: int) -> int:
    mid = _module_id_from_token(db, token)
    doc = XlsxQaRepository.get_document(db, doc_id)
    if not doc or doc.module_id != mid:
        raise HTTPException(status_code=404, detail="文档不存在")
    return mid


@router.get("/{token}/module", response_model=XlsxQaModuleDetail)
def share_get_module(token: str, db: Session = Depends(get_db)):
    mid = _module_id_from_token(db, token)
    return svc.get_module_detail_service(db, mid)


@router.get(
    "/{token}/conversations",
    response_model=List[XlsxQaConversationInfo],
)
def share_list_conversations(token: str, db: Session = Depends(get_db)):
    mid = _module_id_from_token(db, token)
    return svc.list_conversations_service(db, mid)


@router.post(
    "/{token}/conversations",
    response_model=XlsxQaConversationInfo,
)
def share_create_conversation(
    token: str,
    body: XlsxQaConversationCreate = Body(default_factory=XlsxQaConversationCreate),
    db: Session = Depends(get_db),
):
    mid = _module_id_from_token(db, token)
    return svc.create_conversation_service(db, mid, body)


@router.delete("/{token}/conversations/{conv_id}")
def share_delete_conversation(token: str, conv_id: int, db: Session = Depends(get_db)) -> dict:
    _assert_conv_in_share(db, token, conv_id)
    svc.delete_conversation_service(db, conv_id)
    return {"deleted": True}


@router.get(
    "/{token}/conversations/{conv_id}/messages",
    response_model=List[XlsxQaMessageInfo],
)
def share_list_messages(token: str, conv_id: int, db: Session = Depends(get_db)):
    _assert_conv_in_share(db, token, conv_id)
    return svc.list_messages_service(db, conv_id)


@router.post("/{token}/conversations/{conv_id}/ask")
async def share_ask(
    token: str,
    conv_id: int,
    body: XlsxQaAskRequest,
    db: Session = Depends(get_db),
):
    _assert_conv_in_share(db, token, conv_id)
    generator = await svc.ask_stream_service(db, conv_id, body)
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{token}/insight")
def share_get_insight(token: str, db: Session = Depends(get_db)):
    """分享链路：获取已保存的模块级洞察报告。"""
    mid = _module_id_from_token(db, token)
    return svc.get_insight_report_service(db, mid)


@router.post("/{token}/insight")
async def share_insight(token: str, db: Session = Depends(get_db)):
    """分享链路：模块级洞察报告 SSE（免登录）。"""
    mid = _module_id_from_token(db, token)
    generator = await svc.insight_stream_service(db, mid)
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/{token}/conversations/{conv_id}/export-ppt")
def share_export_ppt(
    token: str,
    conv_id: int,
    body: XlsxQaExportPptRequest = Body(default_factory=XlsxQaExportPptRequest),
    db: Session = Depends(get_db),
):
    _assert_conv_in_share(db, token, conv_id)
    data, filename = svc.export_conversation_ppt_service(db, conv_id, body)
    ascii_name = filename.encode("ascii", errors="ignore").decode("ascii") or "xlsx-qa.pptx"
    disp = (
        f'attachment; filename="{ascii_name}"; '
        f"filename*=UTF-8''{quote(filename)}"
    )
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": disp},
    )


@router.post("/{token}/conversations/{conv_id}/export-pdf")
def share_export_pdf(
    token: str,
    conv_id: int,
    body: XlsxQaExportPptRequest = Body(default_factory=XlsxQaExportPptRequest),
    db: Session = Depends(get_db),
):
    _assert_conv_in_share(db, token, conv_id)
    data, filename = svc.export_conversation_pdf_service(db, conv_id, body)
    encoded = quote(filename)
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded}"},
    )


@router.post("/{token}/insight/export-pdf")
def share_export_insight_pdf(
    token: str,
    db: Session = Depends(get_db),
):
    mid = _module_id_from_token(db, token)
    data, filename = svc.export_insight_pdf_service(db, mid)
    encoded = quote(filename)
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded}"},
    )


@router.post("/{token}/insight/export-ppt", response_model=XlsxQaPptExportAsyncResponse)
def share_start_insight_ppt_export(
    token: str,
    db: Session = Depends(get_db),
):
    """分享链路：启动异步数据深度洞察 PPT 导出。"""
    mid = _module_id_from_token(db, token)
    history = svc.start_insight_ppt_export_async(db, mid)
    return {"history_id": history.id, "status": "generating"}


@router.get("/{token}/ppt-history", response_model=List[XlsxQaPptHistoryOut])
def share_list_ppt_history(token: str, db: Session = Depends(get_db)):
    mid = _module_id_from_token(db, token)
    return svc.list_ppt_history_service(db, mid)


@router.get("/{token}/ppt-history/{history_id}/download", response_model=XlsxQaDownloadOut)
def share_download_ppt_history(token: str, history_id: int, db: Session = Depends(get_db)):
    mid = _module_id_from_token(db, token)
    h = XlsxQaRepository.get_ppt_history(db, history_id)
    if not h or h.module_id != mid:
        raise HTTPException(status_code=404, detail="记录不存在")
    return svc.ppt_history_download_service(db, history_id)


@router.delete("/{token}/ppt-history/{history_id}")
def share_delete_ppt_history(token: str, history_id: int, db: Session = Depends(get_db)) -> dict:
    mid = _module_id_from_token(db, token)
    h = XlsxQaRepository.get_ppt_history(db, history_id)
    if not h or h.module_id != mid:
        raise HTTPException(status_code=404, detail="记录不存在")
    svc.delete_ppt_history_service(db, history_id)
    return {"deleted": True}


@router.post("/{token}/documents", response_model=XlsxQaDocumentInfo)
async def share_upload_document(
    token: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    mid = _module_id_from_token(db, token)
    return await svc.upload_document_service(db, mid, file)


@router.get(
    "/{token}/documents/{doc_id}/download",
    response_model=XlsxQaDownloadOut,
)
def share_download_document(token: str, doc_id: int, db: Session = Depends(get_db)):
    mid = _assert_doc_in_share(db, token, doc_id)
    return svc.download_document_service(db, mid, doc_id)


@router.get(
    "/{token}/documents/{doc_id}/preview",
    response_model=XlsxQaPreviewOut,
)
def share_preview_document(
    token: str,
    doc_id: int,
    limit: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
):
    mid = _assert_doc_in_share(db, token, doc_id)
    return svc.preview_document_service(db, mid, doc_id, limit=limit)


@router.get(
    "/{token}/documents/{doc_id}/sheets/{sheet_id}/preview",
    response_model=XlsxQaPreviewOut,
)
def share_preview_sheet(
    token: str,
    doc_id: int,
    sheet_id: int,
    limit: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
):
    mid = _assert_doc_in_share(db, token, doc_id)
    return svc.preview_document_service(db, mid, doc_id, limit=limit, sheet_id=sheet_id)
