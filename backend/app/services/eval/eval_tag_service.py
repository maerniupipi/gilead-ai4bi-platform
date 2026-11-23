"""
评测标签服务层
"""
from typing import List, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ...repositories.eval import eval_tag_repo
from ...schemas.eval import EvalTagCreate, EvalTagUpdate, EvalTagResponse


def list_tags_service(db: Session, space_id: int) -> List[EvalTagResponse]:
    tags = eval_tag_repo.list_tags(db, space_id)
    return [EvalTagResponse.model_validate(t) for t in tags]


def create_tag_service(db: Session, space_id: int, data: EvalTagCreate) -> EvalTagResponse:
    existing = eval_tag_repo.get_tag_by_name(db, space_id, data.name)
    if existing:
        raise HTTPException(status_code=400, detail="标签名称已存在")
    tag = eval_tag_repo.create_tag(db, space_id, data.name, data.color)
    db.commit()
    db.refresh(tag)
    return EvalTagResponse.model_validate(tag)


def update_tag_service(
    db: Session, tag_id: int, space_id: int, data: EvalTagUpdate
) -> EvalTagResponse:
    tag = eval_tag_repo.update_tag(db, tag_id, space_id, data.name, data.color)
    if not tag:
        raise HTTPException(status_code=404, detail="标签不存在")
    db.commit()
    db.refresh(tag)
    return EvalTagResponse.model_validate(tag)


def delete_tag_service(db: Session, tag_id: int, space_id: int) -> dict:
    ok = eval_tag_repo.delete_tag(db, tag_id, space_id)
    if not ok:
        raise HTTPException(status_code=404, detail="标签不存在")
    db.commit()
    return {"ok": True}
