"""
通用 HTTP 异常辅助函数
减少每个 service 文件中重复的 `from fastapi import HTTPException` 导入
"""
from fastapi import HTTPException


def http_error(status_code: int, detail: str) -> HTTPException:
    """创建 HTTP 异常"""
    return HTTPException(status_code=status_code, detail=detail)


def not_found(resource: str) -> HTTPException:
    """404 未找到异常"""
    return HTTPException(status_code=404, detail=f"{resource}不存在")


def forbidden(detail: str = "无权访问该资源") -> HTTPException:
    """403 禁止访问异常"""
    return HTTPException(status_code=403, detail=detail)


def bad_request(detail: str) -> HTTPException:
    """400 错误请求异常"""
    return HTTPException(status_code=400, detail=detail)


def conflict(detail: str) -> HTTPException:
    """409 资源冲突异常"""
    return HTTPException(status_code=409, detail=detail)
