"""
FastAPI 中间件：统一响应包装、审计日志、CORS
"""
import json
import logging
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from os import getenv

from starlette.types import ASGIApp, Receive, Scope, Send

from .response import ResponseCode

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 审计日志配置
# ---------------------------------------------------------------------------

_audit_db_enabled = (getenv("AUDIT_LOG_DB_ENABLED") or "true").strip().lower() not in {"0", "false", "no", "off"}


def _env_int(name: str, default: int, minimum: int | None = None) -> int:
    raw = (getenv(name) or "").strip()
    try:
        value = int(raw) if raw else default
    except ValueError:
        return default
    if minimum is not None:
        return max(minimum, value)
    return value


_audit_executor = ThreadPoolExecutor(
    max_workers=_env_int("AUDIT_LOG_DB_MAX_WORKERS", 4, 1),
    thread_name_prefix="audit-db",
)
_audit_slots = threading.BoundedSemaphore(_env_int("AUDIT_LOG_DB_QUEUE_LIMIT", 200, 1))


# ---------------------------------------------------------------------------
# 审计日志持久化
# ---------------------------------------------------------------------------

def _extract_resource_type(path: str) -> str:
    """从URL路径中提取资源类型"""
    if not path.startswith("/api/"):
        return "unknown"
    parts = path[5:].split("/")
    if parts and parts[0]:
        return parts[0].replace("-", "_")
    return "unknown"


def _persist_audit_log(
    user_id: int | None,
    username: str | None,
    action: str,
    resource_type: str,
    client_ip: str,
    method: str,
    path: str,
    space_id: int | None,
    status_code: int | None,
    duration_ms: int | None,
    request_body_str: str | None,
    response_body_str: str | None,
    error_message: str | None,
) -> None:
    """在独立线程中写入审计日志到数据库"""
    from .database import SessionLocal

    db = SessionLocal()
    try:
        from ..services.audit_log.service import AuditLogService

        AuditLogService.create_log(
            db=db,
            user_id=user_id,
            username=username,
            action=action,
            resource_type=resource_type,
            ip_address=client_ip,
            method=method,
            path=path,
            space_id=space_id,
            status_code=status_code,
            duration_ms=duration_ms,
            request_body=request_body_str,
            response_body=response_body_str,
            error_message=error_message,
        )
    except Exception as e:
        logger.error(f"Failed to persist audit log to DB: {e}\n{traceback.format_exc()}")
    finally:
        db.close()


def _redact_chatbi_key_data(value):
    if isinstance(value, dict):
        return {key: "[REDACTED]" if key.lower() in {"api_key", "password", "secret_key", "access_key", "token", "access_token", "authorization"} else _redact_chatbi_key_data(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_chatbi_key_data(item) for item in value]
    return value


def _schedule_db_audit_log(
    *,
    user_id_str: str,
    username: str | None,
    method: str,
    path: str,
    client_ip: str,
    space_id_str: str,
    status_code: int | None,
    duration_ms: int | None,
    request_body: dict | None = None,
    response_body_str: str | None = None,
    error_message: str | None = None,
) -> None:
    """调度审计日志异步写入数据库（fire-and-forget，使用独立线程避免事件循环干扰）"""
    if not _audit_db_enabled:
        return
    if path.startswith(("/api/chatbi/keys", "/api/users", "/api/auth/", "/api/oss-configs", "/api/es-configs", "/api/data_source", "/api/model-providers")):
        request_body = _redact_chatbi_key_data(request_body)
        if response_body_str:
            try:
                response_body_str = json.dumps(_redact_chatbi_key_data(json.loads(response_body_str)), ensure_ascii=False)
            except (ValueError, TypeError):
                response_body_str = "[REDACTED]"
    try:
        user_id = int(user_id_str) if user_id_str and user_id_str != "anonymous" else None
        space_id = int(space_id_str) if space_id_str and space_id_str.isdigit() else None
        _METHOD_TO_ACTION = {"GET": "view", "POST": "create", "PUT": "update", "DELETE": "delete", "PATCH": "update"}
        action = _METHOD_TO_ACTION.get(method, method.lower())
        resource_type = _extract_resource_type(path)
        request_body_str = None
        if request_body:
            request_body_str = json.dumps(request_body, ensure_ascii=False)[:5000]

        if not _audit_slots.acquire(blocking=False):
            logger.warning("Audit DB queue is full, dropped one audit log")
            return

        def _run() -> None:
            try:
                _persist_audit_log(
                    user_id=user_id,
                    username=username,
                    action=action,
                    resource_type=resource_type,
                    client_ip=client_ip,
                    method=method,
                    path=path,
                    space_id=space_id,
                    status_code=status_code,
                    duration_ms=duration_ms,
                    request_body_str=request_body_str,
                    response_body_str=response_body_str,
                    error_message=error_message,
                )
            finally:
                _audit_slots.release()

        _audit_executor.submit(_run)
    except Exception as e:
        logger.error(f"Failed to schedule audit log: {e}\n{traceback.format_exc()}")


# ---------------------------------------------------------------------------
# 响应包装中间件
# ---------------------------------------------------------------------------

class ResponseEnvelopeMiddleware:
    """
    统一响应包装中间件 + 审计日志（纯 ASGI 实现，避免 BaseHTTPMiddleware 的 body 消费 bug）

    将所有成功响应包装成 {code, message, data} 格式，同时记录审计日志
    错误响应由异常处理器处理，已包含code字段则直接透传
    排除Swagger/OpenAPI相关路径，确保API文档正常显示
    """
    EXCLUDED_PATHS = {"/docs", "/openapi.json", "/redoc", "/health", "/api/service/"}

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        method = scope.get("method", "GET")
        _is_write_op = method in ("POST", "PUT", "PATCH", "DELETE")

        # 提取请求头信息
        headers = dict(scope.get("headers", []))
        user_id_str = headers.get(b"x-user-id", b"anonymous").decode()
        username_raw = headers.get(b"x-username")
        username = username_raw.decode() if username_raw else None
        client = scope.get("client", ("unknown", 0))
        client_ip = client[0] if client else "unknown"
        qs = scope.get("query_string", b"").decode()
        space_id_str = "-"
        for part in qs.split("&"):
            if part.startswith("space_id="):
                space_id_str = part.split("=", 1)[1]
                break

        # 读取并缓存请求体，使下游 handler 可以再次读取
        # multipart 请求不做缓存（会破坏 chunk 边界导致文件损坏）
        content_type_req = headers.get(b"content-type", b"").decode()
        is_multipart = "multipart/" in content_type_req
        # body_chunks: list of (chunk_bytes, more_body_flag) tuples
        body_chunks: list[tuple[bytes, bool]] = []
        request_body_dict = None

        async def _receive():
            nonlocal request_body_dict
            if is_multipart:
                # multipart 直接透传，不缓存
                return await receive()
            if body_chunks:
                # 回放已缓存的 chunk，保留原始的 more_body 标记
                chunk, more = body_chunks.pop(0)
                return {"type": "http.request", "body": chunk, "more_body": more or len(body_chunks) > 0}
            # 首次收取：一次性读完所有 body chunk 再回放
            while True:
                msg = await receive()
                if msg.get("type") != "http.request":
                    return msg
                chunk = msg.get("body", b"")
                more = msg.get("more_body", False)
                body_chunks.append((chunk, more))
                if not more:
                    break
            # 尝试解析完整 body 用于审计日志
            if body_chunks and "application/json" in content_type_req:
                try:
                    full_body = b"".join(c for c, _ in body_chunks)
                    request_body_dict = json.loads(full_body)
                    if (scope.get("path", "").startswith("/api/chatbi/keys") or scope.get("path") == "/api/users/login") and isinstance(request_body_dict, dict):
                        # Imported service credentials must never enter the audit store.
                        request_body_dict = _redact_chatbi_key_data(request_body_dict)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    pass
            chunk, more = body_chunks.pop(0)
            return {"type": "http.request", "body": chunk, "more_body": more or len(body_chunks) > 0}

        _audit_start = time.time()

        # 收集响应
        resp_status = [200]
        resp_headers: list[tuple[bytes, bytes]] = []
        resp_body_chunks: list[bytes] = []
        passthrough_response = [False]

        async def _send(message):
            if message["type"] == "http.response.start":
                resp_status[0] = message["status"]
                resp_headers.clear()
                resp_headers.extend(message.get("headers", []))
                content_type = ""
                for hk, hv in resp_headers:
                    if hk == b"content-type":
                        content_type = hv.decode()
                        break
                if "application/json" not in content_type:
                    passthrough_response[0] = True
                    await send(message)
            elif message["type"] == "http.response.body":
                if passthrough_response[0]:
                    await send(message)
                else:
                    resp_body_chunks.append(message.get("body", b""))

        await self.app(scope, _receive, _send)

        _audit_duration = time.time() - _audit_start
        _audit_duration_ms = int(_audit_duration * 1000)
        status_code = resp_status[0]

        # 审计文件日志（仅增改删操作）
        audit_msg = (
            f"user={user_id_str} | "
            f"ip={client_ip} | "
            f"method={method} | "
            f"path={path} | "
            f"space={space_id_str} | "
            f"status={status_code} | "
            f"duration={_audit_duration:.3f}s"
        )
        if _is_write_op:
            from .logging_config import get_audit_logger
            get_audit_logger().info(audit_msg)
            if status_code >= 400:
                logger.warning("API错误: %s", audit_msg)

        if passthrough_response[0]:
            if _is_write_op:
                _schedule_db_audit_log(
                    user_id_str=user_id_str, username=username, method=method,
                    path=path, client_ip=client_ip, space_id_str=space_id_str,
                    status_code=status_code, duration_ms=_audit_duration_ms,
                    request_body=request_body_dict,
                )
            return

        # 排除路径直接透传
        if any(path.startswith(excluded) for excluded in self.EXCLUDED_PATHS):
            if _is_write_op:
                _schedule_db_audit_log(
                    user_id_str=user_id_str, username=username, method=method,
                    path=path, client_ip=client_ip, space_id_str=space_id_str,
                    status_code=status_code, duration_ms=_audit_duration_ms,
                    request_body=request_body_dict,
                )
            await send({"type": "http.response.start", "status": status_code, "headers": resp_headers})
            for chunk in resp_body_chunks:
                await send({"type": "http.response.body", "body": chunk})
            return

        # 非 JSON 响应直接透传
        ct = ""
        for hk, hv in resp_headers:
            if hk == b"content-type":
                ct = hv.decode()
                break
        if "application/json" not in ct:
            if _is_write_op:
                _schedule_db_audit_log(
                    user_id_str=user_id_str, username=username, method=method,
                    path=path, client_ip=client_ip, space_id_str=space_id_str,
                    status_code=status_code, duration_ms=_audit_duration_ms,
                    request_body=request_body_dict,
                )
            await send({"type": "http.response.start", "status": status_code, "headers": resp_headers})
            for chunk in resp_body_chunks:
                await send({"type": "http.response.body", "body": chunk})
            return

        body = b"".join(resp_body_chunks)
        try:
            data = json.loads(body)
        except (json.JSONDecodeError, ValueError):
            if _is_write_op:
                _schedule_db_audit_log(
                    user_id_str=user_id_str, username=username, method=method,
                    path=path, client_ip=client_ip, space_id_str=space_id_str,
                    status_code=status_code, duration_ms=_audit_duration_ms,
                    request_body=request_body_dict,
                )
            await send({"type": "http.response.start", "status": status_code, "headers": resp_headers})
            await send({"type": "http.response.body", "body": body})
            return

        response_body_str = json.dumps(data, ensure_ascii=False)[:5000]
        error_message = None
        if status_code >= 400 and isinstance(data, dict):
            error_message = data.get("message") or data.get("detail") or str(data)

        if _is_write_op:
            _schedule_db_audit_log(
                user_id_str=user_id_str, username=username, method=method,
                path=path, client_ip=client_ip, space_id_str=space_id_str,
                status_code=status_code, duration_ms=_audit_duration_ms,
                request_body=request_body_dict,
                response_body_str=response_body_str,
                error_message=error_message,
            )

        # 已包含 code 字段的错误响应直接透传
        # JSON wrapping must preserve HttpOnly session cookies issued by login.
        cookie_headers = [(key, value) for key, value in resp_headers if key.lower() in {b"set-cookie", b"cache-control"}]
        if status_code >= 400 and isinstance(data, dict) and "code" in data:
            out = json.dumps(data, ensure_ascii=False).encode()
            await send({"type": "http.response.start", "status": status_code, "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(out)).encode()),
            ] + cookie_headers})
            await send({"type": "http.response.body", "body": out})
            return

        # 包装成功响应
        wrapped = {"code": ResponseCode.SUCCESS, "message": "success", "data": data}
        out = json.dumps(wrapped, ensure_ascii=False).encode()
        await send({"type": "http.response.start", "status": status_code, "headers": [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(out)).encode()),
        ] + cookie_headers})
        await send({"type": "http.response.body", "body": out})


def get_audit_executor() -> ThreadPoolExecutor:
    """供 lifespan 关闭时调用"""
    return _audit_executor
