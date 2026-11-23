"""Bounded SQL workers: a database query must not run on the HTTP event loop."""
import asyncio
import os
import threading
import sqlglot
from sqlglot import exp
from sqlglot.errors import ErrorLevel, SqlglotError
from concurrent.futures import ThreadPoolExecutor

from fastapi import HTTPException
from sqlalchemy.orm import Session

SQL_WORKERS = ThreadPoolExecutor(max_workers=4, thread_name_prefix="knowledge-sql")
SQL_SLOTS = threading.BoundedSemaphore(4)


def query_timeout_seconds():
    return min(300, max(1, int(os.getenv("KNOWLEDGE_SQL_TIMEOUT_SECONDS", "45"))))


def result_row_limit():
    return min(100000, max(1, int(os.getenv("KNOWLEDGE_SQL_MAX_ROWS", "5000"))))


def result_byte_limit():
    return min(67108864, max(1024, int(os.getenv("KNOWLEDGE_SQL_MAX_BYTES", "10485760"))))


def bounded_query(sql, dialect):
    if len(sql) > 100000:
        raise HTTPException(400, "SQL 长度超过上限")
    try:
        statements = [s for s in sqlglot.parse(sql, read=dialect, error_level=ErrorLevel.RAISE)
                      if s is not None and not isinstance(s, exp.Semicolon)]
        if len(statements) != 1 or not isinstance(statements[0], (exp.Select, exp.SetOperation)):
            raise HTTPException(400, "仅允许单条 SELECT 查询")
        tree = statements[0]
        forbidden = (exp.DML, exp.DDL, exp.Command, exp.Into, exp.Lock, exp.Parameter, exp.Placeholder)
        for index, node in enumerate(tree.walk()):
            if index > 12000 or isinstance(node, forbidden):
                raise HTTPException(400, "SQL 包含不支持的语句或结构过于复杂")
        limit = tree.args.get('limit')
        value = limit.expression if limit is not None else None
        cap = result_row_limit() + 1
        if not isinstance(value, exp.Literal) or not value.is_int or int(value.this) > cap:
            tree = tree.limit(cap)
        return tree.sql(dialect=dialect, unsupported_level=ErrorLevel.RAISE)
    except (SqlglotError, RecursionError, ValueError) as exc:
        raise HTTPException(400, "SQL 无法安全解析") from exc


async def execute_knowledge_sql_async(db, knowledge_base_id, sql, *, execute=None):
    if execute is None:
        from .knowledge_base.service import execute_knowledge_base_sql_service
        execute = execute_knowledge_base_sql_service
    bind = db.get_bind()
    if not SQL_SLOTS.acquire(blocking=False):
        raise HTTPException(503, "数据库查询并发已满，请稍后重试")

    def worker():
        try:
            with Session(bind=bind) as worker_db:
                return execute(worker_db, knowledge_base_id, sql)
        finally:
            SQL_SLOTS.release()

    try:
        future = asyncio.get_running_loop().run_in_executor(SQL_WORKERS, worker)
    except BaseException:
        SQL_SLOTS.release()
        raise
    future.add_done_callback(lambda value: value.exception() if not value.cancelled() else None)
    try:
        # Shielding prevents cancellation from marking a still-running worker
        # complete. Its slot remains occupied until its database call ends.
        return await asyncio.wait_for(asyncio.shield(future), query_timeout_seconds() + 5)
    except TimeoutError as exc:
        raise HTTPException(504, "SQL 查询超时，请缩小查询范围后重试") from exc
