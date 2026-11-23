"""评测配置路由"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...core.database import get_db
from ...repositories.eval import eval_config_repo

router = APIRouter(tags=["评测配置"])


@router.get("/eval/configs")
def list_configs(db: Session = Depends(get_db)):
    """列出所有评测配置"""
    rows = eval_config_repo.list_all(db)
    return [
        {"key": r.key, "value": r.value, "description": r.description, "updated_at": str(r.updated_at) if r.updated_at else None}
        for r in rows
    ]


@router.put("/eval/configs/{key}")
def update_config(key: str, body: dict, db: Session = Depends(get_db)):
    """更新评测配置"""
    value = body.get("value")
    if value is None:
        return {"ok": False, "detail": "value 不能为空"}
    eval_config_repo.set_value(db, key, str(value), body.get("description"))
    db.commit()
    return {"ok": True, "key": key, "value": value}
