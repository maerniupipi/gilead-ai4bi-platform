#!/usr/bin/env python3
"""创建全新 MySQL 数据库并初始化 Chat-BI 必需默认数据。"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy import create_engine

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create Chat-BI database tables and seed required defaults.")
    parser.add_argument("--env", choices=["dev", "uat", "prod"], help="加载 config/environments/{env}.env")
    parser.add_argument("--database-url", help="覆盖环境变量 DATABASE_URL")
    parser.add_argument("--drop-existing", action="store_true", help="先 DROP DATABASE，再重新创建。仅用于确认要清空的新库。")
    parser.add_argument("--admin-username")
    parser.add_argument("--admin-password")
    parser.add_argument("--admin-display-name")
    parser.add_argument("--space-name")
    parser.add_argument("--space-code")
    parser.add_argument("--space-description")
    parser.add_argument("--reset-admin-password", action="store_true", help="若管理员已存在，也覆盖其密码。默认不覆盖。")
    return parser


def _quote_identifier(value: str) -> str:
    if not value:
        raise ValueError("DATABASE_URL 必须包含数据库名，例如 ...:3306/chatbi")
    return f"`{value.replace('`', '``')}`"


def _server_url(database_url: str) -> tuple[str, str]:
    url = make_url(database_url)
    if not url.drivername.startswith("mysql"):
        raise ValueError(f"当前初始化脚本只支持 MySQL DATABASE_URL，收到: {url.drivername}")
    database = url.database or ""
    server = url.set(database="")
    return server.render_as_string(hide_password=False), database


def _create_server_engine(url: str):
    kwargs = {"pool_pre_ping": True, "pool_size": 1, "max_overflow": 0}
    if url.startswith("mysql+mysqlconnector://"):
        kwargs["connect_args"] = {
            "connection_timeout": int(os.getenv("DB_CONNECT_TIMEOUT_SECONDS", "10")),
            "read_timeout": int(os.getenv("DB_READ_TIMEOUT_SECONDS", "30")),
            "write_timeout": int(os.getenv("DB_WRITE_TIMEOUT_SECONDS", "30")),
        }
    return create_engine(url, **kwargs)


def main() -> int:
    args = _build_parser().parse_args()
    if args.env:
        os.environ["APP_ENV"] = args.env
    if args.database_url:
        os.environ["DATABASE_URL"] = args.database_url

    from app.core.env_loader import load_app_environment

    load_app_environment(app_env=args.env, override=False)
    if args.database_url:
        os.environ["DATABASE_URL"] = args.database_url

    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("未找到 DATABASE_URL，请先配置环境文件或传入 --database-url")

    admin_password = args.admin_password or os.getenv("INIT_SUPER_ADMIN_PASSWORD", "")
    if not admin_password:
        raise RuntimeError("请设置 INIT_SUPER_ADMIN_PASSWORD 或 --admin-password")

    url = make_url(database_url)
    if url.get_backend_name() == "postgresql":
        if args.drop_existing:
            raise ValueError("PostgreSQL 初始化需要预建数据库和独立 schema。")
        database = url.database
    else:
        server_url, database = _server_url(database_url)
        database_ident = _quote_identifier(database)

        server_engine = _create_server_engine(server_url)
        with server_engine.begin() as conn:
            if args.drop_existing:
                conn.execute(text(f"DROP DATABASE IF EXISTS {database_ident}"))
            conn.execute(text(f"CREATE DATABASE IF NOT EXISTS {database_ident} DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"))
        server_engine.dispose()

    from app.core.database import Base, SessionLocal, engine
    import app.models  # noqa: F401  注册全部 ORM 模型
    from app.services.bootstrap import seed_initial_data

    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        result = seed_initial_data(
            db,
            admin_username=args.admin_username or os.getenv("INIT_SUPER_ADMIN_USERNAME", "admin"),
            admin_password=admin_password,
            admin_display_name=args.admin_display_name or os.getenv("INIT_SUPER_ADMIN_DISPLAY_NAME", "超级管理员"),
            space_name=args.space_name or os.getenv("INIT_SPACE_NAME", "默认空间"),
            space_code=args.space_code or os.getenv("INIT_SPACE_CODE", "default"),
            space_description=args.space_description or os.getenv("INIT_SPACE_DESCRIPTION", "系统默认空间"),
            update_existing_admin_password=args.reset_admin_password,
        )
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    print("数据库初始化完成")
    print(f"database={database}")
    print(f"space_id={result['space_id']} space_code={result['space_code']}")
    print(f"admin_id={result['admin_id']} admin_username={result['admin_username']}")
    print("初始化账号使用本次显式提供的密码。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
