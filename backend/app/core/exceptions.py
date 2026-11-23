"""
FastAPI 全局异常处理器
"""
import logging
import traceback

from fastapi import Request
from fastapi.exceptions import HTTPException, RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError, OperationalError, TimeoutError as SQLAlchemyTimeoutError
from starlette.exceptions import HTTPException as StarletteHTTPException

from .response import HTTP_STATUS_TO_CODE, ResponseCode

logger = logging.getLogger(__name__)


def chatbi_error(request, status, code, message, headers=None):
    if request.url.path == "/api/service" or request.url.path.startswith("/api/service/"):
        return JSONResponse({"status": status, "code": code, "message": message}, status_code=status, headers=headers)
    return None


async def http_exception_handler(request: Request, exc: HTTPException):
    """HTTPException → 统一响应格式"""
    service_codes = {400: "invalid_param", 401: "unauthorized", 403: "forbidden", 404: "not_found",
                  405: "method_not_allowed", 429: "too_many_requests", 500: "internal_server_error",
                  503: "service_unavailable", 504: "timeout"}
    response = chatbi_error(request, exc.status_code, service_codes.get(exc.status_code, "http_error"), str(exc.detail), exc.headers)
    if response is not None:
        return response
    code = HTTP_STATUS_TO_CODE.get(exc.status_code, "ERROR")
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": code, "message": str(exc.detail), "data": None},
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """请求验证异常 → Pydantic 校验错误"""
    response = chatbi_error(request, 400, "invalid_param", "请求字段不符合接口约定")
    if response is not None:
        return response
    logger.warning("422 validation errors on %s %s: %s", request.method, request.url.path, exc.errors())
    return JSONResponse(
        status_code=422,
        content={
            "code": ResponseCode.VALIDATION_ERROR,
            "message": "请求参数校验失败",
            "data": exc.errors(),
        },
    )


async def sqlalchemy_timeout_handler(request: Request, exc: SQLAlchemyTimeoutError):
    """数据库连接池等待超时"""
    logger.warning("Database pool timeout on %s %s: %s", request.method, request.url.path, exc)
    response = chatbi_error(request, 503, "service_unavailable", "数据库繁忙，请稍后重试")
    if response is not None:
        return response
    return JSONResponse(
        status_code=503,
        content={"code": "DB_POOL_TIMEOUT", "message": "数据库繁忙，请稍后重试", "data": None},
    )


async def sqlalchemy_operational_error_handler(request: Request, exc: OperationalError):
    """数据库连接/网络层异常"""
    logger.warning("Database operational error on %s %s: %s", request.method, request.url.path, exc)
    response = chatbi_error(request, 503, "service_unavailable", "数据库暂时不可用，请稍后重试")
    if response is not None:
        return response
    return JSONResponse(
        status_code=503,
        content={"code": "DB_UNAVAILABLE", "message": "数据库暂时不可用，请稍后重试", "data": None},
    )


async def sqlalchemy_dbapi_error_handler(request: Request, exc: DBAPIError):
    """数据库驱动异常兜底"""
    logger.warning("Database API error on %s %s: %s", request.method, request.url.path, exc)
    response = chatbi_error(request, 503 if getattr(exc, "connection_invalidated", False) else 500,
                           "service_unavailable" if getattr(exc, "connection_invalidated", False) else "internal_server_error",
                           "数据库访问失败，请稍后重试")
    if response is not None:
        return response
    return JSONResponse(
        status_code=503 if getattr(exc, "connection_invalidated", False) else 500,
        content={"code": "DB_ERROR", "message": "数据库访问失败，请稍后重试", "data": None},
    )


async def generic_exception_handler(request: Request, exc: Exception):
    """通用异常处理器 - 捕获所有未处理异常"""
    logger.error(
        "Unhandled exception on %s %s: %s\n%s",
        request.method, request.url.path, exc, traceback.format_exc(),
    )
    response = chatbi_error(request, 500, "internal_server_error", "服务器内部错误")
    if response is not None:
        return response
    return JSONResponse(
        status_code=500,
        content={"code": "INTERNAL_ERROR", "message": "服务器内部错误", "data": None},
    )


def register_exception_handlers(app):
    """将所有异常处理器注册到 FastAPI app"""
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(SQLAlchemyTimeoutError, sqlalchemy_timeout_handler)
    app.add_exception_handler(OperationalError, sqlalchemy_operational_error_handler)
    app.add_exception_handler(DBAPIError, sqlalchemy_dbapi_error_handler)
    app.add_exception_handler(Exception, generic_exception_handler)
