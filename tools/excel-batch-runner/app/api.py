"""Local service methods and HTTP routes. Tests call methods directly."""
import asyncio
from collections import Counter
from contextlib import asynccontextmanager
import hmac
from io import BytesIO
import json
import os
from pathlib import Path
import secrets
from urllib.parse import unquote, urlsplit
from uuid import uuid4
from zipfile import ZipFile, ZIP_DEFLATED

from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from sqlalchemy.exc import SQLAlchemyError

from app.auth import COOKIE_NAME, HistoryEdit, LoginLimiter, LoginRequest
from app.database import Database
from app.models import CURRENT_OUTPUT_FORMAT, RunConfig, Selection, StartRequest, OpenWorkbookRequest
from app.runner import Runner
from app.storage import Storage, safe_id, write_json
from app.settings import Settings
from app.workbook import MAX_UPLOAD_BYTES, export_workbook, inspect_workbook, select_rows


class BatchService:
    def __init__(self, root, client=None, database=None):
        self.storage = Storage(root, database)
        self.runner = Runner(self.storage, client)
        if database:
            for status in ("running", "stopping"):
                for archived in (False, True):
                    for job in database.list_jobs(status=status, archived=archived, limit=1000)["items"]:
                        self.storage.load(job["job_id"], recover=True)

    def upload(self, filename, source, start_row=2):
        if (not filename or len(filename) > 200 or "/" in filename or "\\" in filename
                or any(ord(char) < 32 for char in filename)
                or not filename.lower().endswith(".xlsx")):
            raise ValueError("请选择文件名有效的 .xlsx 文件")
        overview = inspect_workbook(source, start_row)
        upload_id = uuid4().hex
        directory = self.storage.root / "uploads" / upload_id
        directory.mkdir(parents=True)
        (directory / "source.xlsx").write_bytes(source)
        write_json(directory / "info.json", {"filename": filename})
        return {"upload_id": upload_id, "filename": filename, "sheets": overview}

    def open_workbook(self, path, start_row=2):
        if self.runner.active:
            raise ValueError("已有批次正在执行，请完成后再加载文件")
        target = Path(path.strip().strip('"'))
        if not target.is_absolute() or target.suffix.lower() != ".xlsx":
            raise ValueError("请输入原始 .xlsx 的本地绝对路径")
        target = target.resolve(strict=True)
        if not target.is_file() or target.stat().st_size > MAX_UPLOAD_BYTES:
            raise ValueError("请选择不超过 20 MB 的 .xlsx 文件")
        source = target.read_bytes()
        opened = self.upload(target.name, source, start_row)
        directory = self.storage.root / "uploads" / opened["upload_id"]
        write_json(directory / "info.json", {"filename": target.name, "source_path": str(target)})
        return {**opened, "source_path": str(target)}

    def _upload(self, upload_id):
        directory = self.storage.root / "uploads" / safe_id(upload_id)
        source = (directory / "source.xlsx").read_bytes()
        metadata = json.loads((directory / "info.json").read_text(encoding="utf-8"))
        return source, metadata["filename"]

    def preview(self, selection: Selection):
        source, _ = self._upload(selection.upload_id)
        rows = select_rows(source, selection.sheets, selection.start_row, selection.overwrite, CURRENT_OUTPUT_FORMAT)
        return {"total": len(rows), "counts": dict(Counter(row.status for row in rows)),
                "items": [row.to_dict(False) for row in rows[:100]], "preview_limit": 100}

    def start(self, request: StartRequest):
        if self.runner.active:
            raise ValueError("已有批次正在执行")
        source, filename = self._upload(request.upload_id)
        rows = select_rows(source, request.sheets, request.start_row, request.overwrite, CURRENT_OUTPUT_FORMAT)
        metadata = json.loads((self.storage.root / "uploads" / safe_id(request.upload_id) /
                               "info.json").read_text(encoding="utf-8"))
        return self.runner.start(source, rows, request.config, filename, metadata.get("source_path"))

    def rows(self, job_id, sheet="", status="", query="", offset=0, limit=100):
        if offset < 0 or not 1 <= limit <= 200:
            raise ValueError("分页参数无效")
        _, rows = self.runner.get(job_id)
        query = query.casefold().strip()
        filtered = [row for row in rows
                    if (not sheet or row.sheet == sheet) and (not status or row.status == status)
                    and (not query or query in (row.question + "\n" + row.output + "\n" + row.error).casefold())]
        return {"total": len(filtered), "offset": offset, "limit": limit,
                "sheets": list(dict.fromkeys(row.sheet for row in rows)),
                "items": [row.to_dict(False) | {"output_length": len(row.output)}
                          for row in filtered[offset:offset + limit]]}

    def row(self, job_id, row_id):
        safe_id(row_id)
        _, rows = self.runner.get(job_id)
        for row in rows:
            if row.row_id == row_id:
                return row.to_dict()
        raise FileNotFoundError("记录不存在")

    def _finished(self, job_id):
        job, rows = self.runner.get(job_id)
        if job["status"] in {"running", "stopping"}:
            raise ValueError("任务正在执行，请完成或停止后下载")
        return job, rows

    def export(self, job_id):
        job, rows = self.runner.get(job_id)
        if job["status"] not in {"running", "stopping"}:
            self.storage.save_workbook(job_id, rows, write_source=False)
        return self.storage.result(job_id)

    def logs(self, job_id):
        job, rows = self._finished(job_id)
        output = BytesIO()
        with ZipFile(output, "w", ZIP_DEFLATED) as archive:
            archive.writestr("results.json", json.dumps(
                {"job": job, "rows": [row.to_dict() for row in rows]}, ensure_ascii=False, indent=2))
            for row in rows:
                archive.writestr(f"rows/{row.row_id}.txt", row.output.encode("utf-8"))
                archive.writestr(f"events/{row.row_id}.jsonl",
                                 self.storage.events(job_id, row.row_id))
        return output.getvalue()

    def history(self):
        jobs = self.storage.list_jobs()
        for job in jobs:
            if self.runner.job and self.runner.job["job_id"] == job["job_id"]:
                job["status"] = self.runner.job["status"]
        return jobs


def create_app(root=None, settings=None):
    settings = settings or Settings()
    root = Path(root) if root is not None else Path(os.getenv("BATCH_DATA_DIR", str(
        Path(__file__).resolve().parent.parent / "runtime")))
    root.mkdir(parents=True, exist_ok=True)
    database = Database(settings.database_url or "sqlite:///" + str((root / "batch.sqlite3").resolve()))
    if not database.has_admin():
        password = settings.admin_password or secrets.token_urlsafe(20)
        database.ensure_admin(password)
        if not settings.admin_password:
            credentials = root / "admin-login.txt"
            with open(credentials, "w", encoding="utf-8", opener=lambda path, flags: os.open(path, flags, 0o600)) as handle:
                handle.write("username=admin\npassword=" + password + "\n")
    settings.admin_password = ""
    service = BatchService(root, database=database)
    limiter = LoginLimiter()

    @asynccontextmanager
    async def lifespan(app):
        try:
            yield
        finally:
            if service.runner.active:
                service.runner.stop(service.runner.job["job_id"])
                try:
                    await asyncio.wait_for(asyncio.shield(service.runner.wait()), timeout=25)
                except TimeoutError:
                    service.runner.task.cancel()
                    await service.runner.wait()
            database.engine.dispose()

    app = FastAPI(title="Excel Batch Runner", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.service = service
    app.state.database = database
    app.state.settings = settings
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)

    @app.middleware("http")
    async def authenticate(request: Request, call_next):
        async def dispatch():
            protected = request.url.path.startswith("/api/") and request.url.path != "/api/auth/login"
            session = None
            if protected or request.url.path in {"/", "/login"}:
                session = await asyncio.to_thread(database.session, request.cookies.get(COOKIE_NAME, ""))
                request.state.session = session
                if protected and not session:
                    return JSONResponse({"detail": "请先登录"}, status_code=401)
            if request.method not in {"GET", "HEAD"}:
                origin = request.headers.get("origin")
                expected = f"{request.url.scheme}://{request.url.netloc}"
                if request.headers.get("x-local-request") != "1" or (origin and origin != expected):
                    return JSONResponse({"detail": "请通过本站页面操作"}, status_code=403)
                if protected and not hmac.compare_digest(request.headers.get("x-csrf-token", ""), session["csrf"]):
                    return JSONResponse({"detail": "登录校验已失效，请刷新页面"}, status_code=403)
            return await call_next(request)
        try:
            response = await dispatch()
        except SQLAlchemyError:
            response = JSONResponse({"detail": "数据库暂时不可用，请稍后重试"}, status_code=503)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["X-Frame-Options"] = "DENY"
        return response

    @app.exception_handler(SQLAlchemyError)
    async def database_failure(request, exc):
        return JSONResponse({"detail": "数据库暂时不可用，请稍后重试"}, status_code=503)

    @app.exception_handler(ValueError)
    async def invalid_request(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=400)

    @app.exception_handler(FileNotFoundError)
    async def missing(request, exc):
        return JSONResponse({"detail": "任务、文件或记录不存在"}, status_code=404)

    @app.exception_handler(OSError)
    async def storage_failure(request, exc):
        return JSONResponse({"detail": "文件读写失败，请检查服务器磁盘空间和目录权限"}, status_code=500)

    @app.exception_handler(RequestValidationError)
    async def validation_failure(request, exc):
        # FastAPI's default response includes the rejected input (possibly credentials).
        errors = [".".join(str(part) for part in error["loc"]) + ": " + error["msg"]
                  for error in exc.errors()]
        return JSONResponse({"detail": "；".join(errors)}, status_code=422)

    @app.get("/healthz")
    async def health():
        await asyncio.to_thread(database.healthy)
        return {"status": "ok"}

    @app.post("/api/auth/login")
    async def login(body: LoginRequest, request: Request):
        host = request.client.host if request.client else "unknown"
        if not limiter.allow(host):
            return JSONResponse({"detail": "登录尝试过多，请在 15 分钟后重试"}, status_code=429,
                                headers={"Retry-After": "900"})
        session = await asyncio.to_thread(database.login, body.username, body.password, settings.session_seconds)
        if not session:
            return JSONResponse({"detail": "账号或密码错误"}, status_code=401)
        limiter.clear(host)
        response = JSONResponse({"username": session["username"], "csrf": session["csrf"]})
        response.set_cookie(COOKIE_NAME, session["token"], max_age=settings.session_seconds,
                            httponly=True, secure=settings.cookie_secure, samesite="lax", path="/")
        return response

    @app.get("/api/auth/me")
    async def me(request: Request):
        return {"username": request.state.session["username"], "csrf": request.state.session["csrf"],
                "database": database.engine.dialect.name, "allow_local_paths": settings.allow_local_paths}

    @app.post("/api/auth/logout")
    async def logout(request: Request):
        await asyncio.to_thread(database.logout, request.cookies[COOKIE_NAME])
        response = JSONResponse({"ok": True})
        response.delete_cookie(COOKIE_NAME, path="/", secure=settings.cookie_secure, httponly=True, samesite="lax")
        return response

    @app.get("/api/defaults")
    async def defaults():
        return RunConfig().model_dump()

    @app.post("/api/uploads")
    async def upload(request: Request, start_row: int = Query(2, ge=1, le=1048576)):
        filename = unquote(request.headers.get("x-filename", ""), errors="strict")
        content = bytearray()
        async for chunk in request.stream():
            content.extend(chunk)
            if len(content) > MAX_UPLOAD_BYTES:
                raise ValueError("文件超过 20 MB")
        return await asyncio.to_thread(service.upload, filename, bytes(content), start_row)

    @app.post("/api/workbooks/open")
    async def open_workbook(request: OpenWorkbookRequest):
        if not settings.allow_local_paths:
            return JSONResponse({"detail": "服务器模式请上传 Excel 文件"}, status_code=403)
        return await asyncio.to_thread(service.open_workbook, request.path, request.start_row)

    @app.post("/api/preview")
    async def preview(selection: Selection):
        return await asyncio.to_thread(service.preview, selection)

    @app.post("/api/jobs")
    async def start(request: StartRequest):
        return service.start(request)

    @app.get("/api/jobs")
    async def history():
        return await asyncio.to_thread(service.history)

    @app.get("/api/history")
    async def managed_history(query: str = Query("", max_length=200), status: str = Query("", max_length=32),
                              archived: bool = False, offset: int = Query(0, ge=0),
                              limit: int = Query(20, ge=1, le=100)):
        return await asyncio.to_thread(database.list_jobs, query.strip(), status, archived, offset, limit)

    @app.patch("/api/jobs/{job_id}")
    async def edit_history(job_id: str, changes: HistoryEdit):
        safe_id(job_id)
        values = changes.model_dump(exclude_none=True)
        if "title" in values:
            values["title"] = values["title"].strip()
            if not values["title"] or any(ord(c) < 32 for c in values["title"]):
                raise ValueError("任务名称不能为空或包含控制字符")
        if not values:
            raise ValueError("请指定要修改的名称或归档状态")
        if values.get("archived") and service.runner.active and service.runner.job["job_id"] == job_id:
            raise ValueError("请等待任务完成后再归档")
        await asyncio.to_thread(database.edit_job, job_id, values)
        if service.runner.job and service.runner.job["job_id"] == job_id:
            service.runner.job.update(values)
        return {"ok": True}

    @app.get("/api/jobs/{job_id}")
    async def snapshot(job_id: str):
        return await asyncio.to_thread(service.runner.snapshot, job_id)

    @app.get("/api/jobs/{job_id}/rows")
    async def rows(job_id: str, sheet: str = "", status: str = "", query: str = "",
                   offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=200)):
        return await asyncio.to_thread(service.rows, job_id, sheet, status, query, offset, limit)

    @app.get("/api/jobs/{job_id}/rows/{row_id}")
    async def row(job_id: str, row_id: str):
        return await asyncio.to_thread(service.row, job_id, row_id)

    @app.get("/api/jobs/{job_id}/source")
    async def source(job_id: str):
        await asyncio.to_thread(service.runner.get, job_id)
        content = await asyncio.to_thread(service.storage.source, job_id)
        return Response(content, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f'attachment; filename="source-{safe_id(job_id)}.xlsx"'})

    @app.post("/api/jobs/{job_id}/stop")
    async def stop(job_id: str):
        service.runner.stop(job_id)
        return service.runner.snapshot(job_id)

    @app.get("/api/jobs/{job_id}/export")
    async def export(job_id: str):
        content = await asyncio.to_thread(service.export, job_id)
        return Response(content, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f'attachment; filename="batch-{safe_id(job_id)}.xlsx"'})

    @app.get("/api/jobs/{job_id}/logs")
    async def logs(job_id: str):
        content = await asyncio.to_thread(service.logs, job_id)
        return Response(content, media_type="application/zip",
                        headers={"Content-Disposition": f'attachment; filename="logs-{safe_id(job_id)}.zip"'})

    static = Path(__file__).resolve().parent / "static"

    @app.get("/")
    async def index(request: Request):
        if not request.state.session:
            return RedirectResponse("/login", status_code=303)
        return FileResponse(static / "index.html")

    @app.get("/login")
    async def login_page(request: Request):
        if request.state.session:
            return RedirectResponse("/", status_code=303)
        return FileResponse(static / "login.html")

    app.mount("/static", StaticFiles(directory=static), name="static")
    return app
