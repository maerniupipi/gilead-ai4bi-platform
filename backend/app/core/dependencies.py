"""
通用 FastAPI 依赖项
"""
from fastapi import Header, HTTPException

from .database import get_db


def get_current_user_id(
    x_user_id: int = Header(default=1, alias="X-User-Id")
) -> int:
    """
    统一的用户ID获取方式。

    优先从 X-User-Id Header 获取，当前端未传时默认为 1（占位值）。
    在生产环境中，应验证用户是否存在并返回真实用户ID。
    """
    return x_user_id


def require_auth(
    x_user_id: int = Header(default=None, alias="X-User-Id")
) -> int:
    """
    需要认证的依赖项。如果未提供用户ID则抛出异常。
    """
    if x_user_id is None:
        raise HTTPException(status_code=401, detail="需要登录")
    return x_user_id
