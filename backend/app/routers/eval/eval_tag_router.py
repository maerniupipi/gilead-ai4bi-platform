from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...core.database import get_db
from ...schemas.eval import EvalTagCreate, EvalTagUpdate, EvalTagResponse
from ...services.eval import eval_tag_service

router = APIRouter(prefix="/spaces/{space_id}/eval/tags", tags=["评测标签"])


@router.get("", response_model=List[EvalTagResponse])
def list_tags(space_id: int, db: Session = Depends(get_db)):
    """获取标签列表"""
    return eval_tag_service.list_tags_service(db, space_id)


@router.post("", response_model=EvalTagResponse)
def create_tag(space_id: int, data: EvalTagCreate, db: Session = Depends(get_db)):
    """创建标签"""
    return eval_tag_service.create_tag_service(db, space_id, data)


@router.put("/{tag_id}", response_model=EvalTagResponse)
def update_tag(space_id: int, tag_id: int, data: EvalTagUpdate, db: Session = Depends(get_db)):
    """更新标签"""
    return eval_tag_service.update_tag_service(db, tag_id, space_id, data)


@router.delete("/{tag_id}")
def delete_tag(space_id: int, tag_id: int, db: Session = Depends(get_db)):
    """删除标签"""
    return eval_tag_service.delete_tag_service(db, tag_id, space_id)
