"""评测标签数据访问层"""
from typing import List, Optional

from sqlalchemy.orm import Session

from ...models.eval import EvalTag


def list_tags(db: Session, space_id: int) -> List[EvalTag]:
    """列出空间下所有标签"""
    return (
        db.query(EvalTag)
        .filter(EvalTag.space_id == space_id)
        .order_by(EvalTag.id.asc())
        .all()
    )


def get_tag(db: Session, tag_id: int, space_id: int = None) -> Optional[EvalTag]:
    """获取单个标签"""
    q = db.query(EvalTag).filter(EvalTag.id == tag_id)
    if space_id is not None:
        q = q.filter(EvalTag.space_id == space_id)
    return q.first()


def get_tag_by_name(db: Session, space_id: int, name: str) -> Optional[EvalTag]:
    """按名称获取标签"""
    return db.query(EvalTag).filter(
        EvalTag.space_id == space_id,
        EvalTag.name == name.strip(),
    ).first()


def create_tag(db: Session, space_id: int, name: str, color: str = "#409EFF") -> EvalTag:
    """创建标签"""
    tag = EvalTag(space_id=space_id, name=name.strip(), color=color)
    db.add(tag)
    db.flush()
    return tag


def update_tag(db: Session, tag_id: int, space_id: int, name: str = None, color: str = None) -> Optional[EvalTag]:
    """更新标签"""
    tag = get_tag(db, tag_id, space_id)
    if tag is None:
        return None
    if name is not None:
        tag.name = name.strip()
    if color is not None:
        tag.color = color
    db.flush()
    return tag


def delete_tag(db: Session, tag_id: int, space_id: int) -> bool:
    """删除标签"""
    tag = get_tag(db, tag_id, space_id)
    if tag is None:
        return False
    db.delete(tag)
    db.flush()
    return True
