"""
XLSX 表格智能问答 · 业务服务层

承担：
  - 模块 / 文档 / 会话 / 消息 CRUD
  - 文件上传：OSS put → 解析 → 动态建表 → 批量插入（事务 + 外部副作用）
  - 预览 / 下载
  - 调用 qa_pipeline 产出 SSE；并在流结束时把 assistant 消息持久化

事务边界：所有写 DB 操作由本层 commit；失败要补偿 OSS / 动态表。
"""
from __future__ import annotations

import datetime as _dt
import json
import logging
import os
import secrets
import time
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

import asyncio as _asyncio_mod
import threading

from ...core.database import engine as default_engine, SessionLocal
from ...models.xlsx_qa import (
    XlsxQaConversation,
    XlsxQaDocument,
    XlsxQaInsightReport,
    XlsxQaMessage,
    XlsxQaModule,
    XlsxQaPptHistory,
    XlsxQaSheet,
)
from ...repositories.xlsx_qa import XlsxQaRepository
from ...schemas.xlsx_qa import (
    XlsxQaAssistantExtras,
    XlsxQaAskRequest,
    XlsxQaChartSpec,
    XlsxQaColumnMeta,
    XlsxQaConversationCreate,
    XlsxQaConversationInfo,
    XlsxQaConversationSheetUpdate,
    XlsxQaDocumentInfo,
    XlsxQaDownloadOut,
    XlsxQaExportPptRequest,
    XlsxQaPptExportAsyncResponse,
    XlsxQaPptHistoryOut,
    XlsxQaKnowledgeAppendRequest,
    XlsxQaKnowledgeAppendOut,
    XlsxQaMessageInfo,
    XlsxQaModuleCreate,
    XlsxQaModuleDetail,
    XlsxQaModuleSummary,
    XlsxQaModuleUpdate,
    XlsxQaPreviewOut,
    XlsxQaShareIssueOut,
    XlsxQaPromptsConfig,
    XlsxQaPromptsConfigOut,
    XlsxQaSheetInfo,
    XlsxQaSheetRegenerateOut,
    XlsxQaSubQuestionResult,
)
from . import insight_pipeline
from . import llm_client
from . import prompts as prompts_mod
from . import qa_pipeline
from . import ppt_exporter
from . import pdf_exporter
from . import table_understanding
from ..oss.client import resolve_active_storage
from .sql_safety import SqlSafetyError, run_select
from .xlsx_parser import (
    DynamicTableBuilder,
    ParseOptions,
    build_data_table_name,
    insert_dataframe,
    parse_xlsx,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 配置读取（运行时可变）
# ---------------------------------------------------------------------------

def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "") or default)
    except (TypeError, ValueError):
        return default


def _parse_options() -> ParseOptions:
    return ParseOptions(
        max_rows=_env_int("XLSX_QA_MAX_ROWS", 100_000),
        max_columns=_env_int("XLSX_QA_MAX_COLUMNS", 200),
    )


def _sql_limits() -> Tuple[int, int]:
    return (
        _env_int("XLSX_QA_SQL_MAX_ROWS", 1000),
        _env_int("XLSX_QA_SQL_TIMEOUT_MS", 10_000),
    )


# ---------------------------------------------------------------------------
# DTO 适配
# ---------------------------------------------------------------------------

def _fmt_dt(v: Optional[_dt.datetime]) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, _dt.datetime):
        return v.isoformat(timespec="seconds")
    return str(v)


def _document_to_dto(doc: XlsxQaDocument, *, include_sheets: bool = True) -> XlsxQaDocumentInfo:
    cols_raw = doc.columns_json or []
    cols = [
        XlsxQaColumnMeta(
            raw_header=c.get("raw_header") or "",
            column_name=c.get("column_name") or "",
            column_type=c.get("column_type") or "",
            sample=c.get("sample") or [],
            distinct=c.get("distinct"),
        )
        for c in cols_raw
    ]
    # 多 Sheet：从关联的 Sheet 记录构建列表
    sheets: List[XlsxQaSheetInfo] = []
    if include_sheets:
        for s in (doc.sheets or []):
            sheets.append(_sheet_to_dto(s))
    return XlsxQaDocumentInfo(
        id=doc.id,
        module_id=doc.module_id,
        file_name=doc.file_name,
        file_size=int(doc.file_size or 0),
        sheet_name=doc.sheet_name,
        data_table_name=doc.data_table_name,
        total_rows=int(doc.total_rows or 0),
        total_columns=int(doc.total_columns or 0),
        columns=cols,
        understanding_md=doc.understanding_md,
        suggested_questions=list(doc.suggested_questions_json or []),
        status=doc.status or "pending",
        parse_error=doc.parse_error,
        sheet_count=int(doc.sheet_count or 0),
        sheets=sheets,
        is_primary=bool(doc.is_primary),
        created_at=_fmt_dt(doc.created_at),
        updated_at=_fmt_dt(doc.updated_at),
    )


def _sheet_to_dto(s: XlsxQaSheet) -> XlsxQaSheetInfo:
    cols_raw = s.columns_json or []
    cols = [
        XlsxQaColumnMeta(
            raw_header=c.get("raw_header") or "",
            column_name=c.get("column_name") or "",
            column_type=c.get("column_type") or "",
            sample=c.get("sample") or [],
            distinct=c.get("distinct"),
        )
        for c in cols_raw
    ]
    return XlsxQaSheetInfo(
        id=s.id,
        document_id=s.document_id,
        sheet_index=s.sheet_index,
        sheet_name=s.sheet_name,
        data_table_name=s.data_table_name,
        total_rows=int(s.total_rows or 0),
        total_columns=int(s.total_columns or 0),
        columns=cols,
        understanding_md=s.understanding_md,
        suggested_questions=list(s.suggested_questions_json or []),
        status=s.status or "pending",
        parse_error=s.parse_error,
        created_at=_fmt_dt(s.created_at),
        updated_at=_fmt_dt(s.updated_at),
    )


def _module_language(m: XlsxQaModule) -> Optional[str]:
    """从 extra_config_json 中读取模块语言设置。"""
    cfg = m.extra_config_json or {}
    if isinstance(cfg, dict):
        lang = cfg.get("language")
        if lang and isinstance(lang, str) and lang.strip():
            return lang.strip()
    return None


def _module_summary(
    m: XlsxQaModule,
    *,
    primary_doc: Optional[XlsxQaDocument],
    conversation_count: int,
) -> XlsxQaModuleSummary:
    return XlsxQaModuleSummary(
        id=m.id,
        name=m.name,
        description=m.description,
        owner_display_name=m.owner_display_name,
        llm_provider_id=m.llm_provider_id,
        llm_model=m.llm_model,
        language=_module_language(m),
        has_document=primary_doc is not None,
        primary_document_file_name=primary_doc.file_name if primary_doc else None,
        primary_document_status=primary_doc.status if primary_doc else None,
        conversation_count=conversation_count,
        created_at=_fmt_dt(m.created_at),
        updated_at=_fmt_dt(m.updated_at),
    )


def _message_to_dto(msg: XlsxQaMessage) -> XlsxQaMessageInfo:
    extras: Optional[XlsxQaAssistantExtras] = None
    if msg.extras_json:
        try:
            extras = XlsxQaAssistantExtras.model_validate(msg.extras_json)
        except Exception:  # noqa: BLE001
            extras = None
    return XlsxQaMessageInfo(
        id=msg.id,
        conversation_id=msg.conversation_id,
        role=msg.role,
        content=msg.content,
        status=msg.status,
        extras=extras,
        created_at=_fmt_dt(msg.created_at),
    )


# ---------------------------------------------------------------------------
# 模块 CRUD
# ---------------------------------------------------------------------------

def list_modules_service(
    db: Session,
    *,
    keyword: Optional[str],
    skip: int,
    limit: int,
) -> List[XlsxQaModuleSummary]:
    rows = XlsxQaRepository.list_modules(db, keyword=keyword, skip=skip, limit=limit)
    counts = XlsxQaRepository.get_module_counts(db, [m.id for m in rows])
    return [
        _module_summary(
            m,
            primary_doc=counts.get(m.id, {}).get("primary_document"),
            conversation_count=counts.get(m.id, {}).get("conversation_count", 0),
        )
        for m in rows
    ]


def get_module_detail_service(db: Session, module_id: int) -> XlsxQaModuleDetail:
    m = XlsxQaRepository.get_module(db, module_id)
    if not m:
        raise HTTPException(status_code=404, detail="模块不存在")
    primary = XlsxQaRepository.get_primary_document(db, module_id)
    docs = XlsxQaRepository.get_documents_for_module(db, module_id)
    all_ready = XlsxQaRepository.all_module_sheets_ready(db, module_id) if docs else False
    conv_count = len(XlsxQaRepository.list_conversations(db, module_id))
    base = _module_summary(m, primary_doc=primary, conversation_count=conv_count)
    return XlsxQaModuleDetail(
        **base.model_dump(),
        primary_document=_document_to_dto(primary, include_sheets=False) if primary else None,
        documents=[_document_to_dto(d) for d in docs],
        module_understanding_md=m.module_understanding_md,
        all_sheets_ready=all_ready,
    )


def create_module_service(db: Session, body: XlsxQaModuleCreate) -> XlsxQaModuleDetail:
    # 语言设置存入 extra_config_json
    extra_cfg: Optional[dict] = None
    lang = (body.language or "").strip()
    if lang and lang != "auto":
        extra_cfg = {"language": lang}

    row = XlsxQaRepository.create_module(
        db,
        name=body.name.strip(),
        description=(body.description or "").strip() or None,
        llm_provider_id=body.llm_provider_id,
        llm_model=(body.llm_model or "").strip() or None,
        extra_config_json=extra_cfg,
    )
    db.commit()
    db.refresh(row)
    return get_module_detail_service(db, row.id)


def update_module_service(
    db: Session,
    module_id: int,
    body: XlsxQaModuleUpdate,
) -> XlsxQaModuleDetail:
    m = XlsxQaRepository.get_module(db, module_id)
    if not m:
        raise HTTPException(status_code=404, detail="模块不存在")
    if body.name is not None:
        m.name = body.name.strip()
    if body.description is not None:
        m.description = body.description.strip() or None
    if body.llm_provider_id is not None:
        m.llm_provider_id = body.llm_provider_id
    if body.llm_model is not None:
        m.llm_model = body.llm_model.strip() or None
    if body.language is not None:
        cfg = dict(m.extra_config_json or {})
        lang = body.language.strip()
        if lang and lang != "auto":
            cfg["language"] = lang
        else:
            cfg.pop("language", None)
        m.extra_config_json = cfg or None
    db.commit()
    db.refresh(m)
    return get_module_detail_service(db, m.id)


def get_module_prompts_service(db: Session, module_id: int) -> XlsxQaPromptsConfigOut:
    m = XlsxQaRepository.get_module(db, module_id)
    if not m:
        raise HTTPException(status_code=404, detail="模块不存在")
    override = _extract_prompts_override(m) or {}
    current = XlsxQaPromptsConfig(
        plan_system=override.get("plan_system"),
        text_to_sql_system=override.get("text_to_sql_system"),
        summary_system=override.get("summary_system"),
        chart_system=override.get("chart_system"),
    )
    defaults = XlsxQaPromptsConfig(
        plan_system=prompts_mod.PLAN_SYSTEM,
        text_to_sql_system=prompts_mod.TEXT_TO_SQL_SYSTEM,
        summary_system=prompts_mod.SUMMARY_SYSTEM,
        chart_system=prompts_mod.CHART_SYSTEM,
    )
    return XlsxQaPromptsConfigOut(current=current, defaults=defaults)


def update_module_prompts_service(
    db: Session,
    module_id: int,
    body: XlsxQaPromptsConfig,
) -> XlsxQaPromptsConfigOut:
    """覆盖写入自定义提示词；字段传 None 或空串 → 清空该项（回落到默认）。"""
    m = XlsxQaRepository.get_module(db, module_id)
    if not m:
        raise HTTPException(status_code=404, detail="模块不存在")
    cfg = dict(m.extra_config_json or {})
    prompts_cfg = dict(cfg.get("prompts") or {}) if isinstance(cfg.get("prompts"), dict) else {}

    for key in ("plan_system", "text_to_sql_system", "summary_system", "chart_system"):
        val = getattr(body, key, None)
        if val is None or (isinstance(val, str) and not val.strip()):
            prompts_cfg.pop(key, None)
        else:
            prompts_cfg[key] = val

    if prompts_cfg:
        cfg["prompts"] = prompts_cfg
    else:
        cfg.pop("prompts", None)
    m.extra_config_json = cfg or None
    db.commit()
    db.refresh(m)
    return get_module_prompts_service(db, module_id)


def issue_share_token_service(
    db: Session,
    module_id: int,
    *,
    rotate: bool = False,
) -> XlsxQaShareIssueOut:
    """为模块生成或复用 share_token（opaque），用于免登录外链。"""
    m = XlsxQaRepository.get_module(db, module_id)
    if not m:
        raise HTTPException(status_code=404, detail="模块不存在")
    if rotate or not m.share_token:
        m.share_token = secrets.token_urlsafe(32)
        db.commit()
        db.refresh(m)
    token = (m.share_token or "").strip()
    if not token:
        m.share_token = secrets.token_urlsafe(32)
        db.commit()
        db.refresh(m)
        token = m.share_token or ""
    base = (os.getenv("XLSX_QA_SHARE_PUBLIC_BASE_URL") or "").strip() or None
    return XlsxQaShareIssueOut(token=token, share_public_base_url=base)


def revoke_share_token_service(db: Session, module_id: int) -> None:
    m = XlsxQaRepository.get_module(db, module_id)
    if not m:
        raise HTTPException(status_code=404, detail="模块不存在")
    m.share_token = None
    db.commit()


def delete_module_service(db: Session, module_id: int) -> None:
    m = XlsxQaRepository.get_module(db, module_id)
    if not m:
        raise HTTPException(status_code=404, detail="模块不存在")
    # 先拿到所有文档，做 OSS + 动态表清理（多 Sheet 版）
    docs = list(m.documents or [])
    # 软删主表
    m.is_deleted = True
    db.commit()
    # 外部副作用（失败只记日志）
    builder = DynamicTableBuilder()
    for d in docs:
        # 删除所有 Sheet 的物理表
        for s in (d.sheets or []):
            if s.data_table_name:
                try:
                    builder.drop(default_engine, s.data_table_name)
                except Exception as e:
                    logger.warning("drop sheet table %s failed: %s", s.data_table_name, e)
        # 保留旧的 document 级表名以防向后兼容
        if d.data_table_name:
            try:
                builder.drop(default_engine, d.data_table_name)
            except Exception as e:
                logger.warning("drop data table %s failed: %s", d.data_table_name, e)
        if d.oss_object_key:
            resolve_active_storage(db, space_id=m.space_id).delete_object(d.oss_object_key)


# ---------------------------------------------------------------------------
# 文档上传 / 下载 / 删除 / 预览
# ---------------------------------------------------------------------------

async def upload_document_service(
    db: Session,
    module_id: int,
    upload: UploadFile,
    *,
    sheet_indices: Optional[List[int]] = None,
) -> XlsxQaDocumentInfo:
    """上传 xlsx 文件，解析其中的指定 Sheet（默认全部非空 Sheet，最多 5 个）。

    sheet_indices: 0-based Sheet 索引列表，最多 5 个。为空时取全部非空 Sheet。
    每个模块最多 5 个文件。
    """
    m = XlsxQaRepository.get_module(db, module_id)
    if not m:
        raise HTTPException(status_code=404, detail="模块不存在")

    # 多文件：最多 5 个
    existing_docs = XlsxQaRepository.get_documents_for_module(db, module_id)
    if len(existing_docs) >= 5:
        raise HTTPException(status_code=400, detail="一个模块最多上传 5 个文件，请删除旧文件后再试")

    filename = (upload.filename or "untitled.xlsx").strip()
    if not filename.lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(status_code=400, detail="仅支持 .xlsx / .xlsm 文件")

    max_bytes = _env_int("XLSX_QA_MAX_FILE_BYTES", 50 * 1024 * 1024)
    data = await upload.read()
    if not data:
        raise HTTPException(status_code=400, detail="文件为空")
    if len(data) > max_bytes:
        raise HTTPException(status_code=400, detail=f"文件大小超过上限 {max_bytes} bytes")

    import asyncio as _asyncio

    # 校验 sheet_indices
    if sheet_indices is not None:
        sheet_indices = list(set(sheet_indices))  # 去重
        if len(sheet_indices) > 5:
            raise HTTPException(status_code=400, detail="最多选择 5 个 Sheet")

    # OSS 上传 + xlsx 解析并行
    oss_storage = resolve_active_storage(db, space_id=m.space_id)
    oss_key = oss_storage.build_module_file_key(module_id, filename)

    def _do_put():
        return oss_storage.put_bytes(
            oss_key,
            data,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    def _do_parse():
        return parse_xlsx(data, sheet_indices=sheet_indices, options=_parse_options())

    upload_res, parse_res = await _asyncio.gather(
        _asyncio.to_thread(_do_put),
        _asyncio.to_thread(_do_parse),
        return_exceptions=True,
    )

    if isinstance(upload_res, RuntimeError):
        raise HTTPException(status_code=500, detail=f"OSS 未配置：{upload_res}") from upload_res
    if isinstance(upload_res, Exception):
        raise HTTPException(status_code=502, detail=f"OSS 上传失败：{upload_res}") from upload_res

    # 建 Document 记录
    is_first = len(existing_docs) == 0
    doc = XlsxQaRepository.create_document(
        db,
        module_id=module_id,
        file_name=filename,
        file_size=len(data),
        oss_object_key=oss_key,
        status="parsing",
        is_primary=is_first,
    )
    db.commit()
    db.refresh(doc)

    if isinstance(parse_res, ValueError):
        doc.status = "failed"
        doc.parse_error = str(parse_res)
        db.commit()
        raise HTTPException(status_code=400, detail=f"解析失败：{parse_res}") from parse_res
    if isinstance(parse_res, Exception):
        doc.status = "failed"
        doc.parse_error = str(parse_res)
        db.commit()
        raise HTTPException(status_code=500, detail=f"解析失败：{parse_res}") from parse_res
    parsed_sheets = parse_res  # List[ParsedSheet]

    # 为每个 Sheet：建表 → 插数据 → 创建 Sheet 记录
    builder = DynamicTableBuilder()
    created_sheets: List[XlsxQaSheet] = []
    created_table_names: List[str] = []

    for sheet_idx, parsed in enumerate(parsed_sheets):
        table_name = build_data_table_name(module_id, doc.id, sheet_idx)
        try:
            await _asyncio.to_thread(builder.create, default_engine, table_name, parsed.columns)
            await _asyncio.to_thread(
                insert_dataframe, default_engine, table_name, parsed.columns, parsed.df
            )
            created_table_names.append(table_name)
        except Exception as e:
            # 回滚已创建的表
            for tn in created_table_names:
                try:
                    await _asyncio.to_thread(builder.drop, default_engine, tn)
                except Exception:
                    pass
            doc.status = "failed"
            doc.parse_error = f"Sheet「{parsed.sheet_name}」建表/插入失败：{e}"
            db.commit()
            raise HTTPException(status_code=500, detail=doc.parse_error) from e

        sheet_record = XlsxQaRepository.create_sheet(
            db,
            document_id=doc.id,
            sheet_index=sheet_idx,
            sheet_name=parsed.sheet_name,
            data_table_name=table_name,
            total_rows=parsed.total_rows,
            total_columns=parsed.total_columns,
            columns_json=[
                {
                    "raw_header": c.raw_header,
                    "column_name": c.column_name,
                    "column_type": c.column_type,
                    "sample": c.sample,
                    "distinct": c.distinct,
                }
                for c in parsed.columns
            ],
            status="pending",
        )
        created_sheets.append(sheet_record)

    # 更新 Document
    doc.sheet_count = len(parsed_sheets)
    doc.status = "ready"
    doc.parse_error = None
    db.commit()
    db.refresh(doc)

    # 后台并行生成每个 Sheet 的表理解 + 推荐问题
    for s in created_sheets:
        _asyncio_mod.create_task(
            _background_generate_sheet_understanding(m.id, doc.id, s.id)
        )

    return _document_to_dto(doc)


async def _background_generate_sheet_understanding(
    module_id: int, doc_id: int, sheet_id: int
) -> None:
    """后台任务：为单个 Sheet 生成表理解 + 推荐问题，完成后检查是否触发模块汇总。"""
    db = SessionLocal()
    try:
        module = XlsxQaRepository.get_module(db, module_id)
        doc = XlsxQaRepository.get_document(db, doc_id)
        sheet = XlsxQaRepository.get_sheet(db, sheet_id)
        if module and doc and sheet:
            await _generate_sheet_post_parse_safe(db, module, doc, sheet)
    except Exception as e:
        logger.warning(
            "xlsx_qa.background_sheet_understanding failed module=%s doc=%s sheet=%s: %s",
            module_id, doc_id, sheet_id, e,
        )
    finally:
        db.close()


async def _generate_sheet_post_parse_safe(
    db: Session,
    module: XlsxQaModule,
    doc: XlsxQaDocument,
    sheet: XlsxQaSheet,
) -> None:
    """为单个 Sheet 并行生成表理解 + 推荐问题，写入 sheet 记录。

    完成后检查是否该模块所有 Sheet 都已就绪，若就绪则触发模块级汇总理解。
    """
    import asyncio as _asyncio

    try:
        choice = llm_client.resolve_llm(
            db,
            provider_id=module.llm_provider_id,
            model=module.llm_model,
        )
    except HTTPException as e:
        logger.warning("xlsx_qa.sheet_understanding skipped: no usable llm: %s", e.detail)
        return
    except Exception as e:
        logger.warning("xlsx_qa.sheet_understanding resolve_llm failed: %s", e)
        return

    # 采样
    try:
        head_rows, rand_rows = await _asyncio.to_thread(
            table_understanding.sample_rows,
            default_engine,
            sheet.data_table_name,
            int(sheet.total_rows or 0),
            head_size=10,
            random_size=90,
        )
    except Exception as e:
        logger.warning("xlsx_qa.sheet_understanding sample failed: %s", e)
        head_rows, rand_rows = [], []

    module_lang = _module_language(module)
    common_kwargs = dict(
        engine=default_engine,
        choice=choice,
        data_table_name=sheet.data_table_name,
        file_name=doc.file_name,
        sheet_name=sheet.sheet_name,
        total_rows=int(sheet.total_rows or 0),
        columns_json=list(sheet.columns_json or []),
        head_rows=head_rows,
        random_rows=rand_rows,
        language=module_lang,
    )

    t_understanding = table_understanding.generate_understanding(**common_kwargs)
    t_suggest = table_understanding.generate_suggested_questions(**common_kwargs)

    md_res, q_res = await _asyncio.gather(t_understanding, t_suggest, return_exceptions=True)

    changed = False
    if isinstance(md_res, Exception):
        logger.warning("xlsx_qa.sheet_understanding understanding failed: %s", md_res)
    elif md_res:
        sheet.understanding_md = md_res
        changed = True

    if isinstance(q_res, Exception):
        logger.warning("xlsx_qa.sheet_understanding suggested_questions failed: %s", q_res)
    elif q_res:
        sheet.suggested_questions_json = list(q_res)
        changed = True

    if changed:
        sheet.status = "ready"
        db.commit()
        db.refresh(sheet)
        logger.info(
            "xlsx_qa.sheet_understanding saved module=%s doc=%s sheet=%s understanding=%d questions=%d",
            module.id, doc.id, sheet.id,
            len(sheet.understanding_md or ""),
            len(sheet.suggested_questions_json or []),
        )

    # 检查是否该模块所有 Sheet 都已就绪 → 触发模块级汇总理解
    if XlsxQaRepository.all_module_sheets_ready(db, module.id):
        if not module.module_understanding_md:
            await _generate_module_summary_understanding(db, module.id)


async def _generate_module_summary_understanding(db: Session, module_id: int) -> None:
    """生成跨 Sheet 汇总理解，写入 module.module_understanding_md。"""
    module = XlsxQaRepository.get_module(db, module_id)
    if not module:
        return
    sheets = XlsxQaRepository.get_ready_sheets_for_module(db, module_id)
    if len(sheets) <= 1:
        return  # 只有 1 个 Sheet 时不需要汇总理解

    try:
        choice = llm_client.resolve_llm(
            db, provider_id=module.llm_provider_id, model=module.llm_model
        )
    except Exception as e:
        logger.warning("xlsx_qa.module_summary resolve_llm failed: %s", e)
        return

    # 构建输入：每个 Sheet 的元信息 + 表理解摘要
    sheet_infos: List[str] = []
    for s in sheets:
        cols = [c.get("column_name", "") for c in (s.columns_json or [])]
        info = (
            f"### Sheet ID={s.id}: {s.sheet_name} (file: {s.document.file_name if s.document else '?'})\n"
            f"- Rows: {s.total_rows}, Columns: {len(cols)}\n"
            f"- Column names: {', '.join(cols[:12])}\n"
            f"- Understanding: {s.understanding_md or '(none)'}\n"
        )
        sheet_infos.append(info)

    user_payload = (
        "# Multi-Sheet Dataset Overview\n\n"
        + "\n---\n".join(sheet_infos)
        + "\n\n---\n\n"
        "Based on the above sheet metadata and understandings, produce a Markdown report "
        "as instructed in the system prompt."
    )

    try:
        md = await llm_client.chat_text(
            choice,
            system=prompts_mod.MODULE_SUMMARY_SYSTEM,
            user=user_payload,
            temperature=0.3,
            max_tokens=800,
            timeout=90.0,
        )
        if md and md.strip():
            module.module_understanding_md = md.strip()
            db.commit()
            logger.info(
                "xlsx_qa.module_summary saved module=%s sheets=%d len=%d",
                module_id, len(sheets), len(md.strip()),
            )
    except Exception as e:
        logger.warning("xlsx_qa.module_summary LLM call failed: %s", e)


async def regenerate_understanding_service(
    db: Session, module_id: int, doc_id: int,
    *,
    sheet_id: Optional[int] = None,
) -> XlsxQaDocumentInfo:
    """手工触发重新生成表理解。

    若指定 sheet_id，则只重新生成该 Sheet 的理解；
    否则，重新生成文档下所有 Sheet 的理解。
    """
    module = XlsxQaRepository.get_module(db, module_id)
    if not module:
        raise HTTPException(status_code=404, detail="模块不存在")
    doc = XlsxQaRepository.get_document(db, doc_id)
    if not doc or doc.module_id != module_id:
        raise HTTPException(status_code=404, detail="文档不存在")

    if sheet_id is not None:
        sheet = XlsxQaRepository.get_sheet(db, sheet_id)
        if not sheet or sheet.document_id != doc.id:
            raise HTTPException(status_code=404, detail="Sheet 不存在")
        if sheet.status not in ("ready",) or not sheet.data_table_name:
            raise HTTPException(status_code=400, detail="Sheet 尚未解析就绪，无法生成业务理解")
        await _generate_sheet_post_parse_safe(db, module, doc, sheet)
    else:
        # 重新生成所有 Sheet
        for s in (doc.sheets or []):
            if s.status == "ready" and s.data_table_name:
                await _generate_sheet_post_parse_safe(db, module, doc, s)
    db.refresh(doc)
    return _document_to_dto(doc)


async def regenerate_sheet_understanding_service(
    db: Session, module_id: int, doc_id: int, sheet_id: int,
) -> XlsxQaSheetRegenerateOut:
    """重新生成单个 Sheet 的表理解 + 推荐问题。"""
    module = XlsxQaRepository.get_module(db, module_id)
    if not module:
        raise HTTPException(status_code=404, detail="模块不存在")
    doc = XlsxQaRepository.get_document(db, doc_id)
    if not doc or doc.module_id != module_id:
        raise HTTPException(status_code=404, detail="文档不存在")
    sheet = XlsxQaRepository.get_sheet(db, sheet_id)
    if not sheet or sheet.document_id != doc.id:
        raise HTTPException(status_code=404, detail="Sheet 不存在")
    if sheet.status not in ("ready",) or not sheet.data_table_name:
        raise HTTPException(status_code=400, detail="Sheet 尚未解析就绪")
    await _generate_sheet_post_parse_safe(db, module, doc, sheet)
    db.refresh(sheet)
    return XlsxQaSheetRegenerateOut(
        understanding_md=sheet.understanding_md or "",
        suggested_questions=list(sheet.suggested_questions_json or []),
    )


def update_sheet_understanding_service(
    db: Session, module_id: int, doc_id: int, sheet_id: int, understanding_md: str,
) -> XlsxQaSheetRegenerateOut:
    """手动更新单个 Sheet 的表理解内容（用户编辑）。"""
    module = XlsxQaRepository.get_module(db, module_id)
    if not module:
        raise HTTPException(status_code=404, detail="模块不存在")
    doc = XlsxQaRepository.get_document(db, doc_id)
    if not doc or doc.module_id != module_id:
        raise HTTPException(status_code=404, detail="文档不存在")
    sheet = XlsxQaRepository.get_sheet(db, sheet_id)
    if not sheet or sheet.document_id != doc.id:
        raise HTTPException(status_code=404, detail="Sheet 不存在")
    sheet.understanding_md = understanding_md
    db.commit()
    db.refresh(sheet)
    return XlsxQaSheetRegenerateOut(
        understanding_md=sheet.understanding_md or "",
        suggested_questions=list(sheet.suggested_questions_json or []),
    )


async def regenerate_module_summary_service(db: Session, module_id: int) -> str:
    """重新生成模块级汇总理解。"""
    module = XlsxQaRepository.get_module(db, module_id)
    if not module:
        raise HTTPException(status_code=404, detail="模块不存在")
    await _generate_module_summary_understanding(db, module_id)
    db.refresh(module)
    return module.module_understanding_md or ""


def append_knowledge_service(
    db: Session,
    body: XlsxQaKnowledgeAppendRequest,
) -> XlsxQaKnowledgeAppendOut:
    """将用户采纳的知识条目追加到 understanding_md 并落库。

    若指定了 sheet_id，追加到该 Sheet 的理解；否则回退到文档的主理解。
    """
    if body.sheet_id is not None:
        sheet = XlsxQaRepository.get_sheet(db, body.sheet_id)
        if not sheet:
            raise HTTPException(status_code=404, detail="Sheet 不存在")
        existing_md = sheet.understanding_md or ""
    else:
        doc = XlsxQaRepository.get_primary_document(db, body.module_id)
        if not doc:
            raise HTTPException(status_code=404, detail="文档不存在")
        existing_md = doc.understanding_md or ""

    knowledge_items = [
        {
            "alias": item.alias,
            "maps_to": item.maps_to,
            "column_hint": item.column_hint,
            "description": item.description,
        }
        for item in body.knowledge_items
    ]

    new_md = table_understanding.append_knowledge_to_understanding(
        existing_md=existing_md,
        knowledge_items=knowledge_items,
    )

    if body.sheet_id is not None:
        sheet = XlsxQaRepository.get_sheet(db, body.sheet_id)
        if sheet:
            sheet.understanding_md = new_md
    else:
        doc = XlsxQaRepository.get_primary_document(db, body.module_id)
        if doc:
            doc.understanding_md = new_md

    db.commit()

    logger.info(
        "xlsx_qa.append_knowledge module=%s sheet=%s items=%d",
        body.module_id,
        body.sheet_id,
        len(knowledge_items),
    )
    return XlsxQaKnowledgeAppendOut(
        understanding_md=new_md,
        sheet_id=body.sheet_id,
    )


def delete_document_service(db: Session, module_id: int, doc_id: int) -> None:
    doc = XlsxQaRepository.get_document(db, doc_id)
    if not doc or doc.module_id != module_id:
        raise HTTPException(status_code=404, detail="文档不存在")
    m = XlsxQaRepository.get_module(db, module_id)
    oss_key = doc.oss_object_key
    builder = DynamicTableBuilder()
    # 删除所有 Sheet 的物理表
    for s in (doc.sheets or []):
        if s.data_table_name:
            try:
                builder.drop(default_engine, s.data_table_name)
            except Exception as e:
                logger.warning("drop sheet table %s failed: %s", s.data_table_name, e)
    # 删除文档时级联删除 Sheet 记录（ORM cascade）
    XlsxQaRepository.delete_document(db, doc)
    # 清空当前模块的所有对话历史
    for conv in XlsxQaRepository.list_conversations(db, module_id):
        XlsxQaRepository.delete_conversation(db, conv)
    db.commit()
    if oss_key:
        resolve_active_storage(db, space_id=m.space_id if m else None).delete_object(oss_key)


def download_document_service(db: Session, module_id: int, doc_id: int) -> XlsxQaDownloadOut:
    doc = XlsxQaRepository.get_document(db, doc_id)
    if not doc or doc.module_id != module_id:
        raise HTTPException(status_code=404, detail="文档不存在")
    m = XlsxQaRepository.get_module(db, module_id)
    oss_storage = resolve_active_storage(db, space_id=m.space_id if m else None)
    try:
        url = oss_storage.generate_presigned_url(doc.oss_object_key)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"生成下载链接失败：{e}") from e
    return XlsxQaDownloadOut(url=url, expires_in=oss_storage.default_expires)


def preview_document_service(
    db: Session,
    module_id: int,
    doc_id: int,
    *,
    limit: int = 20,
    sheet_id: Optional[int] = None,
) -> XlsxQaPreviewOut:
    """预览文档数据。若指定 sheet_id，预览该 Sheet 的数据；否则取第一个 Sheet。"""
    doc = XlsxQaRepository.get_document(db, doc_id)
    if not doc or doc.module_id != module_id:
        raise HTTPException(status_code=404, detail="文档不存在")
    if doc.status != "ready":
        raise HTTPException(status_code=400, detail=f"文档尚未解析成功（当前：{doc.status}）")

    # 确定目标 Sheet 和表名
    if sheet_id is not None:
        sheet = XlsxQaRepository.get_sheet(db, sheet_id)
        if not sheet or sheet.document_id != doc.id:
            raise HTTPException(status_code=404, detail="Sheet 不存在")
        table_name = sheet.data_table_name
    elif doc.sheets:
        table_name = doc.sheets[0].data_table_name
    else:
        # 向后兼容：旧数据使用 doc 级 data_table_name
        table_name = doc.data_table_name
        if not table_name:
            raise HTTPException(status_code=400, detail="文档没有可用数据表")

    limit = max(1, min(limit, 200))
    sql = f"SELECT * FROM `{table_name}` ORDER BY `_row_index` LIMIT {limit}"
    try:
        cols, rows, total, truncated = run_select(
            default_engine,
            sql,
            allowed_tables=[table_name],
            max_rows=limit,
            timeout_ms=_env_int("XLSX_QA_SQL_TIMEOUT_MS", 10_000),
        )
    except SqlSafetyError as e:
        raise HTTPException(status_code=500, detail=f"内部预览 SQL 被拦截：{e}") from e
    hidden = {"_row_id", "_row_index"}
    keep_idx = [i for i, c in enumerate(cols) if c not in hidden]
    return XlsxQaPreviewOut(
        columns=[cols[i] for i in keep_idx],
        rows=[[r[i] for i in keep_idx] for r in rows],
        total_rows=total,
        truncated=truncated,
    )


# ---------------------------------------------------------------------------
# 会话 / 消息
# ---------------------------------------------------------------------------

def list_conversations_service(db: Session, module_id: int) -> List[XlsxQaConversationInfo]:
    if not XlsxQaRepository.get_module(db, module_id):
        raise HTTPException(status_code=404, detail="模块不存在")
    rows = XlsxQaRepository.list_conversations(db, module_id)
    # 批量查消息数
    counts = {c.id: XlsxQaRepository.count_messages(db, c.id) for c in rows}
    return [
        XlsxQaConversationInfo(
            id=c.id,
            module_id=c.module_id,
            title=c.title,
            active_sheet_ids=c.active_sheet_ids if isinstance(c.active_sheet_ids, list) else None,
            message_count=counts.get(c.id, 0),
            created_at=_fmt_dt(c.created_at),
            updated_at=_fmt_dt(c.updated_at),
        )
        for c in rows
    ]


def create_conversation_service(
    db: Session,
    module_id: int,
    body: XlsxQaConversationCreate,
) -> XlsxQaConversationInfo:
    m = XlsxQaRepository.get_module(db, module_id)
    if not m:
        raise HTTPException(status_code=404, detail="模块不存在")
    title = (body.title or "").strip() or "新会话"
    row = XlsxQaRepository.create_conversation(db, module_id, title)
    db.commit()
    db.refresh(row)
    return XlsxQaConversationInfo(
        id=row.id,
        module_id=row.module_id,
        title=row.title,
        message_count=0,
        created_at=_fmt_dt(row.created_at),
        updated_at=_fmt_dt(row.updated_at),
    )


def delete_conversation_service(db: Session, conv_id: int) -> None:
    conv = XlsxQaRepository.get_conversation(db, conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")
    XlsxQaRepository.delete_conversation(db, conv)
    db.commit()


def list_messages_service(db: Session, conv_id: int) -> List[XlsxQaMessageInfo]:
    conv = XlsxQaRepository.get_conversation(db, conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")
    rows = XlsxQaRepository.list_messages(db, conv_id)
    return [_message_to_dto(r) for r in rows]


# ---------------------------------------------------------------------------
# 提问（SSE 流式）
# ---------------------------------------------------------------------------

async def ask_stream_service(
    db: Session,
    conversation_id: int,
    body: XlsxQaAskRequest,
) -> AsyncIterator[str]:
    """返回一个 async 生成器，yield SSE 文本块。

    注意：调用方（router）直接把这个生成器丢给 StreamingResponse 即可。
    持久化 assistant 消息的写库由本函数在最后一次 yield 前完成。
    """
    conv = XlsxQaRepository.get_conversation(db, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")
    module = XlsxQaRepository.get_module(db, conv.module_id)
    if not module:
        raise HTTPException(status_code=404, detail="模块不存在")

    # 确定活跃 Sheet 列表
    active_sheet_ids: Optional[List[int]] = (
        conv.active_sheet_ids if isinstance(conv.active_sheet_ids, list) else None
    )
    sheets = _resolve_active_sheets(db, conv.module_id, active_sheet_ids)

    if not sheets:
        raise HTTPException(
            status_code=400,
            detail="请先上传 xlsx 并等待解析完成，再发起提问。",
        )

    # 持久化 user 消息
    user_msg = XlsxQaRepository.create_message(
        db,
        conversation_id=conv.id,
        role="user",
        content=body.question.strip(),
        status="ok",
        extras_json=None,
    )
    # 更新会话 updated_at
    if conv.title in ("新会话", "", None):
        conv.title = (body.question.strip() or "新会话")[:60]
    db.commit()
    db.refresh(user_msg)

    history = _build_history(db, conv.id)

    sql_max_rows, sql_timeout_ms = _sql_limits()
    prompts_override = _extract_prompts_override(module)
    module_language = _module_language(module)

    # 构建 active_sheets
    active_sheets: List[qa_pipeline.SheetInfo] = [
        qa_pipeline.SheetInfo(
            sheet_id=s.id,
            file_name=s.document.file_name if s.document else "?",
            sheet_name=s.sheet_name,
            data_table_name=s.data_table_name,
            columns_json=list(s.columns_json or []),
            understanding_md=s.understanding_md or "",
            total_rows=s.total_rows or 0,
        )
        for s in sheets
    ]

    ctx = qa_pipeline.QaContext(
        db=db,
        engine=default_engine,
        conversation_id=conv.id,
        module_name=module.name,
        active_sheets=active_sheets,
        user_question=body.question.strip(),
        history=history,
        llm_provider_id=body.llm_provider_id or module.llm_provider_id,
        llm_model=body.llm_model or module.llm_model,
        prompts_override=prompts_override,
        sql_max_rows=sql_max_rows,
        sql_timeout_ms=sql_timeout_ms,
        module_understanding_md=module.module_understanding_md,
        language=module_language,
    )

    return _stream_and_persist(db, conv, user_msg.id, ctx)


async def insight_stream_service(db: Session, module_id: int) -> AsyncIterator[str]:
    """模块级「数据深度洞察报告」SSE：不写入会话消息。"""
    module = XlsxQaRepository.get_module(db, module_id)
    if not module:
        raise HTTPException(status_code=404, detail="模块不存在")

    if not XlsxQaRepository.all_module_sheets_ready(db, module_id):
        raise HTTPException(
            status_code=400,
            detail="请等待所有工作表解析完成后再生成洞察报告。",
        )

    sheets = XlsxQaRepository.get_ready_sheets_for_module(db, module_id)
    if not sheets:
        raise HTTPException(
            status_code=400,
            detail="暂无可分析的表格数据，请先上传并完成解析。",
        )

    sql_max_rows, sql_timeout_ms = _sql_limits()

    active_sheets: List[qa_pipeline.SheetInfo] = [
        qa_pipeline.SheetInfo(
            sheet_id=s.id,
            file_name=s.document.file_name if s.document else "?",
            sheet_name=s.sheet_name,
            data_table_name=s.data_table_name,
            columns_json=list(s.columns_json or []),
            understanding_md=s.understanding_md or "",
            total_rows=s.total_rows or 0,
        )
        for s in sheets
    ]

    ctx = insight_pipeline.InsightContext(
        db=db,
        engine=default_engine,
        module_id=module.id,
        module_name=module.name or "",
        active_sheets=active_sheets,
        module_understanding_md=module.module_understanding_md,
        llm_provider_id=module.llm_provider_id,
        llm_model=module.llm_model,
        language=_module_language(module),
        sql_max_rows=sql_max_rows,
        sql_timeout_ms=sql_timeout_ms,
    )

    return insight_pipeline.run_insight_pipeline(ctx)


def _insight_report_out(row: XlsxQaInsightReport) -> Dict[str, Any]:
    return {
        "id": row.id,
        "module_id": row.module_id,
        "status": row.status or "generating",
        "phase": row.phase or "",
        "role_cards": row.role_cards_json or [],
        "dimensions": row.dimensions_json or [],
        "evidence": row.evidence_json or {},
        "dim_texts": row.dim_texts_json or {},
        "final_md": row.final_md or "",
        "elapsed_ms": row.elapsed_ms,
        "error_message": row.error_message or "",
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def get_insight_report_service(db: Session, module_id: int) -> Dict[str, Any]:
    module = XlsxQaRepository.get_module(db, module_id)
    if not module:
        raise HTTPException(status_code=404, detail="模块不存在")
    row = XlsxQaRepository.get_insight_report(db, module_id)
    if not row:
        return {"exists": False}
    data = _insight_report_out(row)
    data["exists"] = True
    return data


def _resolve_active_sheets(
    db: Session,
    module_id: int,
    active_sheet_ids: Optional[List[int]],
) -> List[XlsxQaSheet]:
    """根据会话的 active_sheet_ids 加载就绪的 Sheet 列表。

    若 active_sheet_ids 为空，取模块所有就绪 Sheet（旧会话兼容）。
    """
    if active_sheet_ids:
        sheets = XlsxQaRepository.get_sheets_by_ids(db, active_sheet_ids)
        return [s for s in sheets if s.status == "ready"]
    return XlsxQaRepository.get_ready_sheets_for_module(db, module_id)


def update_conversation_sheets_service(
    db: Session,
    conv_id: int,
    body: XlsxQaConversationSheetUpdate,
) -> dict:
    """更新会话关联的 Sheet 范围。"""
    conv = XlsxQaRepository.update_conversation_sheets(db, conv_id, body.active_sheet_ids)
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")
    db.commit()
    return {"active_sheet_ids": body.active_sheet_ids}


def _extract_prompts_override(module: XlsxQaModule) -> Optional[Dict[str, Optional[str]]]:
    cfg = module.extra_config_json or {}
    if not isinstance(cfg, dict):
        return None
    prompts_cfg = cfg.get("prompts")
    if not isinstance(prompts_cfg, dict):
        return None
    return {k: v for k, v in prompts_cfg.items() if isinstance(v, str)}


def _build_history(db: Session, conv_id: int) -> List[Dict[str, str]]:
    """取最近 2 轮（4 条）作为 LLM history。"""
    rows = XlsxQaRepository.latest_messages(db, conv_id, limit=4)
    history: List[Dict[str, str]] = []
    for r in rows:
        if r.role == "user":
            history.append({"role": "user", "content": r.content or ""})
        elif r.role == "assistant":
            # 只保留摘要，避免把大结果塞给模型
            summary = ""
            if isinstance(r.extras_json, dict):
                summary = str(r.extras_json.get("summary_markdown") or "")
            content = summary or (r.content or "")
            history.append({"role": "assistant", "content": content[:2000]})
    return history


async def _stream_and_persist(
    db: Session,
    conv: XlsxQaConversation,
    user_msg_id: int,
    ctx: qa_pipeline.QaContext,
) -> AsyncIterator[str]:
    """包一层：转发 pipeline SSE，并在收到 `done` / `error` 时持久化 assistant 消息。"""
    last_state: Dict = {
        "plan_summary": "",
        "subquestions": [],
        "summary_markdown": "",
        "follow_up_questions": [],
        "stage_timings": {},
        "chart": None,
        "charts": [],
        "primary_chart_id": None,
        "think_content": None,       # Stage 0 Module Planning 思考过程
        "relevant_sheet_ids": None,  # Stage 0 筛选的 Sheet ID 列表
    }
    final_status = "failed"
    error_msg: Optional[str] = None

    # 开始事件（前端用来定位 user_message）
    yield f"event: user_message_saved\ndata: {json.dumps({'message_id': user_msg_id}, ensure_ascii=False)}\n\n"

    async for chunk in qa_pipeline.run_pipeline(ctx):
        yield chunk
        event_name, data_obj = _parse_sse_chunk(chunk)
        if event_name == "module_plan":
            last_state["think_content"] = data_obj.get("think_content") or ""
            last_state["relevant_sheet_ids"] = data_obj.get("relevant_sheet_ids") or []
        elif event_name == "plan":
            last_state["plan_summary"] = data_obj.get("plan_summary") or ""
            last_state["subquestions"] = [
                {
                    "id": s.get("id") or "",
                    "question": s.get("question") or "",
                    "purpose": s.get("purpose") or "",
                    "sql": "",
                    "sql_status": "pending",
                    "columns": [],
                    "rows": [],
                    "total_rows": 0,
                    "error": None,
                }
                for s in (data_obj.get("subquestions") or [])
            ]
        elif event_name == "sql":
            _update_subq(last_state, data_obj.get("subquestion_id"), sql=data_obj.get("sql"))
        elif event_name == "sql_result":
            _update_subq(
                last_state,
                data_obj.get("subquestion_id"),
                sql_status=data_obj.get("sql_status") or "ok",
                columns=data_obj.get("columns"),
                rows=data_obj.get("rows"),
                total_rows=data_obj.get("total_rows"),
                error=data_obj.get("error"),
            )
        elif event_name == "chart":
            # 多图结构：data_obj = { primary_id, charts: [...], chart: <primary> }
            if isinstance(data_obj, dict):
                charts_list = data_obj.get("charts") or []
                last_state["charts"] = charts_list
                last_state["primary_chart_id"] = data_obj.get("primary_id")
                last_state["chart"] = data_obj.get("chart") or (charts_list[0] if charts_list else None)
        elif event_name == "summary":
            last_state["summary_markdown"] = data_obj.get("summary_markdown") or ""
            last_state["follow_up_questions"] = list(data_obj.get("follow_up_questions") or [])
        elif event_name == "done":
            final_state = (data_obj or {}).get("state") or last_state
            last_state = final_state
            final_status = "ok"
        elif event_name == "error":
            error_msg = (data_obj or {}).get("message") or "pipeline error"
            final_status = "failed"

    # 持久化 assistant 消息，并把真实 id 回传给前端（便于前端把 tmp id 替换成真实 id，
    # 从而后续可以选中/导出 PPT——否则会一直处于"临时消息"状态）
    try:
        assistant_msg = XlsxQaRepository.create_message(
            db,
            conversation_id=conv.id,
            role="assistant",
            content=last_state.get("summary_markdown") or (error_msg or ""),
            status=final_status if final_status in ("ok", "failed", "partial") else "partial",
            extras_json=last_state,
        )
        conv.updated_at = _dt.datetime.utcnow()
        db.commit()
        yield (
            "event: assistant_message_saved\n"
            f"data: {json.dumps({'message_id': assistant_msg.id, 'status': assistant_msg.status}, ensure_ascii=False)}\n\n"
        )
    except Exception as e:  # noqa: BLE001
        logger.exception("xlsx_qa persist assistant message failed: %s", e)
        db.rollback()


def _parse_sse_chunk(chunk: str) -> Tuple[str, Optional[Dict]]:
    """把一个 `event: x\ndata: {...}\n\n` 块拆回 (event_name, data_obj)。"""
    event_name = ""
    data_str = ""
    for line in chunk.splitlines():
        if line.startswith("event: "):
            event_name = line[7:].strip()
        elif line.startswith("data: "):
            data_str = line[6:]
    if not data_str:
        return event_name, None
    try:
        return event_name, json.loads(data_str)
    except json.JSONDecodeError:
        return event_name, None


def _update_subq(state: Dict, sq_id: Optional[str], **fields) -> None:
    if not sq_id:
        return
    for s in state.get("subquestions") or []:
        if s.get("id") == sq_id:
            for k, v in fields.items():
                if v is None:
                    continue
                s[k] = v
            return


# ---------------------------------------------------------------------------
# 会话导出 PPT
# ---------------------------------------------------------------------------

def export_conversation_ppt_service(
    db: Session,
    conv_id: int,
    body: XlsxQaExportPptRequest,
) -> Tuple[bytes, str]:
    """返回 (pptx bytes, 建议文件名)."""
    conv = XlsxQaRepository.get_conversation(db, conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")
    module = XlsxQaRepository.get_module(db, conv.module_id)
    if not module:
        raise HTTPException(status_code=404, detail="模块不存在")
    doc = XlsxQaRepository.get_primary_document(db, conv.module_id)

    picked, messages = _select_ppt_messages(db, module, conv_id, body.message_ids)

    opts = ppt_exporter.PptExportOptions(
        include_subquestions=bool(body.include_subquestions),
        include_sql=bool(body.include_sql),
        include_chart=bool(body.include_chart),
        template_id=body.template_id or "executive",
    )

    data = ppt_exporter.build_pptx(
        module_name=module.name,
        conversation_title=conv.title or "未命名会话",
        file_name=doc.file_name if doc else None,
        author=module.owner_display_name or "AutoBI",
        messages=messages,
        options=opts,
        db=db,
    )
    return data, _ppt_export_download_filename()


def export_conversation_pdf_service(
    db: Session,
    conv_id: int,
    body: XlsxQaExportPptRequest,
    *,
    author: Optional[str] = None,
) -> Tuple[bytes, str]:
    """返回 (pdf bytes, 建议文件名)。"""
    conv = XlsxQaRepository.get_conversation(db, conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")
    module = XlsxQaRepository.get_module(db, conv.module_id)
    if not module:
        raise HTTPException(status_code=404, detail="模块不存在")
    doc = XlsxQaRepository.get_primary_document(db, conv.module_id)
    _picked, messages = _select_ppt_messages(db, module, conv_id, body.message_ids, skip_insights=True)
    data = pdf_exporter.build_qa_pdf(
        module_name=module.name or "",
        conversation_title=conv.title or "未命名会话",
        file_name=doc.file_name if doc else None,
        author=author or module.owner_display_name or "AutoBI",
        messages=messages,
    )
    return data, _pdf_export_download_filename("xlsx数据问答报告")


def export_insight_pdf_service(
    db: Session,
    module_id: int,
    *,
    author: Optional[str] = None,
) -> Tuple[bytes, str]:
    module = XlsxQaRepository.get_module(db, module_id)
    if not module:
        raise HTTPException(status_code=404, detail="模块不存在")
    row = XlsxQaRepository.get_insight_report(db, module_id)
    if not row:
        raise HTTPException(status_code=400, detail="请先生成数据洞察报告")
    report = _insight_report_out(row)
    if report.get("status") != "done":
        raise HTTPException(status_code=400, detail="数据洞察报告尚未生成完成")
    data = pdf_exporter.build_insight_pdf(
        module_name=module.name or "",
        author=author or module.owner_display_name or "AutoBI",
        report=report,
    )
    return data, _pdf_export_download_filename("xlsx数据洞察报告")


def export_insight_ppt_service(
    db: Session,
    module_id: int,
    *,
    author: Optional[str] = None,
    logo_bytes: Optional[bytes] = None,
) -> Tuple[bytes, str]:
    module = XlsxQaRepository.get_module(db, module_id)
    if not module:
        raise HTTPException(status_code=404, detail="模块不存在")
    row = XlsxQaRepository.get_insight_report(db, module_id)
    if not row:
        raise HTTPException(status_code=400, detail="请先生成数据洞察报告")
    report = _insight_report_out(row)
    if report.get("status") != "done":
        raise HTTPException(status_code=400, detail="数据洞察报告尚未生成完成")
    now = _dt.datetime.now()
    data = ppt_exporter.build_insight_custom_pptx(
        module_name=module.name or "",
        author=author or module.owner_display_name or "AutoBI",
        generated_at=now,
        report=report,
        logo_bytes=logo_bytes,
    )
    return data, _ppt_export_download_filename(now)


def export_conversation_custom_ppt_service(
    db: Session,
    conv_id: int,
    body: XlsxQaExportPptRequest,
    *,
    author: Optional[str] = None,
    logo_bytes: Optional[bytes] = None,
) -> Tuple[bytes, str]:
    """专属定制版 PPT 导出。旧模板导出不走这里。"""
    conv = XlsxQaRepository.get_conversation(db, conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")
    module = XlsxQaRepository.get_module(db, conv.module_id)
    if not module:
        raise HTTPException(status_code=404, detail="模块不存在")
    doc = XlsxQaRepository.get_primary_document(db, conv.module_id)

    picked, messages = _select_ppt_messages(db, module, conv_id, body.message_ids, skip_insights=True)
    assistant_count = sum(1 for m in picked if m.role == "assistant")
    if assistant_count > 5:
        raise HTTPException(status_code=400, detail="专属定制 PPT 最多支持选择 5 个问题")
    _attach_custom_ppt_digests_sync(db, module, picked, messages)

    opts = ppt_exporter.PptExportOptions(
        include_subquestions=bool(body.include_subquestions),
        include_sql=bool(body.include_sql),
        include_chart=bool(body.include_chart),
        template_id="custom_med",
    )
    now = _dt.datetime.now()
    data = ppt_exporter.build_custom_sales_pptx(
        module_name=module.name,
        conversation_title=conv.title or "未命名会话",
        file_name=doc.file_name if doc else None,
        author=author or module.owner_display_name or "AutoBI",
        generated_at=now,
        messages=messages,
        options=opts,
        logo_bytes=logo_bytes,
    )
    return data, _ppt_export_download_filename(now)


# ---------------------------------------------------------------------------
# 异步 PPT 导出（后台线程 + OSS 存储 + 进度追踪）
# ---------------------------------------------------------------------------

_PROGRESS_UI_MIN_INTERVAL_SEC = 1.0


class _ProgressTracker:
    """PPT 导出进度追踪器，定期将状态写入 DB。"""

    def __init__(self, db: Session, history_id: int) -> None:
        self._db = db
        self._history_id = history_id
        self._messages: List[str] = []
        self._last_commit_mono: float = 0.0

    def update(self, message: str) -> None:
        now_mono = time.monotonic()
        if self._last_commit_mono > 0:
            gap = _PROGRESS_UI_MIN_INTERVAL_SEC - (now_mono - self._last_commit_mono)
            if gap > 0:
                time.sleep(gap)
        self._messages.append(message)
        if len(self._messages) > 10:
            self._messages = self._messages[-10:]
        XlsxQaRepository.update_ppt_history(
            self._db, self._history_id,
            status_message=message,
            progress_messages_json=self._messages,
        )
        try:
            self._db.commit()
        except Exception:
            self._db.rollback()
        self._last_commit_mono = time.monotonic()


def start_ppt_export_async(
    db: Session,
    conv_id: int,
    body: XlsxQaExportPptRequest,
    *,
    author: Optional[str] = None,
    logo_bytes: Optional[bytes] = None,
    is_custom: bool = False,
) -> XlsxQaPptHistory:
    """启动异步 PPT 导出，立即返回 history 记录。"""
    conv = XlsxQaRepository.get_conversation(db, conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")
    module = XlsxQaRepository.get_module(db, conv.module_id)
    if not module:
        raise HTTPException(status_code=404, detail="模块不存在")

    template_id = body.template_id or ("custom_med" if is_custom else "executive")

    history = XlsxQaRepository.create_ppt_history(
        db,
        module_id=conv.module_id,
        conversation_id=conv_id,
        conversation_title=conv.title or "未命名会话",
        template_id=template_id,
        status="generating",
        status_message="准备导出...",
        options_json={"message_ids": body.message_ids, "include_subquestions": body.include_subquestions, "include_chart": body.include_chart, "template_id": template_id},
    )
    db.commit()
    history_id = history.id

    def _run_export() -> None:
        _do_export_async(history_id, conv_id, body, author=author, logo_bytes=logo_bytes, is_custom=is_custom)

    thread = threading.Thread(target=_run_export, daemon=True)
    thread.start()

    return history


def start_insight_ppt_export_async(
    db: Session,
    module_id: int,
    *,
    author: Optional[str] = None,
    logo_bytes: Optional[bytes] = None,
) -> XlsxQaPptHistory:
    module = XlsxQaRepository.get_module(db, module_id)
    if not module:
        raise HTTPException(status_code=404, detail="模块不存在")
    row = XlsxQaRepository.get_insight_report(db, module_id)
    if not row:
        raise HTTPException(status_code=400, detail="请先生成数据洞察报告")
    if (row.status or "") != "done":
        raise HTTPException(status_code=400, detail="数据洞察报告尚未生成完成")

    anchor_conv = _get_or_create_insight_export_conversation(db, module_id)
    history = XlsxQaRepository.create_ppt_history(
        db,
        module_id=module_id,
        conversation_id=anchor_conv.id,
        conversation_title="数据深度洞察报告",
        template_id="custom_med_insight",
        status="generating",
        status_message="准备导出洞察 PPT...",
        options_json={"report_type": "insight", "template_id": "custom_med_insight"},
    )
    db.commit()
    history_id = history.id

    def _run_export() -> None:
        _do_insight_ppt_export_async(history_id, module_id, author=author, logo_bytes=logo_bytes)

    thread = threading.Thread(target=_run_export, daemon=True)
    thread.start()
    return history


def _get_or_create_insight_export_conversation(db: Session, module_id: int) -> XlsxQaConversation:
    convs = XlsxQaRepository.list_conversations(db, module_id)
    for conv in convs:
        if conv.title == "数据深度洞察报告":
            return conv
    if convs:
        return convs[0]
    return XlsxQaRepository.create_conversation(db, module_id, "数据深度洞察报告")


def _do_export_async(
    history_id: int,
    conv_id: int,
    body: XlsxQaExportPptRequest,
    *,
    author: Optional[str] = None,
    logo_bytes: Optional[bytes] = None,
    is_custom: bool = False,
) -> None:
    db = SessionLocal()
    try:
        progress = _ProgressTracker(db, history_id)
        progress.update("正在准备导出数据...")

        conv = XlsxQaRepository.get_conversation(db, conv_id)
        if not conv:
            _fail_history(db, history_id, "会话不存在")
            return
        module = XlsxQaRepository.get_module(db, conv.module_id)
        if not module:
            _fail_history(db, history_id, "模块不存在")
            return
        doc = XlsxQaRepository.get_primary_document(db, conv.module_id)

        progress.update("正在分析对话内容...")
        picked, messages = _select_ppt_messages(db, module, conv_id, body.message_ids or None, skip_insights=is_custom)

        progress.update("正在生成 PPT 封面...")
        opts = ppt_exporter.PptExportOptions(
            include_subquestions=bool(body.include_subquestions),
            include_sql=False,
            include_chart=bool(body.include_chart),
            template_id=body.template_id or ("custom_med" if is_custom else "executive"),
        )

        progress.update("正在解析数据洞察...")
        now = _dt.datetime.now()
        if is_custom:
            assistant_count = sum(1 for m in picked if m.role == "assistant")
            if assistant_count > 5:
                _fail_history(db, history_id, "专属定制 PPT 最多支持 5 个问题")
                return
            _attach_custom_ppt_digests_sync(db, module, picked, messages)
            ppt_data = ppt_exporter.build_custom_sales_pptx(
                module_name=module.name,
                conversation_title=conv.title or "未命名会话",
                file_name=doc.file_name if doc else None,
                author=author or module.owner_display_name or "AutoBI",
                generated_at=now,
                messages=messages,
                options=opts,
                logo_bytes=logo_bytes,
            )
        else:
            progress.update("正在构建 PPT 内容...")
            ppt_data = ppt_exporter.build_pptx(
                module_name=module.name,
                conversation_title=conv.title or "未命名会话",
                file_name=doc.file_name if doc else None,
                author=author or module.owner_display_name or "AutoBI",
                messages=messages,
                options=opts,
                db=db,
            )

        progress.update("正在上传到存储...")
        from ..oss.client import resolve_active_storage
        oss_storage = resolve_active_storage(db, module.space_id)
        if oss_storage is None:
            _fail_history(db, history_id, "OSS 未配置，请前往「管理中心 → 对象存储」进行配置")
            return
        client_name = _ppt_export_download_filename(_dt.datetime.now())
        oss_key = oss_storage.build_ppt_file_key(conv.module_id, client_name)
        oss_storage.put_bytes(
            oss_key, ppt_data,
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        )

        progress.update("导出完成")
        XlsxQaRepository.update_ppt_history(
            db, history_id,
            status="ready",
            status_message="导出完成",
            oss_object_key=oss_key,
            file_size=len(ppt_data),
        )
        db.commit()
    except Exception as e:
        logger.exception("PPT export async failed: history_id=%s", history_id)
        try:
            _fail_history(db, history_id, str(e))
        except Exception:
            pass
    finally:
        db.close()


def _do_insight_ppt_export_async(
    history_id: int,
    module_id: int,
    *,
    author: Optional[str] = None,
    logo_bytes: Optional[bytes] = None,
) -> None:
    db = SessionLocal()
    try:
        progress = _ProgressTracker(db, history_id)
        progress.update("正在读取深度洞察报告...")

        module = XlsxQaRepository.get_module(db, module_id)
        if not module:
            _fail_history(db, history_id, "模块不存在")
            return
        row = XlsxQaRepository.get_insight_report(db, module_id)
        if not row:
            _fail_history(db, history_id, "请先生成数据洞察报告")
            return
        report = _insight_report_out(row)
        if report.get("status") != "done":
            _fail_history(db, history_id, "数据洞察报告尚未生成完成")
            return

        progress.update("正在生成洞察PPT文案...")
        digests = _attach_insight_ppt_digests_sync(
            db, module,
            dimensions=report.get("dimensions") or [],
            evidence=report.get("evidence") or {},
            dim_texts=report.get("dim_texts") or {},
            final_md=str(report.get("final_md") or ""),
        )
        chart_failures = (digests or {}).get("chart_failures") or []
        if chart_failures:
            progress.update(f"有 {len(chart_failures)} 个图表文案生成失败，已使用图表数据兜底...")
        progress.update("正在整理维度结论和证据...")
        now = _dt.datetime.now()
        ppt_data = ppt_exporter.build_insight_custom_pptx(
            module_name=module.name or "",
            author=author or module.owner_display_name or "AutoBI",
            generated_at=now,
            report=report,
            logo_bytes=logo_bytes,
            digests=digests,
        )

        progress.update("正在上传到存储...")
        from ..oss.client import resolve_active_storage
        oss_storage = resolve_active_storage(db, module.space_id)
        if oss_storage is None:
            _fail_history(db, history_id, "OSS 未配置，请前往「管理中心 → 对象存储」进行配置")
            return
        client_name = _ppt_export_download_filename(now)
        oss_key = oss_storage.build_ppt_file_key(module_id, client_name)
        oss_storage.put_bytes(
            oss_key,
            ppt_data,
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        )

        progress.update("导出完成")
        XlsxQaRepository.update_ppt_history(
            db,
            history_id,
            status="ready",
            status_message="导出完成",
            oss_object_key=oss_key,
            file_size=len(ppt_data),
        )
        db.commit()
    except Exception as e:
        logger.exception("Insight PPT export async failed: history_id=%s", history_id)
        try:
            _fail_history(db, history_id, str(e))
        except Exception:
            pass
    finally:
        db.close()


def _fail_history(db: Session, history_id: int, error: str) -> None:
    XlsxQaRepository.update_ppt_history(
        db, history_id,
        status="failed",
        error_message=error,
        status_message="导出失败",
    )
    try:
        db.commit()
    except Exception:
        db.rollback()


# ---------------------------------------------------------------------------
# 模块 Logo CRUD
# ---------------------------------------------------------------------------

def upload_module_logo_service(db: Session, module_id: int, file: UploadFile) -> dict:
    m = XlsxQaRepository.get_module(db, module_id)
    if not m:
        raise HTTPException(status_code=404, detail="模块不存在")

    content = file.file.read()
    if len(content) > 2 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Logo 文件不能超过 2MB")

    content_type = file.content_type or "image/png"
    if content_type not in {"image/png", "image/jpeg", "image/jpg"}:
        raise HTTPException(status_code=400, detail="Logo 仅支持 PNG/JPG")

    from ..oss.client import resolve_active_storage
    oss_storage = resolve_active_storage(db, m.space_id)
    if oss_storage is None:
        raise HTTPException(status_code=503, detail="OSS 未配置，请前往「管理中心 → 对象存储」进行配置")
    old_key = (m.extra_config_json or {}).get("logo_oss_key")
    if old_key:
        try:
            oss_storage.delete_object(old_key)
        except Exception:
            logger.warning("Failed to delete old logo key=%s", old_key)

    ext = "png" if "png" in content_type else "jpg"
    oss_key = oss_storage.build_module_logo_key(module_id, f"logo.{ext}")
    oss_storage.put_bytes(oss_key, content, content_type)

    cfg = dict(m.extra_config_json or {})
    cfg["logo_oss_key"] = oss_key
    m.extra_config_json = cfg
    db.commit()
    return {"logo_oss_key": oss_key}


def get_module_logo_url_service(db: Session, module_id: int) -> Optional[str]:
    m = XlsxQaRepository.get_module(db, module_id)
    if not m:
        raise HTTPException(status_code=404, detail="模块不存在")
    oss_key = (m.extra_config_json or {}).get("logo_oss_key")
    if not oss_key:
        return None
    from ..oss.client import resolve_active_storage
    oss_storage = resolve_active_storage(db, m.space_id)
    if oss_storage is None:
        return None
    return oss_storage.generate_presigned_url(oss_key, expires=3600)


def delete_module_logo_service(db: Session, module_id: int) -> None:
    m = XlsxQaRepository.get_module(db, module_id)
    if not m:
        raise HTTPException(status_code=404, detail="模块不存在")
    oss_key = (m.extra_config_json or {}).get("logo_oss_key")
    if oss_key:
        from ..oss.client import resolve_active_storage
        oss_storage = resolve_active_storage(db, m.space_id)
        if oss_storage is not None:
            try:
                oss_storage.delete_object(oss_key)
            except Exception:
                logger.warning("Failed to delete module logo key=%s", oss_key)
    cfg = dict(m.extra_config_json or {})
    cfg.pop("logo_oss_key", None)
    m.extra_config_json = cfg or None
    db.commit()


# ---------------------------------------------------------------------------
# PPT 导出历史 CRUD
# ---------------------------------------------------------------------------

def list_ppt_history_service(db: Session, module_id: int) -> List[dict]:
    rows = XlsxQaRepository.list_ppt_history_for_module(db, module_id)
    return [
        {
            "id": r.id,
            "module_id": r.module_id,
            "conversation_id": r.conversation_id,
            "conversation_title": r.conversation_title,
            "template_id": r.template_id,
            "status": r.status,
            "status_message": r.status_message,
            "progress_messages": r.progress_messages_json or [],
            "error_message": r.error_message,
            "file_size": r.file_size,
            "created_at": _fmt_dt(r.created_at),
            "updated_at": _fmt_dt(r.updated_at),
        }
        for r in rows
    ]


def ppt_history_download_service(db: Session, history_id: int) -> XlsxQaDownloadOut:
    row = XlsxQaRepository.get_ppt_history(db, history_id)
    if not row:
        raise HTTPException(status_code=404, detail="记录不存在")
    if row.status != "ready" or not row.oss_object_key:
        raise HTTPException(status_code=400, detail="PPT 尚未生成完成")
    m = XlsxQaRepository.get_module(db, row.module_id)
    from ..oss.client import resolve_active_storage
    oss_storage = resolve_active_storage(db, m.space_id if m else None)
    if oss_storage is None:
        raise HTTPException(status_code=503, detail="OSS 未配置，请前往「管理中心 → 对象存储」进行配置")
    url = oss_storage.generate_presigned_url(row.oss_object_key)
    return XlsxQaDownloadOut(url=url, expires_in=oss_storage.default_expires)


def delete_ppt_history_service(db: Session, history_id: int) -> None:
    row = XlsxQaRepository.get_ppt_history(db, history_id)
    if not row:
        raise HTTPException(status_code=404, detail="记录不存在")
    if row.oss_object_key:
        m = XlsxQaRepository.get_module(db, row.module_id)
        from ..oss.client import resolve_active_storage
        oss_storage = resolve_active_storage(db, m.space_id if m else None)
        if oss_storage is not None:
            try:
                oss_storage.delete_object(row.oss_object_key)
            except Exception:
                logger.warning("Failed to delete ppt history OSS key=%s", row.oss_object_key)
    XlsxQaRepository.delete_ppt_history(db, history_id)
    db.commit()


_UNSAFE_FS_RE = __import__("re").compile(r"[\\/:*?\"<>|\s]+")


def _safe_filename(s: str) -> str:
    s = (s or "conversation").strip()
    s = _UNSAFE_FS_RE.sub("_", s)
    return s[:60] or "conversation"


def _ppt_export_download_filename(at: Optional[_dt.datetime] = None) -> str:
    """PPT 导出在用户下载 / OSS 展示中使用的文件名（Office 实际为 pptx 容器）。"""
    t = at or _dt.datetime.now()
    return f"xlsx数据洞察报告_{t.strftime('%Y%m%d%H%M%S')}.pptx"


def _pdf_export_download_filename(prefix: str, at: Optional[_dt.datetime] = None) -> str:
    t = at or _dt.datetime.now()
    return f"{prefix}_{t.strftime('%Y%m%d%H%M%S')}.pdf"


def _select_ppt_messages(
    db: Session,
    module: XlsxQaModule,
    conv_id: int,
    message_ids: Optional[List[int]],
    *,
    custom_digest: bool = False,
    skip_insights: bool = False,
) -> Tuple[List[XlsxQaMessage], List[ppt_exporter.PptMessage]]:
    all_rows = XlsxQaRepository.list_messages(db, conv_id)
    if not all_rows:
        raise HTTPException(status_code=400, detail="会话还没有消息，无法导出")

    want_ids = set(message_ids or [])
    if want_ids:
        selected_ids: set[int] = set()
        for i, m in enumerate(all_rows):
            if m.role == "assistant" and m.id in want_ids:
                selected_ids.add(m.id)
                for j in range(i - 1, -1, -1):
                    if all_rows[j].role == "user":
                        selected_ids.add(all_rows[j].id)
                        break
            elif m.role == "user" and m.id in want_ids:
                selected_ids.add(m.id)
        picked = [m for m in all_rows if m.id in selected_ids]
    else:
        picked = list(all_rows)

    if not any(m.role == "assistant" for m in picked):
        raise HTTPException(status_code=400, detail="未勾选任何 AI 回复，无法导出")

    messages = [
        _message_to_ppt_message(db, module, picked, idx, m, custom_digest=custom_digest, skip_insights=skip_insights)
        for idx, m in enumerate(picked)
    ]
    return picked, messages


def _message_to_ppt_message(
    db: Session,
    module: XlsxQaModule,
    rows: List[XlsxQaMessage],
    idx: int,
    msg: XlsxQaMessage,
    *,
    custom_digest: bool = False,
    skip_insights: bool = False,
) -> ppt_exporter.PptMessage:
    extras = dict(msg.extras_json or {}) if isinstance(msg.extras_json, dict) else None
    if msg.role == "assistant" and extras is not None:
        question = ""
        for j in range(idx - 1, -1, -1):
            if rows[j].role == "user":
                question = rows[j].content or ""
                break
        if not skip_insights:
            insights = _generate_ppt_insights_sync(db, module, question, msg.content or "", extras)
            if insights:
                extras["__ppt_insights"] = insights
        if custom_digest:
            digest = _generate_custom_ppt_digest_sync(db, module, question, msg.content or "", extras)
            if digest:
                extras["__custom_digest"] = digest
    return ppt_exporter.PptMessage(
        role=msg.role,
        content=msg.content or "",
        extras=extras,
        created_at=_fmt_dt(msg.created_at),
    )


def _generate_ppt_insights_sync(
    db: Session,
    module: XlsxQaModule,
    question: str,
    content: str,
    extras: dict,
) -> Optional[dict]:
    try:
        try:
            _asyncio_mod.get_running_loop()
            logger.warning("xlsx_qa.ppt_insights skipped: running event loop in current thread")
            return None
        except RuntimeError:
            pass
        return _asyncio_mod.run(_generate_ppt_insights(db, module, question, content, extras))
    except RuntimeError as e:
        logger.warning("xlsx_qa.ppt_insights skipped: event loop unavailable: %s", e)
        return None
    except Exception as e:  # noqa: BLE001
        logger.warning("xlsx_qa.ppt_insights failed: %s", e)
        return None


def _generate_custom_ppt_digest_sync(
    db: Session,
    module: XlsxQaModule,
    question: str,
    content: str,
    extras: dict,
) -> Optional[dict]:
    try:
        try:
            _asyncio_mod.get_running_loop()
            logger.warning("xlsx_qa.custom_ppt_digest skipped: running event loop in current thread")
            return None
        except RuntimeError:
            pass
        return _asyncio_mod.run(_generate_custom_ppt_digest(db, module, question, content, extras))
    except RuntimeError as e:
        logger.warning("xlsx_qa.custom_ppt_digest skipped: event loop unavailable: %s", e)
        return None
    except Exception as e:  # noqa: BLE001
        logger.warning("xlsx_qa.custom_ppt_digest failed: %s", e)
        return None


def _attach_custom_ppt_digests_sync(
    db: Session,
    module: XlsxQaModule,
    rows: List[XlsxQaMessage],
    messages: List[ppt_exporter.PptMessage],
) -> None:
    try:
        try:
            _asyncio_mod.get_running_loop()
            logger.warning("xlsx_qa.custom_ppt_digest parallel skipped: running event loop in current thread")
            return
        except RuntimeError:
            pass
        digests = _asyncio_mod.run(_generate_custom_ppt_digests_parallel(db, module, rows))
    except Exception as e:  # noqa: BLE001
        logger.warning("xlsx_qa.custom_ppt_digest parallel failed: %s", e)
        return
    for idx, digest in digests.items():
        if not digest or idx >= len(messages):
            continue
        extras = dict(messages[idx].extras or {})
        extras["__custom_digest"] = digest
        messages[idx].extras = extras


async def _generate_custom_ppt_digests_parallel(
    db: Session,
    module: XlsxQaModule,
    rows: List[XlsxQaMessage],
) -> Dict[int, dict]:
    try:
        choice = llm_client.resolve_llm(
            db,
            provider_id=module.llm_provider_id,
            model=module.llm_model,
        )
    except Exception as e:
        logger.warning("xlsx_qa.custom_ppt_digest resolve_llm failed: %s", e)
        return {}

    tasks = []
    positions = []
    for idx, msg in enumerate(rows):
        if msg.role != "assistant":
            continue
        extras = dict(msg.extras_json or {}) if isinstance(msg.extras_json, dict) else {}
        question = ""
        for j in range(idx - 1, -1, -1):
            if rows[j].role == "user":
                question = rows[j].content or ""
                break
        positions.append(idx)
        tasks.append(_generate_custom_ppt_digest_with_choice(choice, module, question, msg.content or "", extras))
    if not tasks:
        return {}
    results = await _asyncio_mod.gather(*tasks, return_exceptions=True)
    out: Dict[int, dict] = {}
    for idx, result in zip(positions, results):
        if isinstance(result, Exception):
            logger.warning("xlsx_qa.custom_ppt_digest item failed: %s", result)
            continue
        if result:
            out[idx] = result
    return out


async def _generate_ppt_insights(
    db: Session,
    module: XlsxQaModule,
    question: str,
    content: str,
    extras: dict,
) -> Optional[dict]:
    try:
        choice = llm_client.resolve_llm(
            db,
            provider_id=module.llm_provider_id,
            model=module.llm_model,
        )
    except Exception as e:
        logger.warning("xlsx_qa.ppt_insights resolve_llm failed: %s", e)
        return None

    charts = _compact_ppt_charts(extras.get("charts") or ([extras.get("chart")] if extras.get("chart") else []))
    subqs = _compact_ppt_subquestions(extras.get("subquestions") or [])
    payload = {
        "module": module.name,
        "question": question,
        "final_answer_markdown": extras.get("summary_markdown") or content or "",
        "charts": charts,
        "result_tables": subqs,
    }
    try:
        obj = await llm_client.chat_json(
            choice,
            system=prompts_mod.PPT_INSIGHT_SYSTEM,
            user=json.dumps(payload, ensure_ascii=False, default=str),
            temperature=0.25,
            max_tokens=1800,
            timeout=90.0,
        )
    except Exception as e:
        logger.warning("xlsx_qa.ppt_insights LLM call failed: %s", e)
        return None
    sections = obj.get("sections") if isinstance(obj, dict) else None
    if not isinstance(sections, list):
        return None
    cleaned = []
    for sec in sections[:5]:
        if not isinstance(sec, dict):
            continue
        cleaned.append({
            "title": str(sec.get("title") or "关键洞察")[:80],
            "visual_type": str(sec.get("visual_type") or "none")[:20],
            "chart_id": sec.get("chart_id"),
            "axis_note": str(sec.get("axis_note") or "")[:200],
            "conclusion": str(sec.get("conclusion") or "")[:300],
            "bullets": [str(x)[:180] for x in (sec.get("bullets") or [])[:4]],
        })
    return {"sections": cleaned} if cleaned else None


async def _generate_custom_ppt_digest(
    db: Session,
    module: XlsxQaModule,
    question: str,
    content: str,
    extras: dict,
) -> Optional[dict]:
    try:
        choice = llm_client.resolve_llm(
            db,
            provider_id=module.llm_provider_id,
            model=module.llm_model,
        )
    except Exception as e:
        logger.warning("xlsx_qa.custom_ppt_digest resolve_llm failed: %s", e)
        return None
    return await _generate_custom_ppt_digest_with_choice(choice, module, question, content, extras)


async def _generate_custom_ppt_digest_with_choice(
    choice,
    module: XlsxQaModule,
    question: str,
    content: str,
    extras: dict,
) -> Optional[dict]:
    charts = _compact_ppt_charts(extras.get("charts") or ([extras.get("chart")] if extras.get("chart") else []))
    payload = {
        "module": module.name,
        "question": question,
        "final_answer_markdown": extras.get("summary_markdown") or content or "",
        "charts": charts,
        "result_tables": _compact_ppt_subquestions(extras.get("subquestions") or []),
    }
    try:
        obj = await llm_client.chat_json(
            choice,
            system=prompts_mod.PPT_CUSTOM_DIGEST_SYSTEM,
            user=json.dumps(payload, ensure_ascii=False, default=str),
            temperature=0.2,
            max_tokens=6000,
            timeout=90.0,
        )
    except Exception as e:
        logger.warning("xlsx_qa.custom_ppt_digest LLM call failed: %s", e)
        return None
    if not isinstance(obj, dict):
        return None
    summary = obj.get("summary") if isinstance(obj.get("summary"), dict) else {}
    chart_summaries = obj.get("chart_summaries") if isinstance(obj.get("chart_summaries"), list) else []
    return {
        "question_short": str(obj.get("question_short") or "")[:10],
        "summary": {
            "title": str(summary.get("title") or "")[:10],
            "description": str(summary.get("description") or "")[:320],
            "points": [str(x)[:320] for x in (summary.get("points") or [])[:4]],
            "conclusion": str(summary.get("conclusion") or "")[:320],
        },
        "chart_summaries": [
            {
                "chart_id": str(item.get("chart_id") or ""),
                "title": str(item.get("title") or "")[:12],
                "description": str(item.get("description") or "")[:150],
                "analysis": str(item.get("analysis") or "")[:480],
                "cards": [
                    {
                        "title": str(card.get("title") or "")[:8],
                        "body": str(card.get("body") or "")[:160],
                    }
                    for card in (item.get("cards") or [])[:3]
                    if isinstance(card, dict)
                ],
                "points": [str(x)[:60] for x in (item.get("points") or [])[:3]],
                "conclusion": str(item.get("conclusion") or "")[:90],
            }
            for item in chart_summaries[:8]
            if isinstance(item, dict)
        ],
    }


# ---------------------------------------------------------------------------
# Insight PPT digest generation (model-driven, parallel)
# ---------------------------------------------------------------------------

def _compact_insight_evidence(evs: List[Any]) -> List[dict]:
    """与 ppt_exporter._insight_ordered_evidence_visuals 完全一致：仅含可出页的图/表，顺序与 PPT 逐页对齐。"""
    visuals = ppt_exporter._insight_ordered_evidence_visuals(evs)
    out: List[dict] = []
    for v in visuals:
        cid = str(v.get("subquestion_id") or "").strip()
        out.append({
            "business_question": str(v.get("title") or ""),
            "purpose": str(v.get("explain") or ""),
            "chart": {
                "chart_id": cid,
                "title": str(v.get("title") or ""),
                "chart_type": str(v.get("chart_type") or "table"),
                "columns": v.get("columns") or [],
                "rows": (v.get("rows") or [])[:10],
            },
        })
    return out


def _to_float_or_none(v: Any) -> Optional[float]:
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    s = str(v).strip().replace(",", "")
    if s.endswith("%"):
        s = s[:-1]
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def _insight_chart_data_profile(chart: dict) -> dict:
    columns = list((chart or {}).get("columns") or [])
    rows = list((chart or {}).get("rows") or [])
    numeric_columns: List[dict] = []
    for col_idx, col in enumerate(columns[:12]):
        vals: List[float] = []
        for row in rows:
            if not isinstance(row, (list, tuple)) or col_idx >= len(row):
                continue
            num = _to_float_or_none(row[col_idx])
            if num is not None:
                vals.append(num)
        if not vals:
            continue
        numeric_columns.append({
            "column": col,
            "count": len(vals),
            "min": min(vals),
            "max": max(vals),
            "sum": sum(vals),
            "avg": sum(vals) / len(vals),
        })
        if len(numeric_columns) >= 6:
            break
    return {
        "row_count": len(rows),
        "column_count": len(columns),
        "columns": columns,
        "numeric_columns": numeric_columns,
        "rows_sample": rows[:30],
    }


def _compact_single_insight_chart(chart: dict) -> dict:
    cid = str((chart or {}).get("subquestion_id") or "").strip()
    return {
        "chart_id": cid,
        "title": str((chart or {}).get("title") or ""),
        "purpose": str((chart or {}).get("explain") or ""),
        "chart_type": str((chart or {}).get("chart_type") or "table"),
        "dimension_field": (chart or {}).get("dimension_field"),
        "metric_fields": (chart or {}).get("metric_fields") or [],
        "columns": (chart or {}).get("columns") or [],
        "rows_sample": ((chart or {}).get("rows") or [])[:30],
        "data_profile": _insight_chart_data_profile(chart or {}),
    }


def _fmt_profile_num(v: Any) -> str:
    num = _to_float_or_none(v)
    if num is None:
        return str(v or "")
    if abs(num) >= 1000:
        return f"{num:,.2f}".rstrip("0").rstrip(".")
    if abs(num - round(num)) < 0.000001:
        return str(int(round(num)))
    return f"{num:.2f}".rstrip("0").rstrip(".")


def _insight_chart_data_blurb_for_prompt(chart: dict) -> str:
    title = str((chart or {}).get("title") or "当前图表").strip()
    columns = list((chart or {}).get("columns") or [])
    rows = list((chart or {}).get("rows") or [])
    profile = _insight_chart_data_profile(chart or {})
    parts = [f"《{title}》包含{profile.get('row_count', len(rows))}行、{profile.get('column_count', len(columns))}列"]
    numeric = profile.get("numeric_columns") or []
    if numeric:
        n0 = numeric[0]
        parts.append(
            f"{n0.get('column')}最小值{_fmt_profile_num(n0.get('min'))}、最大值{_fmt_profile_num(n0.get('max'))}、均值{_fmt_profile_num(n0.get('avg'))}"
        )
    if rows and columns:
        row = rows[0]
        pairs = []
        if isinstance(row, (list, tuple)):
            for idx, col in enumerate(columns[:4]):
                if idx >= len(row):
                    continue
                val = row[idx]
                if val is None or val == "":
                    continue
                pairs.append(f"{col}={_fmt_profile_num(val)}")
        if pairs:
            parts.append("首行样本：" + "、".join(pairs[:4]))
    return "；".join(parts) + "。"


def _data_bound_chart_cards(chart: dict) -> List[dict]:
    columns = list((chart or {}).get("columns") or [])
    rows = list((chart or {}).get("rows") or [])
    profile = _insight_chart_data_profile(chart or {})
    title = str((chart or {}).get("title") or "当前图表").strip()
    numeric = profile.get("numeric_columns") or []

    scope = f"这张图表是「{title}」，当前可视化数据包含{len(rows)}行、{len(columns)}列"
    if columns:
        scope += f"，字段包括{'、'.join(str(c) for c in columns[:5])}"
    scope += "，分析应围绕这张表本身展开。"

    if numeric:
        metrics = []
        for n in numeric[:2]:
            metrics.append(
                f"{n.get('column')}均值{_fmt_profile_num(n.get('avg'))}，范围{_fmt_profile_num(n.get('min'))}至{_fmt_profile_num(n.get('max'))}"
            )
        metric_body = "；".join(metrics) + "。请结合维度报告判断这些指标反映的业务趋势与异常，而非仅描述数值本身。"
    else:
        metric_body = "当前表格以分类或文本字段为主，应重点观察类别、对象和字段之间的结构关系，而不是套用其他图表的数值结论。"

    if rows and columns and isinstance(rows[0], (list, tuple)):
        row = rows[0]
        pairs = []
        for idx, col in enumerate(columns[:4]):
            if idx < len(row) and row[idx] not in (None, ""):
                pairs.append(f"{col}={_fmt_profile_num(row[idx])}")
        sample_body = f"从样本看，首行呈现{'、'.join(pairs)}，可作为本页解读的具体锚点。" if pairs else scope
    else:
        sample_body = "当前图表没有足够样本行可展开细节，应以字段结构和业务问题为主进行谨慎判断。"

    return [
        {"title": "数据范围", "body": scope[:160]},
        {"title": "数值特征", "body": metric_body[:160]},
        {"title": "样本线索", "body": sample_body[:160]},
    ]


def _looks_generic_or_duplicate(cards: List[dict], seen_signatures: set[str]) -> bool:
    bodies = [str((c or {}).get("body") or "").strip() for c in cards[:3] if isinstance(c, dict)]
    joined = "|".join(bodies)
    if not joined:
        return True
    if joined in seen_signatures:
        return True
    non_empty = [b for b in bodies if b]
    return len(non_empty) >= 2 and len(set(non_empty)) == 1


def _stabilize_chart_digest_for_chart(digest: dict, chart: dict, seen_signatures: set[str]) -> dict:
    data_cards = _data_bound_chart_cards(chart)
    data_blurb = _insight_chart_data_blurb_for_prompt(chart)
    llm_cards = digest.get("cards") or []
    cards = (llm_cards if llm_cards else data_cards)
    signature = "|".join(str((c or {}).get("body") or "").strip() for c in cards[:3])
    seen_signatures.add(signature)
    analysis = str(digest.get("analysis") or "").strip() or data_blurb

    llm_analysis_raw = str(digest.get("analysis") or "").strip()
    llm_cards_raw = digest.get("cards") or []
    logger.info(
        "xlsx_qa.stabilize_chart_digest chart=%s llm_analysis_len=%d llm_cards_count=%d "
        "using_llm_analysis=%s using_llm_cards=%s data_blurb_len=%d final_analysis_preview=%s",
        digest.get("chart_id"),
        len(llm_analysis_raw), len(llm_cards_raw),
        bool(llm_analysis_raw), bool(llm_cards_raw),
        len(data_blurb),
        analysis[:120],
    )

    out = dict(digest)
    out["analysis"] = analysis[:480]
    out["cards"] = cards[:3]
    return out


async def _generate_insight_dim_ppt_digest(choice, dim_item: dict) -> Optional[dict]:
    markdown = str(dim_item.get("markdown") or "").strip()
    evidence = _compact_insight_evidence(dim_item.get("evidence") or [])
    if not markdown and not evidence:
        return None
    payload = {
        "dimension_title": dim_item.get("title") or "",
        "markdown": markdown,
        "evidence_overview": [
            {
                "business_question": ev.get("business_question"),
                "purpose": ev.get("purpose"),
                "chart_id": ((ev.get("chart") or {}).get("chart_id")),
                "chart_type": ((ev.get("chart") or {}).get("chart_type")),
                "columns": ((ev.get("chart") or {}).get("columns") or []),
                "row_count": len(((ev.get("chart") or {}).get("rows") or [])),
            }
            for ev in evidence
        ],
    }
    try:
        obj = await llm_client.chat_json(
            choice,
            system=prompts_mod.INSIGHT_DIM_PPT_SYSTEM,
            user=json.dumps(payload, ensure_ascii=False, default=str),
            temperature=0.2,
            max_tokens=8000,
            timeout=120.0,
        )
    except Exception as e:
        logger.warning("xlsx_qa.insight_dim_ppt_digest LLM call failed: %s", e)
        return None
    if not isinstance(obj, dict):
        return None
    summary = obj.get("summary") if isinstance(obj.get("summary"), dict) else {}
    overall = obj.get("overall") if isinstance(obj.get("overall"), dict) else {}
    actions_risks_raw = obj.get("actions") if isinstance(obj.get("actions"), list) else []
    return {
        "summary": {
            "title": str(summary.get("title") or "")[:10],
            "desc": str(summary.get("desc") or "")[:320],
            "points": [str(x)[:320] for x in (summary.get("points") or [])[:4]],
            "conclusion": str(summary.get("conclusion") or "")[:ppt_exporter.INSIGHT_SUMMARY_CONCL_MAX_CHARS],
        },
        "chart_summaries": [],
        "overall": {
            "title": str(overall.get("title") or "")[:10],
            "desc": str(overall.get("desc") or "")[:260],
            "points": [str(x)[:260] for x in (overall.get("points") or [])[:4]],
            "conclusion": str(overall.get("conclusion") or "")[:260],
        },
        "actions": [
            {
                "title": str(a.get("title") or "")[:12],
                "body": str(a.get("body") or "")[:260],
                "owner": str(a.get("owner") or "")[:6],
                "metric": str(a.get("metric") or "")[:8],
                "deadline": str(a.get("deadline") or "")[:8],
            }
            for a in actions_risks_raw[:3] if isinstance(a, dict)
        ],
    }


async def _generate_insight_chart_ppt_digest(choice, dim_item: dict, chart: dict) -> Optional[dict]:
    cid = str((chart or {}).get("subquestion_id") or "").strip()
    if not cid:
        return None
    compact_chart = _compact_single_insight_chart(chart)
    payload = {
        "dimension_context": {
            "dimension_id": dim_item.get("id"),
            "dimension_title": dim_item.get("title") or "",
            "dimension_claim": dim_item.get("claim") or "",
            "dimension_findings": dim_item.get("findings") or [],
            "dimension_markdown": dim_item.get("markdown") or "",
        },
        "chart": {
            **compact_chart,
            "explain": str((chart or {}).get("evidence_explain") or (chart or {}).get("explain") or ""),
        },
    }
    user_json = json.dumps(payload, ensure_ascii=False, default=str)
    logger.info(
        "xlsx_qa.insight_chart_ppt_digest REQUEST dim=%s chart=%s system_len=%d user_len=%d user_json=%s",
        dim_item.get("id"), cid, len(prompts_mod.INSIGHT_CHART_PPT_SYSTEM), len(user_json), user_json,
    )
    try:
        obj = await llm_client.chat_json(
            choice,
            system=prompts_mod.INSIGHT_CHART_PPT_SYSTEM,
            user=user_json,
            temperature=0.2,
            max_tokens=2200,
            timeout=90.0,
        )
        logger.info(
            "xlsx_qa.insight_chart_ppt_digest RESPONSE dim=%s chart=%s obj=%s",
            dim_item.get("id"), cid, json.dumps(obj, ensure_ascii=False, default=str) if isinstance(obj, dict) else str(obj),
        )
    except Exception as e:
        logger.warning("xlsx_qa.insight_chart_ppt_digest LLM call failed dim=%s chart=%s: %s", dim_item.get("id"), cid, e)
        return None
    if not isinstance(obj, dict):
        return None
    returned_cid = str(obj.get("chart_id") or "").strip()
    if returned_cid and returned_cid != cid:
        logger.warning(
            "xlsx_qa.insight_chart_ppt_digest chart_id mismatch dim=%s expected=%s got=%s; forcing expected id",
            dim_item.get("id"), cid, returned_cid,
        )
    return {
        "chart_id": cid,
        "title": str(obj.get("title") or "")[:12],
        "description": str(obj.get("description") or "")[:160],
        "analysis": str(obj.get("analysis") or "")[:480],
        "cards": [
            {"title": str(c.get("title") or "")[:8], "body": str(c.get("body") or "")[:160]}
            for c in (obj.get("cards") or [])[:3] if isinstance(c, dict)
        ],
        "conclusion": str(obj.get("conclusion") or "")[:100],
        "source": "llm",
    }


async def _generate_insight_final_ppt_digest(choice, final_md: str, dim_summaries: List[dict]) -> Optional[dict]:
    payload = {
        "final_md": final_md or "",
        "dimension_summaries": dim_summaries or [],
    }
    try:
        obj = await llm_client.chat_json(
            choice,
            system=prompts_mod.INSIGHT_FINAL_PPT_SYSTEM,
            user=json.dumps(payload, ensure_ascii=False, default=str),
            temperature=0.2,
            max_tokens=8000,
            timeout=90.0,
        )
    except Exception as e:
        logger.warning("xlsx_qa.insight_final_ppt_digest LLM call failed: %s", e)
        return None
    if not isinstance(obj, dict):
        return None
    dashboard = obj.get("dashboard") if isinstance(obj.get("dashboard"), dict) else {}
    priority_map = obj.get("priority_map") if isinstance(obj.get("priority_map"), dict) else {}
    roadmap = obj.get("roadmap") if isinstance(obj.get("roadmap"), dict) else {}
    readout = obj.get("readout") if isinstance(obj.get("readout"), dict) else {}
    return {
        "dashboard": {
            "title": str(dashboard.get("title") or "")[:15],
            "desc": str(dashboard.get("desc") or "")[:240],
            "kpis": [
                {"label": str(k.get("label") or "")[:4], "value": str(k.get("value") or "")[:8]}
                for k in (dashboard.get("kpis") or [])[:4] if isinstance(k, dict)
            ],
            "judgments": [
                {"title": str(j.get("title") or "")[:8], "body": str(j.get("body") or "")[:240]}
                for j in (dashboard.get("judgments") or [])[:4] if isinstance(j, dict)
            ],
        },
        "priority_map": {
            "opportunities": [str(x)[:160] for x in (priority_map.get("opportunities") or [])[:3]],
            "anomalies": [str(x)[:160] for x in (priority_map.get("anomalies") or [])[:3]],
            "risks": [str(x)[:160] for x in (priority_map.get("risks") or [])[:3]],
        },
        "roadmap": {
            "short_term": [str(x)[:160] for x in (roadmap.get("short_term") or [])[:2]],
            "mid_term": [str(x)[:160] for x in (roadmap.get("mid_term") or [])[:2]],
            "long_term": [str(x)[:160] for x in (roadmap.get("long_term") or [])[:2]],
        },
        "readout": {
            "one_liner": str(readout.get("one_liner") or "")[:200],
            "must_verify": str(readout.get("must_verify") or "")[:200],
            "keep_watching": str(readout.get("keep_watching") or "")[:200],
        },
    }


async def _generate_insight_ppt_digests_parallel(
    db: Session,
    module: XlsxQaModule,
    dimensions: List[Dict],
    evidence: Dict[str, Any],
    dim_texts: Dict[str, Any],
    final_md: str,
) -> Optional[Dict[str, Any]]:
    try:
        choice = llm_client.resolve_llm(
            db,
            provider_id=module.llm_provider_id,
            model=module.llm_model,
        )
    except Exception as e:
        logger.warning("xlsx_qa.insight_ppt_digest resolve_llm failed: %s", e)
        return None

    evidence = ppt_exporter._insight_str_key_dict(evidence or {})
    dim_texts = ppt_exporter._insight_str_key_dict(dim_texts or {})

    dim_items = ppt_exporter._insight_dimension_items(dimensions, evidence, dim_texts)

    digest_sem = _asyncio_mod.Semaphore(4)
    chart_sem = _asyncio_mod.Semaphore(6)

    async def _bounded_dim_digest(item: dict):
        async with digest_sem:
            return await _generate_insight_dim_ppt_digest(choice, item)

    async def _bounded_chart_digest(item: dict, chart: dict):
        async with chart_sem:
            return await _generate_insight_chart_ppt_digest(choice, item, chart)

    dim_tasks = []
    dim_ids = []
    chart_tasks = []
    chart_keys = []
    chart_by_key: Dict[Tuple[str, str], dict] = {}
    for item in dim_items:
        dim_id = str(item["id"])
        dim_ids.append(dim_id)
        dim_tasks.append(_bounded_dim_digest(item))
        for chart in ppt_exporter._insight_ordered_evidence_visuals(item.get("evidence") or []):
            chart_key = (dim_id, str((chart or {}).get("subquestion_id") or ""))
            chart_keys.append(chart_key)
            chart_by_key[chart_key] = chart
            chart_tasks.append(_bounded_chart_digest(item, chart))

    # 与维度 digest 并行生成最终洞察页文案；摘要字段来自维度 claim/title（不等待各维度 digest LLM）
    dim_summaries_preflight = [
        {
            "dim_id": item["id"],
            "title": str(item.get("title") or "")[:32],
            "conclusion": str(item.get("claim") or "")[:320],
        }
        for item in dim_items
    ]
    all_tasks = []
    if dim_tasks:
        all_tasks.append(_asyncio_mod.gather(*dim_tasks, return_exceptions=True))
    else:
        all_tasks.append(_asyncio_mod.sleep(0, result=[]))
    if chart_tasks:
        all_tasks.append(_asyncio_mod.gather(*chart_tasks, return_exceptions=True))
    else:
        all_tasks.append(_asyncio_mod.sleep(0, result=[]))
    if final_md:
        all_tasks.append(_generate_insight_final_ppt_digest(choice, final_md, dim_summaries_preflight))
    results = await _asyncio_mod.gather(*all_tasks, return_exceptions=True)

    dim_results = results[0] if len(results) > 0 and not isinstance(results[0], Exception) else []
    chart_results = results[1] if len(results) > 1 and not isinstance(results[1], Exception) else []
    final_result = results[2] if final_md and len(results) > 2 else None
    if len(results) > 0 and isinstance(results[0], Exception):
        logger.warning("xlsx_qa.insight_dim_ppt_digest batch failed: %s", results[0])
    if len(results) > 1 and isinstance(results[1], Exception):
        logger.warning("xlsx_qa.insight_chart_ppt_digest batch failed: %s", results[1])

    dim_digests: Dict[str, dict] = {}
    for dim_id, result in zip(dim_ids, dim_results):
        if isinstance(result, Exception):
            logger.warning("xlsx_qa.insight_dim_ppt_digest item failed: %s", result)
            continue
        if result:
            dim_digests[dim_id] = result

    chart_failures: List[dict] = []
    seen_chart_card_signatures: Dict[str, set[str]] = {}
    for chart_key, result in zip(chart_keys, chart_results):
        dim_id, chart_id = chart_key
        if isinstance(result, Exception):
            logger.warning("xlsx_qa.insight_chart_ppt_digest item failed: %s", result)
            chart_failures.append({"dim_id": dim_id, "chart_id": chart_id, "error": str(result)[:240]})
            continue
        if not result:
            chart_failures.append({"dim_id": dim_id, "chart_id": chart_id, "error": "empty chart digest"})
            continue
        dim_digest = dim_digests.setdefault(dim_id, {
            "summary": {},
            "chart_summaries": [],
            "overall": {},
            "actions": [],
        })
        summaries = dim_digest.setdefault("chart_summaries", [])
        if isinstance(summaries, list):
            seen = seen_chart_card_signatures.setdefault(dim_id, set())
            summaries.append(_stabilize_chart_digest_for_chart(result, chart_by_key.get(chart_key) or {}, seen))

    final_digest = None
    if final_md:
        if isinstance(final_result, Exception):
            logger.warning("xlsx_qa.insight_final_ppt_digest failed: %s", final_result)
        elif final_result:
            final_digest = final_result

    return {
        "dim_digests": dim_digests,
        "final_digest": final_digest,
        "chart_failures": chart_failures,
    }


def _attach_insight_ppt_digests_sync(
    db: Session,
    module: XlsxQaModule,
    dimensions: List[Dict],
    evidence: Dict[str, Any],
    dim_texts: Dict[str, Any],
    final_md: str,
) -> Optional[Dict[str, Any]]:
    """同步包装器：在 _do_insight_ppt_export_async 中调用，并行生成所有洞察PPT文案。"""
    try:
        try:
            _asyncio_mod.get_running_loop()
            logger.warning("xlsx_qa.insight_ppt_digest parallel skipped: running event loop in current thread")
            return None
        except RuntimeError:
            pass
        digests = _asyncio_mod.run(_generate_insight_ppt_digests_parallel(
            db, module, dimensions, evidence, dim_texts, final_md,
        ))
    except Exception as e:
        logger.warning("xlsx_qa.insight_ppt_digest parallel failed: %s", e)
        return None
    return digests


def _compact_ppt_charts(charts: List[Any]) -> List[dict]:
    result = []
    for c in charts[:6]:
        if not isinstance(c, dict):
            continue
        result.append({
            "chart_id": c.get("subquestion_id"),
            "chart_type": c.get("chart_type"),
            "title": c.get("title"),
            "explain": c.get("explain"),
            "dimension_field": c.get("dimension_field"),
            "metric_fields": c.get("metric_fields") or [],
            "columns": c.get("columns") or [],
            "rows_sample": (c.get("rows") or [])[:12],
            "row_count": len(c.get("rows") or []),
        })
    return result


def _compact_ppt_subquestions(subqs: List[Any]) -> List[dict]:
    result = []
    for s in subqs[:6]:
        if not isinstance(s, dict):
            continue
        result.append({
            "id": s.get("id"),
            "question": s.get("question"),
            "columns": s.get("columns") or [],
            "rows_sample": (s.get("rows") or [])[:12],
            "total_rows": s.get("total_rows") or len(s.get("rows") or []),
        })
    return result
