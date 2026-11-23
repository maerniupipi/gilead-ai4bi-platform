"""
评测文件夹服务层
"""
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from ...models.eval import EvalFolder, EvalSuite


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _folder_to_dict(row: EvalFolder, children: Optional[List[Dict]] = None) -> Dict[str, Any]:
    d: Dict[str, Any] = {
        "id": row.id,
        "space_id": row.space_id,
        "parent_id": row.parent_id,
        "name": row.name,
        "description": row.description,
        "sort_order": int(row.sort_order or 0),
        "is_system": bool(row.is_system),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }
    if children is not None:
        d["children"] = children
    return d


def _build_tree(rows: List[EvalFolder], parent_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """从扁平列表构建树结构。"""
    tree: List[Dict[str, Any]] = []
    for row in rows:
        if row.parent_id == parent_id:
            children = _build_tree(rows, row.id)
            node = _folder_to_dict(row, children=children)
            tree.append(node)
    # 按 sort_order, id 排序
    tree.sort(key=lambda x: (x.get("sort_order", 0), x.get("id", 0)))
    return tree


# ---------------------------------------------------------------------------
# service functions
# ---------------------------------------------------------------------------

def list_folders_service(db: Session, space_id: int) -> List[Dict[str, Any]]:
    """列出空间下所有文件夹，返回树形结构。"""
    rows = (
        db.query(EvalFolder)
        .filter(EvalFolder.space_id == space_id)
        .order_by(EvalFolder.sort_order.asc(), EvalFolder.id.asc())
        .all()
    )
    return _build_tree(rows, parent_id=None)


def create_folder_service(db: Session, space_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
    """创建文件夹。"""
    name = (data.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="文件夹名称不能为空")

    parent_id = data.get("parent_id")
    # 验证父文件夹存在且同属一个空间
    if parent_id is not None:
        parent = db.query(EvalFolder).filter(
            EvalFolder.id == parent_id,
            EvalFolder.space_id == space_id,
        ).first()
        if not parent:
            raise HTTPException(status_code=404, detail="父文件夹不存在")

    # 计算 sort_order
    max_order = _get_max_order(db, space_id, parent_id)
    next_order = max_order + 1

    row = EvalFolder(
        space_id=space_id,
        parent_id=parent_id,
        name=name,
        description=data.get("description"),
        sort_order=data.get("sort_order", next_order),
        is_system=False,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _folder_to_dict(row)


def update_folder_service(
    db: Session, folder_id: int, space_id: int, data: Dict[str, Any],
) -> Dict[str, Any]:
    """更新文件夹。"""
    row = db.query(EvalFolder).filter(
        EvalFolder.id == folder_id,
        EvalFolder.space_id == space_id,
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="文件夹不存在")

    if row.is_system:
        raise HTTPException(status_code=400, detail="系统文件夹不可编辑")

    if "name" in data:
        name = (data["name"] or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="文件夹名称不能为空")
        row.name = name

    if "description" in data:
        row.description = data["description"]

    if "sort_order" in data:
        row.sort_order = data["sort_order"]

    # 移动到新父文件夹
    if "parent_id" in data:
        new_parent_id = data["parent_id"]
        if new_parent_id == folder_id:
            raise HTTPException(status_code=400, detail="不能将文件夹移动到自身")
        if new_parent_id is not None:
            parent = db.query(EvalFolder).filter(
                EvalFolder.id == new_parent_id,
                EvalFolder.space_id == space_id,
            ).first()
            if not parent:
                raise HTTPException(status_code=404, detail="目标父文件夹不存在")
            # 检查是否会形成循环（新父文件夹不能是自己的后代）
            if _is_descendant(db, new_parent_id, folder_id):
                raise HTTPException(status_code=400, detail="不能将文件夹移动到其子文件夹下")
        row.parent_id = new_parent_id

    db.commit()
    db.refresh(row)
    return _folder_to_dict(row)


def delete_folder_service(db: Session, folder_id: int, space_id: int) -> Dict[str, Any]:
    """删除文件夹。检查是否有子文件夹或关联评测集。"""
    row = db.query(EvalFolder).filter(
        EvalFolder.id == folder_id,
        EvalFolder.space_id == space_id,
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="文件夹不存在")

    if row.is_system:
        raise HTTPException(status_code=400, detail="系统文件夹不可删除")

    # 检查是否有子文件夹
    child_count = db.query(EvalFolder).filter(EvalFolder.parent_id == folder_id).count()
    if child_count > 0:
        raise HTTPException(status_code=400, detail="文件夹下存在子文件夹，请先删除子文件夹")

    # 检查是否有关联评测集
    suite_count = db.query(EvalSuite).filter(EvalSuite.folder_id == folder_id).count()
    if suite_count > 0:
        raise HTTPException(status_code=400, detail="文件夹下存在评测集，请先移动或删除评测集")

    db.delete(row)
    db.commit()
    return {"ok": True}


def move_folder_service(db: Session, folder_id: int, direction: str, space_id: int) -> List[Dict[str, Any]]:
    """移动文件夹（上移/下移），在同级兄弟节点之间交换位置。"""
    folder = db.query(EvalFolder).filter(
        EvalFolder.id == folder_id,
        EvalFolder.space_id == space_id,
    ).first()
    if not folder:
        raise HTTPException(status_code=404, detail="文件夹不存在")

    # 查找同级兄弟节点
    parent_id = folder.parent_id
    if parent_id is None:
        rows = (
            db.query(EvalFolder)
            .filter(EvalFolder.space_id == space_id, EvalFolder.parent_id.is_(None))
            .order_by(EvalFolder.sort_order.asc(), EvalFolder.id.asc())
            .all()
        )
    else:
        rows = (
            db.query(EvalFolder)
            .filter(EvalFolder.space_id == space_id, EvalFolder.parent_id == parent_id)
            .order_by(EvalFolder.sort_order.asc(), EvalFolder.id.asc())
            .all()
        )

    ids = [r.id for r in rows]
    try:
        i = ids.index(folder_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="文件夹不存在")

    if direction == "up":
        if i == 0:
            raise HTTPException(status_code=400, detail="已在最上方")
        rows[i], rows[i - 1] = rows[i - 1], rows[i]
    elif direction == "down":
        if i == len(rows) - 1:
            raise HTTPException(status_code=400, detail="已在最下方")
        rows[i], rows[i + 1] = rows[i + 1], rows[i]
    else:
        raise HTTPException(status_code=400, detail="direction 须为 up 或 down")

    for idx, r in enumerate(rows):
        r.sort_order = idx
    db.commit()
    for r in rows:
        db.refresh(r)
    return [_folder_to_dict(r) for r in rows]


# ---------------------------------------------------------------------------
# internal helpers
# ---------------------------------------------------------------------------


def _get_max_order(db: Session, space_id: int, parent_id: Optional[int]) -> int:
    q = db.query(func.max(EvalFolder.sort_order)).filter(EvalFolder.space_id == space_id)
    if parent_id is None:
        q = q.filter(EvalFolder.parent_id.is_(None))
    else:
        q = q.filter(EvalFolder.parent_id == parent_id)
    return int(q.scalar() or 0)


def _is_descendant(db: Session, candidate_id: int, ancestor_id: int) -> bool:
    """检查 candidate_id 是否是 ancestor_id 的后代。"""
    visited = set()
    stack = [candidate_id]
    while stack:
        current = stack.pop()
        if current in visited:
            continue
        visited.add(current)
        if current == ancestor_id:
            return True
        children = db.query(EvalFolder.id).filter(EvalFolder.parent_id == current).all()
        stack.extend([c[0] for c in children])
    return False
