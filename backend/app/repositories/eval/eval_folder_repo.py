"""评测文件夹数据访问层"""
from typing import List, Optional

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from ...models.eval import EvalFolder, EvalSuite, EvalCase


def list_folders(db: Session, space_id: int) -> List[EvalFolder]:
    """列出空间下所有文件夹，按 sort_order 排序"""
    return (
        db.query(EvalFolder)
        .filter(EvalFolder.space_id == space_id)
        .order_by(EvalFolder.sort_order.asc(), EvalFolder.id.asc())
        .all()
    )


def get_folder(db: Session, folder_id: int, space_id: int = None) -> Optional[EvalFolder]:
    """获取单个文件夹"""
    q = db.query(EvalFolder).filter(EvalFolder.id == folder_id)
    if space_id is not None:
        q = q.filter(EvalFolder.space_id == space_id)
    return q.first()


def create_folder(
    db: Session,
    space_id: int,
    name: str,
    description: str = None,
    parent_id: int = None,
    sort_order: int = 0,
) -> EvalFolder:
    """创建文件夹"""
    folder = EvalFolder(
        space_id=space_id,
        name=name.strip(),
        description=description,
        parent_id=parent_id,
        sort_order=sort_order,
        is_system=False,
    )
    db.add(folder)
    db.flush()
    return folder


def update_folder(db: Session, folder_id: int, space_id: int, **kwargs) -> Optional[EvalFolder]:
    """更新文件夹"""
    folder = get_folder(db, folder_id, space_id)
    if folder is None:
        return None
    for key, value in kwargs.items():
        if value is not None:
            setattr(folder, key, value)
    db.flush()
    return folder


def delete_folder(db: Session, folder_id: int, space_id: int) -> bool:
    """删除文件夹（若有子文件夹或评测集则拒绝删除）"""
    folder = get_folder(db, folder_id, space_id)
    if folder is None:
        return False

    # 检查是否有子文件夹
    child_count = (
        db.query(func.count(EvalFolder.id))
        .filter(EvalFolder.parent_id == folder_id)
        .scalar()
    )
    if child_count and child_count > 0:
        raise HTTPException(status_code=400, detail="该文件夹下存在子文件夹，无法删除")

    # 检查是否有关联评测集
    suite_count = (
        db.query(func.count(EvalSuite.id))
        .filter(EvalSuite.folder_id == folder_id)
        .scalar()
    )
    if suite_count and suite_count > 0:
        raise HTTPException(status_code=400, detail="该文件夹下存在评测集，无法删除")

    db.delete(folder)
    db.flush()
    return True


def next_sort_order(db: Session, space_id: int) -> int:
    """获取下一个排序序号"""
    m = (
        db.query(func.max(EvalFolder.sort_order))
        .filter(EvalFolder.space_id == space_id)
        .scalar()
    )
    return int(m or -1) + 1
