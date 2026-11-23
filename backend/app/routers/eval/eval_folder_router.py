from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ...core.database import get_db
from ...schemas.eval import (
    EvalFolderCreate, EvalFolderUpdate, EvalFolderResponse, EvalFolderTree,
)
from ...services.eval import eval_folder_service

router = APIRouter(prefix="/spaces/{space_id}/eval/folders", tags=["评测文件夹"])


@router.get("", response_model=list)
def list_folders(space_id: int, db: Session = Depends(get_db)):
    """获取文件夹列表（树形结构）"""
    return eval_folder_service.list_folders_service(db, space_id)


@router.post("", response_model=EvalFolderResponse)
def create_folder(space_id: int, data: EvalFolderCreate, db: Session = Depends(get_db)):
    """创建文件夹"""
    return eval_folder_service.create_folder_service(db, space_id, data.model_dump())


@router.put("/{folder_id}", response_model=EvalFolderResponse)
def update_folder(space_id: int, folder_id: int, data: EvalFolderUpdate, db: Session = Depends(get_db)):
    """更新文件夹"""
    return eval_folder_service.update_folder_service(db, folder_id, space_id, data.model_dump(exclude_unset=True))


@router.delete("/{folder_id}")
def delete_folder(space_id: int, folder_id: int, db: Session = Depends(get_db)):
    """删除文件夹"""
    return eval_folder_service.delete_folder_service(db, folder_id, space_id)


@router.post("/{folder_id}/move", response_model=list)
def move_folder(space_id: int, folder_id: int, data: dict, db: Session = Depends(get_db)):
    """移动文件夹（上移/下移）"""
    direction = data.get("direction")
    return eval_folder_service.move_folder_service(db, folder_id, direction, space_id)
