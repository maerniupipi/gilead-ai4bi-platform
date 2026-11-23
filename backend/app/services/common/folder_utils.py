"""
通用文件夹工具函数
消除 autobi、agent_app 等模块中重复的 ensure_default_folder 逻辑
"""
from typing import Type, TypeVar, Generic
from sqlalchemy.orm import Session

from ...core.database import get_db

ModelType = TypeVar("ModelType")


def folder_to_dict(row, extra_fields: dict = None) -> dict:
    """
    将文件夹对象转为字典的通用方法。

    Args:
        row: 文件夹 ORM 对象
        extra_fields: 额外字段 dict

    Returns:
        文件夹字典
    """
    result = {
        "id": row.id,
        "name": row.name,
        "sort_order": int(row.sort_order or 0),
        "is_system": bool(row.is_system),
        "created_at": row.created_at,
    }
    # 如果模型有 space_id 字段则添加
    if hasattr(row, "space_id"):
        result["space_id"] = row.space_id
    if extra_fields:
        result.update(extra_fields)
    return result


def ensure_default_folder(
    db: Session,
    folder_model: Type[ModelType],
    space_id: int = None,
    default_name: str = "默认文件夹",
) -> int:
    """
    保证至少存在一个系统默认文件夹；若无则创建。

    查找优先级：
    1. 已有 is_system=True 的文件夹
    2. 名为「默认文件夹」的已有文件夹（升级为系统文件夹）
    3. 创建新的系统默认文件夹

    Args:
        db: 数据库会话
        folder_model: 文件夹模型类（如 AutobiFolder、AgentAppFolder）
        space_id: 空间ID，可为空
        default_name: 默认文件夹名称

    Returns:
        默认文件夹的 ID
    """
    # 1. 查找已有的系统文件夹
    query = db.query(folder_model).filter(folder_model.is_system.is_(True))
    if space_id is not None:
        query = query.filter(folder_model.space_id == space_id)
    row = query.order_by(folder_model.id.asc()).first()
    if row is not None:
        return int(row.id)

    # 2. 查找名为「默认文件夹」的已有文件夹
    legacy_query = db.query(folder_model).filter(folder_model.name == default_name)
    if space_id is not None:
        legacy_query = legacy_query.filter(folder_model.space_id == space_id)
    legacy = legacy_query.order_by(folder_model.id.asc()).first()
    if legacy is not None:
        legacy.is_system = True
        if legacy.sort_order is None:
            legacy.sort_order = 0
        db.commit()
        db.refresh(legacy)
        return int(legacy.id)

    # 3. 创建新的系统默认文件夹
    kwargs = {
        "name": default_name,
        "sort_order": 0,
        "is_system": True,
    }
    if space_id is not None:
        kwargs["space_id"] = space_id

    row = folder_model(**kwargs)
    db.add(row)
    db.commit()
    db.refresh(row)
    return int(row.id)
