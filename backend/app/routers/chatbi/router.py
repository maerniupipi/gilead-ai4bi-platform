from uuid import UUID
from fastapi import APIRouter, BackgroundTasks, Depends, Header, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.routing import APIRoute
from sqlalchemy.orm import Session

from ...core.database import get_db
from ...schemas.chatbi import AppInfo, ChatRequest, UserRequest, PPTRequest, XLSXRequest, ExportState, DownloadURL
from ...services.chatbi.config import APIError, validate_inputs
from ...services.chatbi.credentials import ServiceCredential, resolve_credential
from ...services.chatbi.chat import prepare_chat, stream_chat, stop_chat
from ...services.chatbi.exports import create_export, export_state, get_job, download_url, signed_file, file_path
from ...core.observability import bind_context


class ChatBIRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()
        async def wrapped(request):
            try:
                return await handler(request)
            except APIError as exc:
                return JSONResponse(exc.body(), status_code=exc.status)
            except RequestValidationError:
                return JSONResponse({"status": 400, "code": "invalid_param", "message": "请求字段不符合接口约定"}, status_code=400)
        return wrapped


def service_auth(authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    return resolve_credential(db, authorization)


router = APIRouter(prefix="/api/service", tags=["平台服务"], route_class=ChatBIRoute)
private = APIRouter(dependencies=[Depends(service_auth)], route_class=ChatBIRoute)


@private.get("/info", response_model=AppInfo, summary="验证服务凭证并获取应用信息")
def info():
    # Authentication only: does not start analysis, create a session or issue a token.
    return AppInfo()


@private.post("/chat-messages", responses={200: {"content": {"text/event-stream": {"schema": {"type": "string"}}}}})
async def chat_messages(body: ChatRequest, request: Request, db: Session = Depends(get_db), credential: ServiceCredential = Depends(service_auth)):
    user = credential.user(body.user)
    bind_context(user_id=user.user_id)
    validate_inputs(body.inputs)
    mid = prepare_chat(db, body, user, runtime=credential.chat_runtime(db), original_request={
        'method':request.method,'path':request.url.path,'query_params':dict(request.query_params),
        'headers':dict(request.headers),'body':await request.json()})
    return StreamingResponse(stream_chat(mid, body, user, request), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache, no-store, no-transform",
                                      "X-Accel-Buffering": "no"})


@private.post("/chat-messages/{task_id}/stop")
def stop(task_id: UUID, body: UserRequest, db: Session = Depends(get_db), credential: ServiceCredential = Depends(service_auth)):
    return stop_chat(db, task_id, credential.user(body.user))


@private.post("/exports/ppt", status_code=202, response_model=ExportState)
def ppt(body: PPTRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db), credential: ServiceCredential = Depends(service_auth)):
    return export_state(create_export(db, "ppt", body, credential.user(body.user), background_tasks=background_tasks), db)




@private.post("/exports/xlsx", status_code=202, response_model=ExportState)
def xlsx(body: XLSXRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db), credential: ServiceCredential = Depends(service_auth)):
    return export_state(create_export(db, "xlsx", body, credential.user(body.user), background_tasks=background_tasks))


@private.get("/export-tasks/{task_id}", response_model=ExportState)
def task(task_id: UUID, user: str = Query(...), db: Session = Depends(get_db), credential: ServiceCredential = Depends(service_auth)):
    return export_state(get_job(db, task_id, credential.user(user)), db)


@private.get("/files/{file_id}/download-url", response_model=DownloadURL)
def url(file_id: UUID, request: Request, user: str = Query(...), db: Session = Depends(get_db), credential: ServiceCredential = Depends(service_auth)):
    return download_url(db, file_id, credential.user(user), str(request.base_url))


router.include_router(private)


@router.get("/files/{file_id}/content", include_in_schema=False)
def content(file_id: UUID, expires: int, signature: str, db: Session = Depends(get_db)):
    job = signed_file(db, file_id, expires, signature)
    mime = "application/vnd.openxmlformats-officedocument." + ("spreadsheetml.sheet" if job.kind == "xlsx" else "presentationml.presentation")
    return FileResponse(file_path(job), filename=job.file_name, media_type=mime,
                        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})
