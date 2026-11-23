"""数据库连接配置 - 提供SQLAlchemy引擎、会话工厂和依赖注入函数。"""
from __future__ import annotations

import logging
import os
import threading
from collections import OrderedDict
from typing import Any

from .env_loader import load_app_environment

load_app_environment()

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# 环境变量由 app.core.env_loader（在 main 入口）或脚本显式 load 注入
logger = logging.getLogger(__name__)

# 从环境变量读取数据库连接URL
DATABASE_URL = os.getenv("DATABASE_URL", "mysql+mysqlconnector://root:password@localhost:3306/chatbi")


def _env_int(name: str, default: int, minimum: int | None = None) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        logger.warning("环境变量 %s=%r 不是整数，使用默认值 %s", name, raw, default)
        return default
    if minimum is not None:
        return max(minimum, value)
    return value


def _env_bool(name: str, default: bool = False) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _mysql_connect_args() -> dict[str, Any]:
    """mysql-connector-python 连接级超时，避免建连/读写无限挂住。"""
    return {
        "connection_timeout": _env_int("DB_CONNECT_TIMEOUT_SECONDS", 10, 1),
        "read_timeout": _env_int("DB_READ_TIMEOUT_SECONDS", 30, 1),
        "write_timeout": _env_int("DB_WRITE_TIMEOUT_SECONDS", 30, 1),
    }


def create_database_engine(
    url: str,
    *,
    pool_size: int | None = None,
    max_overflow: int | None = None,
    pool_timeout: int | None = None,
    pool_recycle: int | None = None,
) -> Engine:
    """创建带探活、回收和等待上限的 SQLAlchemy Engine。"""
    kwargs: dict[str, Any] = {
        "pool_pre_ping": True,
        "pool_recycle": pool_recycle if pool_recycle is not None else _env_int("DB_POOL_RECYCLE_SECONDS", 1800, 60),
        "pool_size": pool_size if pool_size is not None else _env_int("DB_POOL_SIZE", 10, 1),
        "max_overflow": max_overflow if max_overflow is not None else _env_int("DB_MAX_OVERFLOW", 10, 0),
        "pool_timeout": pool_timeout if pool_timeout is not None else _env_int("DB_POOL_TIMEOUT_SECONDS", 10, 1),
    }
    if url.startswith("mysql+mysqlconnector://"):
        kwargs["connect_args"] = _mysql_connect_args()
    elif url.startswith('mysql+pymysql://'):
        kwargs['connect_args'] = {
            'connect_timeout': _env_int('DB_CONNECT_TIMEOUT_SECONDS', 10, 1),
            'read_timeout': _env_int('DB_READ_TIMEOUT_SECONDS', 30, 1),
            'write_timeout': _env_int('DB_WRITE_TIMEOUT_SECONDS', 30, 1),
        }
    elif url.startswith(("postgresql://", "postgresql+psycopg2://")):
        kwargs["connect_args"] = {"connect_timeout": _env_int("DB_CONNECT_TIMEOUT_SECONDS", 10, 1)}
    return create_engine(url, **kwargs)


def create_external_mysql_engine(url: str) -> Engine:
    """外部业务数据源使用较小连接池，避免拖垮主库连接池。"""
    return create_database_engine(
        url,
        pool_size=_env_int("EXTERNAL_DB_POOL_SIZE", 3, 1),
        max_overflow=_env_int("EXTERNAL_DB_MAX_OVERFLOW", 2, 0),
        pool_timeout=_env_int("EXTERNAL_DB_POOL_TIMEOUT_SECONDS", 8, 1),
        pool_recycle=_env_int("EXTERNAL_DB_POOL_RECYCLE_SECONDS", 900, 60),
    )


_query_engines = OrderedDict()
_query_engine_lock = threading.Lock()


def query_engine(url):
    with _query_engine_lock:
        if url not in _query_engines:
            _query_engines[url] = create_external_mysql_engine(url)
        _query_engines.move_to_end(url)
        while len(_query_engines) > 16:
            _, retired = _query_engines.popitem(last=False)
            retired.dispose()
        return _query_engines[url]


def close_query_engines():
    with _query_engine_lock:
        for item in _query_engines.values():
            item.dispose()
        _query_engines.clear()


# 创建数据库引擎
engine = create_database_engine(DATABASE_URL)

# 创建会话工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# ORM模型基类
Base = declarative_base()


def check_database() -> dict[str, Any]:
    """执行轻量健康检查，供启动和 /health 使用。"""
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    pool = engine.pool
    status = pool.status() if hasattr(pool, "status") else "unknown"
    return {"ok": True, "pool": status}


def should_create_tables_on_startup() -> bool:
    return _env_bool("DB_CREATE_ALL_ON_STARTUP", True)


def get_db():
    """获取数据库会话（FastAPI依赖注入）"""
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def trace_upsert(session, model, values, update_columns):
    """Create or update a trace atomically, keeping its original creation metadata."""
    if session.get_bind().dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
        stmt = insert(model).values(**values)
        return stmt.on_conflict_do_update(
            index_elements=[model.trace_id],
            set_={key: stmt.excluded[key] for key in update_columns},
        )
    from sqlalchemy.dialects.mysql import insert
    stmt = insert(model).values(**values)
    return stmt.on_duplicate_key_update(**{key: stmt.inserted[key] for key in update_columns})
