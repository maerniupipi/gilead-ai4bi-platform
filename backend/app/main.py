"""
Chat-BI 应用主入口 - 配置 FastAPI 应用、中间件、异常处理和路由
"""
import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .core.logging_config import setup_logging, get_logger
from .core.database import check_database, should_create_tables_on_startup, Base, engine
from .core.middleware import ResponseEnvelopeMiddleware, get_audit_executor
from .core.exceptions import register_exception_handlers
from . import models as _models  # noqa: F401  ensure all ORM models are registered before create_all

# 初始化日志系统
setup_logging()
logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# 数据库启动检查
# ---------------------------------------------------------------------------

def _ensure_model_thinking_settings_column() -> None:
    from sqlalchemy import inspect, text
    from sqlalchemy.exc import SQLAlchemyError

    try:
        with engine.begin() as conn:
            inspector = inspect(conn)
            if "model_providers" not in inspector.get_table_names():
                return
            if "model_settings" not in {c["name"] for c in inspector.get_columns("model_providers")}:
                conn.execute(text("ALTER TABLE model_providers ADD COLUMN model_settings JSON NULL"))
    except SQLAlchemyError:
        # Another worker may have added the column during startup.
        with engine.connect() as conn:
            if "model_settings" not in {c["name"] for c in inspect(conn).get_columns("model_providers")}:
                raise


def _ensure_eval_case_remark_column() -> None:
    """确保 eval_cases.remark 列存在（兼容历史库）。"""
    from sqlalchemy import inspect, text
    try:
        with engine.begin() as conn:
            inspector = inspect(conn)
            table_names = inspector.get_table_names()
            if "eval_cases" not in table_names:
                return
            columns = {c["name"] for c in inspector.get_columns("eval_cases")}
            if "remark" in columns:
                return
            conn.execute(text("ALTER TABLE eval_cases ADD COLUMN remark TEXT NULL"))
            logger.info("数据库结构升级：已为 eval_cases 添加 remark 字段")
    except Exception:
        logger.exception("数据库结构升级失败：添加 eval_cases.remark")


def _ensure_xlsx_qa_insight_report_table() -> None:
    """历史库可能缺少洞察报告表（关闭 create_all 时）；按需单表补建。"""
    from sqlalchemy import inspect

    from .models.xlsx_qa import XlsxQaInsightReport

    try:
        insp = inspect(engine)
        names = {t.lower() for t in insp.get_table_names()}
        if "xlsx_qa_insight_report" in names:
            return
        XlsxQaInsightReport.__table__.create(bind=engine, checkfirst=True)
        logger.info("数据库结构升级：已创建 xlsx_qa_insight_report 表")
    except Exception:
        logger.exception("数据库结构升级失败：创建 xlsx_qa_insight_report")


def _ensure_vector_manifest_table() -> None:
    """历史库可能缺少向量化 manifest 表；按需单表补建。"""
    from sqlalchemy import inspect

    from .models.vector_manifest import KbVectorManifest

    try:
        insp = inspect(engine)
        names = {t.lower() for t in insp.get_table_names()}
        if "kb_vector_manifest" in names:
            return
        KbVectorManifest.__table__.create(bind=engine, checkfirst=True)
        logger.info("数据库结构升级：已创建 kb_vector_manifest 表")
    except Exception:
        logger.exception("数据库结构升级失败：创建 kb_vector_manifest")


def _ensure_data_sync_tables():
    from .models.data_sync import DataSyncEvent, DataSyncRun, DataSyncTask
    try:
        Base.metadata.create_all(bind=engine, tables=[DataSyncTask.__table__, DataSyncRun.__table__, DataSyncEvent.__table__])
    except Exception:
        logger.exception("数据库结构升级失败：创建数据同步管理表")


def _ensure_support_tables():
    from .models.chatbi import ChatBIMessage, ChatBIMessageDiagnostic, ChatBITraceLookup, ChatBIDiagnosticIndexState
    from .models.system_log import SystemLog
    try:
        Base.metadata.create_all(bind=engine, tables=[ChatBIMessageDiagnostic.__table__, ChatBITraceLookup.__table__, ChatBIDiagnosticIndexState.__table__, SystemLog.__table__])
        for index in ChatBIMessage.__table__.indexes:
            if index.name == "ix_chatbi_message_conversation_sequence":
                index.create(bind=engine, checkfirst=True)
    except Exception:
        logger.exception('数据库结构升级失败：创建会话诊断与系统日志表')


def _seed_ppt_templates() -> None:
    """首次启动时将 8 条内置 PPT 模板写入数据库；表不存在时自动创建。"""
    from sqlalchemy import inspect
    from .core.database import SessionLocal
    from .models.xlsx_qa import XlsxQaPptTemplate

    try:
        insp = inspect(engine)
        names = {t.lower() for t in insp.get_table_names()}
        if "xlsx_qa_ppt_template" not in names:
            XlsxQaPptTemplate.__table__.create(bind=engine, checkfirst=True)
            logger.info("数据库结构升级：已创建 xlsx_qa_ppt_template 表")
    except Exception:
        logger.exception("数据库结构升级失败：创建 xlsx_qa_ppt_template")
        return

    db = SessionLocal()
    try:
        if db.query(XlsxQaPptTemplate).first() is not None:
            return
        templates = [
            dict(id="executive", name="商务简报", description="专业商务风格，侧边栏布局", layout="sidebar", sort_order=10,
                 colors={"accent":"#16A34A","accent_dark":"#085F37","accent_soft":"#E8F8EE","bg":"#F7FAFC","panel":"#FFFFFF","text":"#17241F","muted":"#64748B","table_header":"#0F7A4B","table_alt":"#F1FAF5","palette":["#16A34A","#2563EB","#F59E0B","#DC2626","#7C3AED","#0E7480"]}),
            dict(id="insight", name="洞察分析", description="蓝色洞察风格，顶部横幅布局", layout="header", sort_order=20,
                 colors={"accent":"#2563EB","accent_dark":"#1E3A8A","accent_soft":"#E8F0FF","bg":"#F8FAFC","panel":"#FFFFFF","text":"#0F172A","muted":"#64748B","table_header":"#1D4E89","table_alt":"#F1F5FF","palette":["#2563EB","#10B981","#F97316","#8B5CF6","#06B6D4","#E11D48"]}),
            dict(id="clean", name="简约数据", description="极简干净风格，最小化布局", layout="minimal", sort_order=30,
                 colors={"accent":"#334155","accent_dark":"#0F172A","accent_soft":"#F1F5F9","bg":"#FFFFFF","panel":"#FFFFFF","text":"#111827","muted":"#6B7280","table_header":"#334155","table_alt":"#F8FAFC","palette":["#334155","#0E7480","#65A30D","#CA8A04","#7C2D12","#7E22CE"]}),
            dict(id="midnight", name="午夜深蓝", description="深蓝夜间风格，全屏暗色布局", layout="dark_full", sort_order=40,
                 colors={"accent":"#FFB224","accent_dark":"#0D1B2A","accent_soft":"#1B2D44","bg":"#0D1B2A","panel":"#15263B","text":"#E8ECF1","muted":"#8B9DB3","table_header":"#1B3A5C","table_alt":"#122236","palette":["#FFB224","#38BDF8","#A78BFA","#34D399","#FB7185","#60A5FA"]}),
            dict(id="coral", name="珊瑚活力", description="珊瑚活力风格，对角线布局", layout="diagonal", sort_order=50,
                 colors={"accent":"#F96167","accent_dark":"#C0392B","accent_soft":"#FFF1F0","bg":"#FFFAF7","panel":"#FFFFFF","text":"#2D1B1B","muted":"#9C7A7A","table_header":"#E84D4D","table_alt":"#FFF5F4","palette":["#F96167","#F97316","#FBBF24","#2DC653","#38BDF8","#A78BFA"]}),
            dict(id="teal", name="青绿信赖", description="青绿信赖风格，角落布局", layout="corner", sort_order=60,
                 colors={"accent":"#0D9488","accent_dark":"#115E59","accent_soft":"#ECFDF5","bg":"#F0FDFA","panel":"#FFFFFF","text":"#132B2B","muted":"#6B8A87","table_header":"#0F766E","table_alt":"#F0FDFA","palette":["#0D9488","#06B6D4","#8B5CF6","#F59E0B","#EF4444","#22C55E"]}),
            dict(id="berry", name="浆果奶油", description="浆果甜美风格，右侧面板布局", layout="right_panel", sort_order=70,
                 colors={"accent":"#9D174D","accent_dark":"#701238","accent_soft":"#FDF2F8","bg":"#FFFAFC","panel":"#FFFFFF","text":"#2A1522","muted":"#9C7A8C","table_header":"#831843","table_alt":"#FDF2F8","palette":["#9D174D","#A26769","#BE185D","#D97706","#6D28D9","#0891B2"]}),
            dict(id="charcoal", name="炭黑深沉", description="炭黑深沉风格，暗色头部布局", layout="dark_header", sort_order=80,
                 colors={"accent":"#F59E0B","accent_dark":"#1E1E1E","accent_soft":"#2A2A2A","bg":"#1E1E1E","panel":"#2A2A2A","text":"#E5E5E5","muted":"#8A8A8A","table_header":"#3A3A3A","table_alt":"#242424","palette":["#F59E0B","#38BDF8","#A3E635","#F472B6","#C084FC","#FB923C"]}),
        ]
        for t in templates:
            db.add(XlsxQaPptTemplate(**t, is_builtin=True))
        db.commit()
        logger.info("已初始化 %d 条内置 PPT 模板", len(templates))
    except Exception:
        db.rollback()
        logger.exception("初始化 PPT 模板种子数据失败")
    finally:
        db.close()


def _seed_eval_configs() -> None:
    """首次启动时写入评测默认配置；表不存在时自动创建。"""
    from sqlalchemy import inspect
    from .core.database import SessionLocal
    from .models.eval import EvalConfig
    from .repositories.eval.eval_config_repo import seed_defaults

    try:
        insp = inspect(engine)
        names = {t.lower() for t in insp.get_table_names()}
        if "eval_configs" not in names:
            EvalConfig.__table__.create(bind=engine, checkfirst=True)
            logger.info("数据库结构升级：已创建 eval_configs 表")
    except Exception:
        logger.exception("数据库结构升级失败：创建 eval_configs")
        return

    db = SessionLocal()
    try:
        seed_defaults(db)
    except Exception:
        db.rollback()
        logger.exception("初始化评测配置种子数据失败")
    finally:
        db.close()


def initialize_database():
    if should_create_tables_on_startup():
        try:
            Base.metadata.create_all(bind=engine)
            _ensure_eval_case_remark_column()
        except Exception:
            logger.exception("数据库建表检查失败，应用继续启动；/health 会暴露数据库状态")
    _ensure_model_thinking_settings_column()
    _ensure_xlsx_qa_insight_report_table()
    _ensure_vector_manifest_table()
    _ensure_data_sync_tables()
    _ensure_support_tables()
    _seed_ppt_templates()
    _seed_eval_configs()


if os.getenv("PLATFORM_SCHEMA_INITIALIZED") != "true":
    initialize_database()


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def _lifespan(app: FastAPI):
    from contextlib import AsyncExitStack
    from .services.system_logs import start_log_writer, stop_log_writer
    from .core.database import SessionLocal
    from .worker import background_mode, background_tasks
    from .core.execution import DATABASE_WORK, monitor_event_loop
    start_log_writer(SessionLocal)
    logger.info("Chat-BI API 启动")
    try:
        await DATABASE_WORK.run(check_database)
    except Exception:
        logger.exception("数据库启动健康检查失败")
    async with AsyncExitStack() as stack:
        if background_mode() == "inline":
            await stack.enter_async_context(background_tasks())
        monitor = asyncio.create_task(monitor_event_loop())
        try:
            yield
        finally:
            monitor.cancel()
            await asyncio.gather(monitor, return_exceptions=True)
    from .core.trace_writer import flush_traces
    from .core.http_clients import close_http_clients
    await flush_traces()
    await close_http_clients()
    from .services.eval.eval_target_adapter import shutdown_target_executor
    from .services.eval.eval_task_service import shutdown_judge_executor

    shutdown_target_executor()
    shutdown_judge_executor()
    get_audit_executor().shutdown(wait=False, cancel_futures=True)
    logger.info("Chat-BI API 关闭")
    stop_log_writer()
    from .core.execution import shutdown_blocking_pools
    from .core.logging_config import stop_logging
    await asyncio.to_thread(shutdown_blocking_pools)
    from .core.resources import close_resources
    from .core.db_connections import close_connection_pools
    from .core.database import close_query_engines
    await asyncio.to_thread(close_resources)
    await asyncio.to_thread(close_connection_pools)
    await asyncio.to_thread(close_query_engines)
    await asyncio.to_thread(stop_logging)


# ---------------------------------------------------------------------------
# FastAPI 应用
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Chat-BI API",
    description="Chat-BI 项目的后端 API 服务",
    version="1.0.0",
    lifespan=_lifespan,
)

# 注册异常处理器
register_exception_handlers(app)

# 注册中间件
app.add_middleware(ResponseEnvelopeMiddleware)
from .core.observability import RequestLogMiddleware
app.add_middleware(RequestLogMiddleware)
if signing_key := os.getenv("PLATFORM_SESSION_SIGNING_KEY"):
    from starlette.middleware.sessions import SessionMiddleware
    from .core.management_session import ManagementSessionMiddleware
    app.add_middleware(ManagementSessionMiddleware)
    app.add_middleware(
        SessionMiddleware, secret_key=signing_key, session_cookie="ai4bi_platform",
        path="/", max_age=86400, same_site="strict",
        https_only=os.getenv("PLATFORM_SESSION_HTTPS_ONLY", "false").lower() == "true",
    )
from .routers.system_logs import router as system_logs_router
app.include_router(system_logs_router)


# ---------------------------------------------------------------------------
# CORS 配置辅助
# ---------------------------------------------------------------------------

def _env_list(name: str, default: list[str] | None = None) -> list[str]:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default or []
    return [item.strip() for item in raw.split(",") if item.strip()]


def _get_cors_origins():
    return _env_list("CORS_ALLOWED_ORIGINS", ["*"])


def _get_cors_allow_credentials():
    allow = (os.getenv("CORS_ALLOW_CREDENTIALS") or "true").strip().lower() not in {"0", "false", "no", "off"}
    if "*" in _get_cors_origins() and allow:
        logger.warning("CORS_ALLOWED_ORIGINS=* 时不能安全启用 credentials，已自动关闭 CORS_ALLOW_CREDENTIALS")
        return False
    return allow


app.add_middleware(
    CORSMiddleware,
    allow_origins=_get_cors_origins(),
    allow_credentials=_get_cors_allow_credentials(),
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# 路由
# ---------------------------------------------------------------------------

from .routers.knowledge import router as knowledge_router
from .routers.auth import router as auth_router
from .routers.spaces import router as spaces_router
from .routers.model_provider import router as model_provider_router
from .routers.vector_store import router as vector_store_router
from .routers.oss_config import router as oss_config_router
from .routers.es_config import router as es_config_router
from .routers.embedding_config import router as embedding_config_router
from .routers.chat import router as chat_router
from .routers.autobi import router as autobi_router
from .routers.agent_platform import router as agent_platform_router
from .routers.xlsx_qa import router as xlsx_qa_router
from .routers.user import router as user_router
from .routers.audit_log import router as audit_log_router
from .routers.eval import router as eval_router
from .routers.system_update import router as system_update_router
from .routers.external_agent import router as external_agent_router

app.include_router(knowledge_router)
app.include_router(auth_router)
app.include_router(spaces_router)
app.include_router(model_provider_router)
app.include_router(vector_store_router)
app.include_router(oss_config_router)
app.include_router(es_config_router)
app.include_router(embedding_config_router)
app.include_router(chat_router)
app.include_router(autobi_router)
app.include_router(agent_platform_router)
app.include_router(xlsx_qa_router)
app.include_router(user_router)
app.include_router(audit_log_router)
app.include_router(eval_router)
app.include_router(system_update_router, prefix="/api/system-updates", tags=["系统更新"])
app.include_router(external_agent_router)
from .routers.chatbi import router as chatbi_router
app.include_router(chatbi_router)
from .routers.chatbi.admin import router as chatbi_admin_router
app.include_router(chatbi_admin_router)
from .routers.chatbi.conversations import router as chatbi_conversation_router
app.include_router(chatbi_conversation_router)
from .routers.chatbi.ppt_model import router as chatbi_ppt_model_router
app.include_router(chatbi_ppt_model_router)
from .routers.data_sync import router as data_sync_router
app.include_router(data_sync_router)


# ---------------------------------------------------------------------------
# 健康检查
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    """进程与数据库健康检查。"""
    try:
        from .core.execution import HEALTH_WORK
        db_status = await asyncio.wait_for(HEALTH_WORK.run(check_database), 3)
    except Exception as e:
        logger.warning("health check database failed: %s", e)
        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "database": {"ok": False, "error": str(e)}},
        )
    return {
        "status": "ok",
        "app_env": os.getenv("APP_ENV", "dev"),
        "version": os.getenv("APP_VERSION", app.version),
        "database": db_status,
    }


@app.get("/live")
async def live():
    """进程存活检查，不访问外部依赖，适合容器 livenessProbe。"""
    return {
        "status": "ok",
        "app_env": os.getenv("APP_ENV", "dev"),
        "version": os.getenv("APP_VERSION", app.version),
    }


@app.get("/")
def read_root():
    """根路径 - API 欢迎信息"""
    return {"message": "Welcome to Chat-BI API"}
