"""
评测输出模板服务层
"""
from typing import Any, Dict, List

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ...models.eval import EvalOutputTemplate, EvalSuite


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _template_to_dict(row: EvalOutputTemplate) -> Dict[str, Any]:
    return {
        "id": row.id,
        "suite_id": row.suite_id,
        "name": row.name,
        "fields": row.fields,
        "is_default": row.is_default,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _validate_suite(db: Session, suite_id: int) -> EvalSuite:
    suite = db.query(EvalSuite).filter(EvalSuite.id == suite_id).first()
    if not suite:
        raise HTTPException(status_code=404, detail="评测集不存在")
    return suite


# ---------------------------------------------------------------------------
# service functions
# ---------------------------------------------------------------------------

def list_templates_service(db: Session, suite_id: int) -> List[Dict[str, Any]]:
    """列出评测集的所有输出模板。"""
    _validate_suite(db, suite_id)
    rows = (
        db.query(EvalOutputTemplate)
        .filter(EvalOutputTemplate.suite_id == suite_id)
        .order_by(EvalOutputTemplate.is_default.desc(), EvalOutputTemplate.id.asc())
        .all()
    )
    return [_template_to_dict(r) for r in rows]


def create_template_service(db: Session, suite_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
    """创建输出模板。"""
    _validate_suite(db, suite_id)

    name = (data.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="模板名称不能为空")

    fields = data.get("fields")
    if not fields or not isinstance(fields, list):
        raise HTTPException(status_code=400, detail="字段定义不能为空")

    row = EvalOutputTemplate(
        suite_id=suite_id,
        name=name,
        fields=fields,
        is_default=data.get("is_default", False),
    )

    # 如果设为默认，取消其他默认
    if row.is_default:
        _clear_default(db, suite_id)

    db.add(row)
    db.commit()
    db.refresh(row)
    return _template_to_dict(row)


def update_template_service(
    db: Session, template_id: int, data: Dict[str, Any],
) -> Dict[str, Any]:
    """更新输出模板。"""
    row = db.query(EvalOutputTemplate).filter(EvalOutputTemplate.id == template_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="输出模板不存在")

    if "name" in data:
        name = (data["name"] or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="模板名称不能为空")
        row.name = name

    if "fields" in data:
        fields = data["fields"]
        if not fields or not isinstance(fields, list):
            raise HTTPException(status_code=400, detail="字段定义不能为空")
        row.fields = fields

    if "is_default" in data and data["is_default"]:
        _clear_default(db, row.suite_id)
        row.is_default = True
    elif "is_default" in data:
        row.is_default = False

    db.commit()
    db.refresh(row)
    return _template_to_dict(row)


def delete_template_service(db: Session, template_id: int) -> Dict[str, Any]:
    """删除输出模板。"""
    row = db.query(EvalOutputTemplate).filter(EvalOutputTemplate.id == template_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="输出模板不存在")

    db.delete(row)
    db.commit()
    return {"ok": True}


def set_default_service(db: Session, template_id: int, suite_id: int) -> Dict[str, Any]:
    """设置默认输出模板。"""
    row = db.query(EvalOutputTemplate).filter(
        EvalOutputTemplate.id == template_id,
        EvalOutputTemplate.suite_id == suite_id,
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="输出模板不存在")

    _clear_default(db, suite_id)
    row.is_default = True
    db.commit()
    db.refresh(row)
    return _template_to_dict(row)


# ---------------------------------------------------------------------------
# internal helpers
# ---------------------------------------------------------------------------

def _clear_default(db: Session, suite_id: int) -> None:
    """清除评测集下所有模板的默认标记。"""
    db.query(EvalOutputTemplate).filter(
        EvalOutputTemplate.suite_id == suite_id,
        EvalOutputTemplate.is_default.is_(True),
    ).update({"is_default": False})
