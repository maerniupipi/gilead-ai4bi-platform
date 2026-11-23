from typing import List, Optional, Tuple

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from ... import models


def search_kb_ner_rows_alias_contains_entities(
    db: Session,
    knowledge_base_id: int,
    entities: List[str],
    limit_per_entity: int,
) -> List[models.KbNerRow]:
    """
    按知识库查询 kb_ner_row：别名字段包含任一实体子串（LIKE %entity%）。
    每个实体单独查询，条数上限为 limit_per_entity；合并结果按 id 去重保序。
    """
    seen = set()
    out: List[models.KbNerRow] = []
    cap = max(1, min(int(limit_per_entity or 20), 500))
    for ent in entities:
        e = (ent or "").strip()
        if not e:
            continue
        pattern = f"%{e}%"
        rows = (
            db.query(models.KbNerRow)
            .filter(
                models.KbNerRow.knowledge_base_id == knowledge_base_id,
                models.KbNerRow.alias.like(pattern),
            )
            .order_by(models.KbNerRow.id.asc())
            .limit(cap)
            .all()
        )
        for r in rows:
            if r.id not in seen:
                seen.add(r.id)
                out.append(r)
    return out


def count_kb_ner_rows(db: Session, knowledge_base_id: int) -> int:
    return (
        db.query(func.count(models.KbNerRow.id))
        .filter(models.KbNerRow.knowledge_base_id == knowledge_base_id)
        .scalar()
        or 0
    )


def list_sheet_summaries(db: Session, knowledge_base_id: int) -> List[Tuple[str, int]]:
    rows = (
        db.query(models.KbNerRow.sheet_name, func.count(models.KbNerRow.id))
        .filter(models.KbNerRow.knowledge_base_id == knowledge_base_id)
        .group_by(models.KbNerRow.sheet_name)
        .order_by(models.KbNerRow.sheet_name)
        .all()
    )
    return [(str(s), int(c)) for s, c in rows]


def list_kb_ner_rows_page(
    db: Session,
    knowledge_base_id: int,
    sheet_name: str,
    q: Optional[str],
    skip: int,
    limit: int,
) -> Tuple[int, List[models.KbNerRow]]:
    query = db.query(models.KbNerRow).filter(
        models.KbNerRow.knowledge_base_id == knowledge_base_id,
        models.KbNerRow.sheet_name == sheet_name,
    )
    if q and q.strip():
        pattern = f"%{q.strip()}%"
        query = query.filter(
            or_(
                models.KbNerRow.table_name.like(pattern),
                models.KbNerRow.field_name.like(pattern),
                models.KbNerRow.standard_name.like(pattern),
                models.KbNerRow.alias.like(pattern),
                models.KbNerRow.remark.like(pattern),
            )
        )
    total = query.count()
    items = (
        query.order_by(models.KbNerRow.id.asc()).offset(skip).limit(limit).all()
    )
    return total, items


def get_kb_ner_row(db: Session, knowledge_base_id: int, row_id: int) -> Optional[models.KbNerRow]:
    return (
        db.query(models.KbNerRow)
        .filter(
            models.KbNerRow.id == row_id,
            models.KbNerRow.knowledge_base_id == knowledge_base_id,
        )
        .first()
    )


def delete_sheet_rows(db: Session, knowledge_base_id: int, sheet_name: str) -> int:
    q = db.query(models.KbNerRow).filter(
        models.KbNerRow.knowledge_base_id == knowledge_base_id,
        models.KbNerRow.sheet_name == sheet_name,
    )
    count = q.count()
    q.delete(synchronize_session=False)
    return count


def delete_all_kb_ner_rows(db: Session, knowledge_base_id: int) -> None:
    db.query(models.KbNerRow).filter(
        models.KbNerRow.knowledge_base_id == knowledge_base_id
    ).delete(synchronize_session=False)


def list_all_kb_ner_rows(db: Session, knowledge_base_id: int) -> List[models.KbNerRow]:
    return (
        db.query(models.KbNerRow)
        .filter(models.KbNerRow.knowledge_base_id == knowledge_base_id)
        .order_by(models.KbNerRow.sheet_name, models.KbNerRow.id)
        .all()
    )


def bulk_insert_kb_ner_rows(
    db: Session, knowledge_base_id: int, rows_data: List[dict], space_id: int = None
) -> None:
    for d in rows_data:
        db.add(
            models.KbNerRow(
                knowledge_base_id=knowledge_base_id,
                sheet_name=d["sheet_name"],
                table_name=d["table_name"],
                field_name=d["field_name"],
                standard_name=d.get("standard_name") or "",
                alias=d.get("alias") or "",
                remark=d.get("remark") or "",
                space_id=space_id,
            )
        )
