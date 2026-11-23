from typing import List, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ... import models, schemas
from ...repositories.knowledge.knowledge_base.repository import get_knowledge_base_active
from ...repositories.knowledge import kb_ner_repository as ner_repo
from ...schemas.kb_ner import (
    KbNerImportMode,
    NER_MAX_PER_KNOWLEDGE_BASE,
    NER_FIELD_MAX_LEN,
    NER_SHEET_NAME_MAX_LEN,
)


def _ensure_kb(db: Session, knowledge_base_id: int, space_id: int = None) -> models.KnowledgeBase:
    kb = get_knowledge_base_active(db, knowledge_base_id, space_id)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    return kb


def _normalize_row(d: dict) -> dict:
    return {
        "sheet_name": (d.get("sheet_name") or "").strip()[:NER_SHEET_NAME_MAX_LEN],
        "table_name": (d.get("table_name") or "").strip()[:NER_FIELD_MAX_LEN],
        "field_name": (d.get("field_name") or "").strip()[:NER_FIELD_MAX_LEN],
        "standard_name": (d.get("standard_name") or "").strip()[:NER_FIELD_MAX_LEN],
        "alias": (d.get("alias") or "").strip()[:NER_FIELD_MAX_LEN],
        "remark": (d.get("remark") or "").strip()[:NER_FIELD_MAX_LEN],
    }


def _validate_row_norm(n: dict) -> None:
    if not n["sheet_name"]:
        raise HTTPException(status_code=400, detail="sheet_name 不能为空")
    if not n["table_name"] or not n["field_name"]:
        raise HTTPException(status_code=400, detail="表名与字段名不能为空")
    for key, max_len, label in (
        ("sheet_name", NER_SHEET_NAME_MAX_LEN, "Sheet 名"),
        ("table_name", NER_FIELD_MAX_LEN, "表名"),
        ("field_name", NER_FIELD_MAX_LEN, "字段名"),
        ("standard_name", NER_FIELD_MAX_LEN, "标准名称"),
        ("alias", NER_FIELD_MAX_LEN, "别名"),
        ("remark", NER_FIELD_MAX_LEN, "备注"),
    ):
        if len(n[key]) > max_len:
            raise HTTPException(
                status_code=400,
                detail=f"{label}长度不能超过 {max_len} 个字符",
            )


def list_ner_sheets_service(db: Session, knowledge_base_id: int, space_id: int = None) -> List[schemas.KbNerSheetSummary]:
    _ensure_kb(db, knowledge_base_id, space_id)
    pairs = ner_repo.list_sheet_summaries(db, knowledge_base_id)
    return [schemas.KbNerSheetSummary(sheet_name=s, row_count=c) for s, c in pairs]


def list_ner_rows_page_service(
    db: Session,
    knowledge_base_id: int,
    sheet_name: str,
    q: Optional[str],
    page: int,
    page_size: int,
    space_id: int = None,
) -> schemas.KbNerRowPage:
    _ensure_kb(db, knowledge_base_id, space_id)
    if not sheet_name or not sheet_name.strip():
        raise HTTPException(status_code=400, detail="请指定 sheet_name")
    page = max(1, page)
    page_size = min(max(1, page_size), 100)
    skip = (page - 1) * page_size
    total, items = ner_repo.list_kb_ner_rows_page(
        db, knowledge_base_id, sheet_name.strip(), q, skip, page_size
    )
    return schemas.KbNerRowPage(
        total=total,
        items=[schemas.KbNerRowOut.model_validate(x) for x in items],
    )


def create_ner_row_service(
    db: Session, knowledge_base_id: int, body: schemas.KbNerRowCreate, space_id: int = None
) -> schemas.KbNerRowOut:
    _ensure_kb(db, knowledge_base_id, space_id)
    n = _normalize_row(body.model_dump())
    _validate_row_norm(n)
    current = ner_repo.count_kb_ner_rows(db, knowledge_base_id)
    if current >= NER_MAX_PER_KNOWLEDGE_BASE:
        raise HTTPException(
            status_code=400,
            detail=f"该知识库 NER 映射已达上限 {NER_MAX_PER_KNOWLEDGE_BASE} 条",
        )
    row = models.KbNerRow(
        knowledge_base_id=knowledge_base_id,
        sheet_name=n["sheet_name"],
        table_name=n["table_name"],
        field_name=n["field_name"],
        standard_name=n["standard_name"],
        alias=n["alias"],
        remark=n["remark"],
        space_id=space_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return schemas.KbNerRowOut.model_validate(row)


def update_ner_row_service(
    db: Session,
    knowledge_base_id: int,
    row_id: int,
    body: schemas.KbNerRowUpdate,
    space_id: int = None,
) -> schemas.KbNerRowOut:
    _ensure_kb(db, knowledge_base_id, space_id)
    row = ner_repo.get_kb_ner_row(db, knowledge_base_id, row_id)
    if not row:
        raise HTTPException(status_code=404, detail="记录不存在")
    data = body.model_dump(exclude_unset=True)
    merged = {
        "sheet_name": data.get("sheet_name", row.sheet_name),
        "table_name": data.get("table_name", row.table_name),
        "field_name": data.get("field_name", row.field_name),
        "standard_name": data.get("standard_name", row.standard_name),
        "alias": data.get("alias", row.alias),
        "remark": data.get("remark", row.remark),
    }
    n = _normalize_row(merged)
    _validate_row_norm(n)
    row.sheet_name = n["sheet_name"]
    row.table_name = n["table_name"]
    row.field_name = n["field_name"]
    row.standard_name = n["standard_name"]
    row.alias = n["alias"]
    row.remark = n["remark"]
    db.commit()
    db.refresh(row)
    return schemas.KbNerRowOut.model_validate(row)


def delete_ner_row_service(db: Session, knowledge_base_id: int, row_id: int, space_id: int = None) -> dict:
    _ensure_kb(db, knowledge_base_id, space_id)
    row = ner_repo.get_kb_ner_row(db, knowledge_base_id, row_id)
    if not row:
        raise HTTPException(status_code=404, detail="记录不存在")
    db.delete(row)
    db.commit()
    return {"message": "deleted"}


def delete_ner_sheet_service(db: Session, knowledge_base_id: int, sheet_name: str, space_id: int = None) -> dict:
    _ensure_kb(db, knowledge_base_id, space_id)
    if not sheet_name or not sheet_name.strip():
        raise HTTPException(status_code=400, detail="请指定 sheet_name")
    n = ner_repo.delete_sheet_rows(db, knowledge_base_id, sheet_name.strip())
    db.commit()
    return {"message": "ok", "deleted": n}


def export_all_ner_rows_service(
    db: Session, knowledge_base_id: int, space_id: int = None
) -> List[schemas.KbNerRowOut]:
    _ensure_kb(db, knowledge_base_id, space_id)
    rows = ner_repo.list_all_kb_ner_rows(db, knowledge_base_id)
    return [schemas.KbNerRowOut.model_validate(x) for x in rows]


def import_ner_rows_service(
    db: Session, knowledge_base_id: int, body: schemas.KbNerImportRequest, space_id: int = None
) -> schemas.KbNerImportResult:
    _ensure_kb(db, knowledge_base_id, space_id)
    if not body.rows:
        raise HTTPException(status_code=400, detail="导入数据为空")

    normalized: List[dict] = []
    for item in body.rows:
        n = _normalize_row(item.model_dump())
        _validate_row_norm(n)
        normalized.append(n)

    if len(normalized) > NER_MAX_PER_KNOWLEDGE_BASE:
        raise HTTPException(
            status_code=400,
            detail=f"单次导入不能超过 {NER_MAX_PER_KNOWLEDGE_BASE} 条",
        )

    if body.mode == KbNerImportMode.replace_all:
        ner_repo.delete_all_kb_ner_rows(db, knowledge_base_id)
        ner_repo.bulk_insert_kb_ner_rows(db, knowledge_base_id, normalized, space_id)
        db.commit()
        return schemas.KbNerImportResult(
            inserted=len(normalized),
            message=f"已全量覆盖，共写入 {len(normalized)} 条",
        )

    # append
    current = ner_repo.count_kb_ner_rows(db, knowledge_base_id)
    if current + len(normalized) > NER_MAX_PER_KNOWLEDGE_BASE:
        raise HTTPException(
            status_code=400,
            detail=(
                f"批量新增后将超过上限 {NER_MAX_PER_KNOWLEDGE_BASE} 条"
                f"（当前 {current} 条，本次 {len(normalized)} 条）"
            ),
        )
    ner_repo.bulk_insert_kb_ner_rows(db, knowledge_base_id, normalized, space_id)
    db.commit()
    return schemas.KbNerImportResult(
        inserted=len(normalized),
        message=f"已新增 {len(normalized)} 条",
    )