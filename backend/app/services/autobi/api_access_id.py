"""AutoBI 对外 API 调用主键：10 位字母数字，库内唯一。"""
from __future__ import annotations

import secrets
import string

from sqlalchemy.orm import Session

from ...models.autobi_project import AutobiProject

_ALPHANUM = string.ascii_letters + string.digits


def generate_api_access_id() -> str:
    return "".join(secrets.choice(_ALPHANUM) for _ in range(10))


def allocate_unique_api_access_id(db: Session) -> str:
    for _ in range(48):
        candidate = generate_api_access_id()
        taken = (
            db.query(AutobiProject)
            .filter(AutobiProject.api_access_id == candidate)
            .first()
        )
        if taken is None:
            return candidate
    raise RuntimeError("无法分配唯一的 api_access_id")


def ensure_row_has_api_access_id(db: Session, row: AutobiProject) -> bool:
    """若缺失则写入并返回是否发生修改（调用方负责 commit）。"""
    if row.api_access_id:
        return False
    row.api_access_id = allocate_unique_api_access_id(db)
    return True
