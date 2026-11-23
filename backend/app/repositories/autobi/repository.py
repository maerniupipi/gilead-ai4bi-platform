from typing import List, Optional, Dict, Any

from sqlalchemy.orm import Session

from ...models.autobi_folder import AutobiFolder
from ...models.autobi_project import AutobiProject


def autobi_folder_to_dict(row: AutobiFolder) -> Dict[str, Any]:
    """将 AutobiFolder 转为字典"""
    return {
        "id": row.id,
        "name": row.name,
        "sort_order": int(row.sort_order or 0),
        "is_system": bool(row.is_system),
        "created_at": row.created_at,
    }


def list_autobi_folders(db: Session, space_id: int = None) -> List[AutobiFolder]:
    query = db.query(AutobiFolder)
    if space_id is not None:
        query = query.filter(AutobiFolder.space_id == space_id)
    return query.order_by(AutobiFolder.sort_order.asc(), AutobiFolder.id.asc()).all()


def next_folder_sort_order(db: Session) -> int:
    from sqlalchemy import func

    m = db.query(func.max(AutobiFolder.sort_order)).scalar()
    return int(m or -1) + 1


def get_autobi_folder(db: Session, folder_id: int, space_id: int = None) -> Optional[AutobiFolder]:
    query = db.query(AutobiFolder).filter(AutobiFolder.id == folder_id)
    if space_id is not None:
        query = query.filter(AutobiFolder.space_id == space_id)
    return query.first()


def create_autobi_folder(db: Session, name: str, sort_order: int, space_id: int = None) -> AutobiFolder:
    row = AutobiFolder(name=name.strip(), sort_order=sort_order, is_system=False, space_id=space_id)
    db.add(row)
    db.flush()
    return row


def delete_autobi_folder_row(db: Session, row: AutobiFolder) -> None:
    db.delete(row)


def reassign_folder_for_projects(db: Session, from_folder_id: int, to_folder_id: int) -> int:
    """将项目从 from 挪到 to，返回更新行数"""
    q = (
        db.query(AutobiProject)
        .filter(AutobiProject.folder_id == from_folder_id)
        .all()
    )
    n = 0
    for p in q:
        p.folder_id = to_folder_id
        n += 1
    if n:
        db.flush()
    return n


def list_autobi_projects_active(
    db: Session, skip: int = 0, limit: int = 200, folder_id: Optional[int] = None, space_id: int = None
) -> List[AutobiProject]:
    q = db.query(AutobiProject).filter(AutobiProject.is_deleted == False)
    if folder_id is not None:
        q = q.filter(AutobiProject.folder_id == folder_id)
    if space_id is not None:
        q = q.filter(AutobiProject.space_id == space_id)
    return q.order_by(AutobiProject.id.desc()).offset(skip).limit(limit).all()


def get_autobi_project_active(db: Session, project_id: int, space_id: int = None) -> Optional[AutobiProject]:
    query = db.query(AutobiProject).filter(
        AutobiProject.id == project_id, AutobiProject.is_deleted == False
    )
    if space_id is not None:
        query = query.filter(AutobiProject.space_id == space_id)
    return query.first()


def get_autobi_project_by_api_access_id(db: Session, api_access_id: str, space_id: int = None) -> Optional[AutobiProject]:
    if not (api_access_id or "").strip():
        return None
    query = db.query(AutobiProject).filter(
        AutobiProject.api_access_id == api_access_id.strip(),
        AutobiProject.is_deleted == False,
    )
    if space_id is not None:
        query = query.filter(AutobiProject.space_id == space_id)
    return query.first()


def create_autobi_project(
    db: Session,
    name: str,
    description: Optional[str],
    config_json_str: str,
    kb_id: Optional[int],
    api_access_id: str,
    folder_id: int,
    space_id: int = None,
):
    row = AutobiProject(
        name=name,
        description=description,
        knowledge_base_id=kb_id,
        config_json=config_json_str,
        api_access_id=api_access_id,
        folder_id=folder_id,
        space_id=space_id,
    )
    db.add(row)
    return row


def apply_autobi_project_update(db: Session, row: AutobiProject, **kwargs):
    for k, v in kwargs.items():
        if v is not None or k in ("description", "knowledge_base_id"):
            setattr(row, k, v)
    return row


def soft_delete_autobi_project(db: Session, row: AutobiProject):
    db.delete(row)
    return row


def get_autobi_projects_by_knowledge_base(db: Session, knowledge_base_id: int, space_id: int = None) -> List[AutobiProject]:
    """获取引用指定知识库的所有AutoBI项目"""
    query = db.query(AutobiProject).filter(
        AutobiProject.knowledge_base_id == knowledge_base_id,
        AutobiProject.is_deleted == False
    )
    if space_id is not None:
        query = query.filter(AutobiProject.space_id == space_id)
    return query.all()
