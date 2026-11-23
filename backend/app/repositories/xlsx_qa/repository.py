"""
XLSX 表格智能问答 · 仓储层

仅封装 ORM 查询 / 写入细节；不做业务规则、不抛 HTTPException、不负责 commit。
事务由 service 层控制。
"""
from __future__ import annotations

from typing import List, Optional, Sequence

from sqlalchemy import desc, func, or_
from sqlalchemy.orm import Session, selectinload

from ...models.xlsx_qa import (
    XlsxQaConversation,
    XlsxQaDocument,
    XlsxQaInsightReport,
    XlsxQaMessage,
    XlsxQaModule,
    XlsxQaPptHistory,
    XlsxQaPptTemplate,
    XlsxQaSheet,
)


class XlsxQaRepository:

    # ------------------------------------------------------------------
    # 模块
    # ------------------------------------------------------------------

    @staticmethod
    def list_modules(
        db: Session,
        *,
        keyword: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[XlsxQaModule]:
        q = db.query(XlsxQaModule).filter(XlsxQaModule.is_deleted.is_(False))
        if keyword:
            like = f"%{keyword.strip()}%"
            q = q.filter(or_(XlsxQaModule.name.like(like), XlsxQaModule.description.like(like)))
        return (
            q.order_by(desc(XlsxQaModule.updated_at))
            .offset(skip)
            .limit(limit)
            .all()
        )

    @staticmethod
    def get_module(db: Session, module_id: int) -> Optional[XlsxQaModule]:
        return (
            db.query(XlsxQaModule)
            .filter(
                XlsxQaModule.id == module_id,
                XlsxQaModule.is_deleted.is_(False),
            )
            .first()
        )

    @staticmethod
    def get_module_by_share_token(db: Session, token: str) -> Optional[XlsxQaModule]:
        if not token or not str(token).strip():
            return None
        t = str(token).strip()
        return (
            db.query(XlsxQaModule)
            .filter(
                XlsxQaModule.share_token == t,
                XlsxQaModule.is_deleted.is_(False),
            )
            .first()
        )

    @staticmethod
    def create_module(db: Session, **kwargs) -> XlsxQaModule:
        row = XlsxQaModule(**kwargs)
        db.add(row)
        db.flush()
        return row

    @staticmethod
    def get_module_counts(
        db: Session,
        module_ids: Sequence[int],
    ) -> dict[int, dict]:
        """批量查 module → {has_document, primary_doc, conversation_count}。"""
        if not module_ids:
            return {}
        docs = (
            db.query(XlsxQaDocument)
            .filter(
                XlsxQaDocument.module_id.in_(module_ids),
                XlsxQaDocument.is_primary.is_(True),
            )
            .all()
        )
        doc_map = {d.module_id: d for d in docs}
        conv_counts = dict(
            db.query(
                XlsxQaConversation.module_id,
                func.count(XlsxQaConversation.id),
            )
            .filter(XlsxQaConversation.module_id.in_(module_ids))
            .group_by(XlsxQaConversation.module_id)
            .all()
        )
        result: dict[int, dict] = {}
        for mid in module_ids:
            d = doc_map.get(mid)
            result[mid] = {
                "has_document": d is not None,
                "primary_document": d,
                "conversation_count": int(conv_counts.get(mid) or 0),
            }
        return result

    # ------------------------------------------------------------------
    # 文档
    # ------------------------------------------------------------------

    @staticmethod
    def get_primary_document(db: Session, module_id: int) -> Optional[XlsxQaDocument]:
        return (
            db.query(XlsxQaDocument)
            .filter(
                XlsxQaDocument.module_id == module_id,
                XlsxQaDocument.is_primary.is_(True),
            )
            .order_by(desc(XlsxQaDocument.id))
            .first()
        )

    @staticmethod
    def get_document(db: Session, doc_id: int) -> Optional[XlsxQaDocument]:
        return db.query(XlsxQaDocument).filter(XlsxQaDocument.id == doc_id).first()

    @staticmethod
    def create_document(db: Session, **kwargs) -> XlsxQaDocument:
        row = XlsxQaDocument(**kwargs)
        db.add(row)
        db.flush()
        return row

    @staticmethod
    def delete_document(db: Session, doc: XlsxQaDocument) -> None:
        db.delete(doc)
        db.flush()

    @staticmethod
    def get_documents_for_module(db: Session, module_id: int) -> List[XlsxQaDocument]:
        return (
            db.query(XlsxQaDocument)
            .filter(XlsxQaDocument.module_id == module_id)
            .order_by(XlsxQaDocument.id)
            .all()
        )

    # ------------------------------------------------------------------
    # Sheet
    # ------------------------------------------------------------------

    @staticmethod
    def create_sheet(db: Session, **kwargs) -> XlsxQaSheet:
        row = XlsxQaSheet(**kwargs)
        db.add(row)
        db.flush()
        return row

    @staticmethod
    def get_sheet(db: Session, sheet_id: int) -> Optional[XlsxQaSheet]:
        return db.query(XlsxQaSheet).filter(XlsxQaSheet.id == sheet_id).first()

    @staticmethod
    def get_sheets_by_ids(db: Session, sheet_ids: List[int]) -> List[XlsxQaSheet]:
        if not sheet_ids:
            return []
        return (
            db.query(XlsxQaSheet)
            .filter(XlsxQaSheet.id.in_(sheet_ids))
            .all()
        )

    @staticmethod
    def get_sheets_for_module(
        db: Session, module_id: int, *, status: Optional[str] = None
    ) -> List[XlsxQaSheet]:
        q = (
            db.query(XlsxQaSheet)
            .join(XlsxQaDocument, XlsxQaSheet.document_id == XlsxQaDocument.id)
            .filter(XlsxQaDocument.module_id == module_id)
        )
        if status:
            q = q.filter(XlsxQaSheet.status == status)
        return q.order_by(XlsxQaDocument.id, XlsxQaSheet.sheet_index).all()

    @staticmethod
    def get_ready_sheets_for_module(db: Session, module_id: int) -> List[XlsxQaSheet]:
        return XlsxQaRepository.get_sheets_for_module(db, module_id, status="ready")

    @staticmethod
    def update_sheet(db: Session, sheet_id: int, **kwargs) -> Optional[XlsxQaSheet]:
        sheet = db.query(XlsxQaSheet).filter(XlsxQaSheet.id == sheet_id).first()
        if not sheet:
            return None
        for k, v in kwargs.items():
            setattr(sheet, k, v)
        db.flush()
        return sheet

    @staticmethod
    def delete_sheets_by_document(db: Session, document_id: int) -> None:
        db.query(XlsxQaSheet).filter(XlsxQaSheet.document_id == document_id).delete()
        db.flush()

    @staticmethod
    def all_module_sheets_ready(db: Session, module_id: int) -> bool:
        sheets = XlsxQaRepository.get_sheets_for_module(db, module_id)
        return bool(sheets) and all(s.status == "ready" for s in sheets)

    # ------------------------------------------------------------------
    # 深度洞察报告
    # ------------------------------------------------------------------

    @staticmethod
    def get_insight_report(db: Session, module_id: int) -> Optional[XlsxQaInsightReport]:
        return (
            db.query(XlsxQaInsightReport)
            .filter(XlsxQaInsightReport.module_id == module_id)
            .first()
        )

    @staticmethod
    def create_or_reset_insight_report(db: Session, module_id: int) -> XlsxQaInsightReport:
        row = XlsxQaRepository.get_insight_report(db, module_id)
        if row is None:
            row = XlsxQaInsightReport(module_id=module_id)
            db.add(row)
        row.status = "generating"
        row.phase = "profile"
        row.role_cards_json = []
        row.dimensions_json = []
        row.evidence_json = {}
        row.dim_texts_json = {}
        row.final_md = ""
        row.elapsed_ms = None
        row.error_message = None
        db.flush()
        return row

    @staticmethod
    def update_insight_report(
        db: Session,
        module_id: int,
        **kwargs,
    ) -> Optional[XlsxQaInsightReport]:
        row = XlsxQaRepository.get_insight_report(db, module_id)
        if not row:
            return None
        for k, v in kwargs.items():
            setattr(row, k, v)
        db.flush()
        return row

    # ------------------------------------------------------------------
    # 会话 / 消息
    # ------------------------------------------------------------------

    @staticmethod
    def list_conversations(db: Session, module_id: int) -> List[XlsxQaConversation]:
        return (
            db.query(XlsxQaConversation)
            .filter(XlsxQaConversation.module_id == module_id)
            .order_by(desc(XlsxQaConversation.updated_at), desc(XlsxQaConversation.id))
            .all()
        )

    @staticmethod
    def get_conversation(db: Session, conv_id: int) -> Optional[XlsxQaConversation]:
        return db.query(XlsxQaConversation).filter(XlsxQaConversation.id == conv_id).first()

    @staticmethod
    def create_conversation(db: Session, module_id: int, title: str) -> XlsxQaConversation:
        row = XlsxQaConversation(module_id=module_id, title=title)
        db.add(row)
        db.flush()
        return row

    @staticmethod
    def delete_conversation(db: Session, conv: XlsxQaConversation) -> None:
        db.delete(conv)
        db.flush()

    @staticmethod
    def list_messages(db: Session, conversation_id: int) -> List[XlsxQaMessage]:
        return (
            db.query(XlsxQaMessage)
            .filter(XlsxQaMessage.conversation_id == conversation_id)
            .order_by(XlsxQaMessage.id)
            .all()
        )

    @staticmethod
    def create_message(db: Session, **kwargs) -> XlsxQaMessage:
        row = XlsxQaMessage(**kwargs)
        db.add(row)
        db.flush()
        return row

    @staticmethod
    def latest_messages(
        db: Session,
        conversation_id: int,
        *,
        limit: int = 4,
    ) -> List[XlsxQaMessage]:
        """取最近 N 条消息（按时间顺序从旧到新返回，方便构造 history）。"""
        rows = (
            db.query(XlsxQaMessage)
            .filter(XlsxQaMessage.conversation_id == conversation_id)
            .order_by(desc(XlsxQaMessage.id))
            .limit(limit)
            .all()
        )
        return list(reversed(rows))

    @staticmethod
    def count_messages(db: Session, conversation_id: int) -> int:
        return (
            db.query(func.count(XlsxQaMessage.id))
            .filter(XlsxQaMessage.conversation_id == conversation_id)
            .scalar()
            or 0
        )

    @staticmethod
    def update_conversation_sheets(
        db: Session, conv_id: int, active_sheet_ids: List[int]
    ) -> Optional[XlsxQaConversation]:
        conv = db.query(XlsxQaConversation).filter(XlsxQaConversation.id == conv_id).first()
        if not conv:
            return None
        conv.active_sheet_ids = active_sheet_ids
        db.flush()
        return conv

    # ------------------------------------------------------------------
    # PPT 模板
    # ------------------------------------------------------------------

    @staticmethod
    def list_ppt_templates(db: Session) -> List[XlsxQaPptTemplate]:
        return (
            db.query(XlsxQaPptTemplate)
            .order_by(XlsxQaPptTemplate.sort_order, XlsxQaPptTemplate.id)
            .all()
        )

    @staticmethod
    def get_ppt_template(db: Session, template_id: str) -> Optional[XlsxQaPptTemplate]:
        return (
            db.query(XlsxQaPptTemplate)
            .filter(XlsxQaPptTemplate.id == template_id)
            .first()
        )

    # ------------------------------------------------------------------
    # PPT 导出历史
    # ------------------------------------------------------------------

    @staticmethod
    def create_ppt_history(db: Session, **kwargs) -> XlsxQaPptHistory:
        row = XlsxQaPptHistory(**kwargs)
        db.add(row)
        db.flush()
        return row

    @staticmethod
    def get_ppt_history(db: Session, history_id: int) -> Optional[XlsxQaPptHistory]:
        return db.query(XlsxQaPptHistory).filter(XlsxQaPptHistory.id == history_id).first()

    @staticmethod
    def list_ppt_history_for_module(db: Session, module_id: int) -> List[XlsxQaPptHistory]:
        from sqlalchemy import desc
        return (
            db.query(XlsxQaPptHistory)
            .filter(XlsxQaPptHistory.module_id == module_id)
            .order_by(desc(XlsxQaPptHistory.created_at))
            .all()
        )

    @staticmethod
    def update_ppt_history(db: Session, history_id: int, **kwargs) -> Optional[XlsxQaPptHistory]:
        row = db.query(XlsxQaPptHistory).filter(XlsxQaPptHistory.id == history_id).first()
        if not row:
            return None
        for k, v in kwargs.items():
            setattr(row, k, v)
        db.flush()
        return row

    @staticmethod
    def delete_ppt_history(db: Session, history_id: int) -> None:
        row = db.query(XlsxQaPptHistory).filter(XlsxQaPptHistory.id == history_id).first()
        if row:
            db.delete(row)
            db.flush()
