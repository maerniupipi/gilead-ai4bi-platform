"""评测输出模板数据访问层"""
from typing import List, Optional

from sqlalchemy.orm import Session

from ...models.eval import EvalOutputTemplate


def list_templates(db: Session, suite_id: int) -> List[EvalOutputTemplate]:
    """列出评测集的所有输出模板"""
    return (
        db.query(EvalOutputTemplate)
        .filter(EvalOutputTemplate.suite_id == suite_id)
        .order_by(EvalOutputTemplate.is_default.desc(), EvalOutputTemplate.id.asc())
        .all()
    )


def get_template(db: Session, template_id: int) -> Optional[EvalOutputTemplate]:
    """获取单个输出模板"""
    return db.query(EvalOutputTemplate).filter(EvalOutputTemplate.id == template_id).first()


def create_template(
    db: Session,
    suite_id: int,
    name: str,
    fields: list,
    is_default: bool = False,
) -> EvalOutputTemplate:
    """创建输出模板"""
    template = EvalOutputTemplate(
        suite_id=suite_id,
        name=name.strip(),
        fields=fields,
        is_default=is_default,
    )
    db.add(template)
    db.flush()
    return template


def update_template(db: Session, template_id: int, **kwargs) -> Optional[EvalOutputTemplate]:
    """更新输出模板"""
    template = get_template(db, template_id)
    if template is None:
        return None
    for key, value in kwargs.items():
        if value is not None:
            setattr(template, key, value)
    db.flush()
    return template


def delete_template(db: Session, template_id: int) -> bool:
    """删除输出模板"""
    template = get_template(db, template_id)
    if template is None:
        return False
    db.delete(template)
    db.flush()
    return True


def set_default(db: Session, template_id: int, suite_id: int) -> None:
    """设置默认模板（先取消其他默认，再设置当前）"""
    db.query(EvalOutputTemplate).filter(
        EvalOutputTemplate.suite_id == suite_id
    ).update({EvalOutputTemplate.is_default: False}, synchronize_session=False)

    template = get_template(db, template_id)
    if template is not None:
        template.is_default = True
    db.flush()
