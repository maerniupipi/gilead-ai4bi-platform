"""Deployment-configured HTTP JSON synchronization tasks; no built-in sources."""
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re
from urllib.parse import urlsplit
from sqlalchemy.engine import make_url


def task_definitions(env=None):
    env = os.environ if env is None else env
    try:
        tasks = json.loads(env.get("DATA_SYNC_TASKS", "{}"))
    except (TypeError, ValueError):
        raise ValueError("DATA_SYNC_TASKS 必须为 JSON 对象") from None
    if not isinstance(tasks, dict) or any(
        not re.fullmatch(r"[A-Za-z0-9_-]{1,16}", key) or not isinstance(value, dict)
        for key, value in tasks.items()
    ):
        raise ValueError("同步任务须为对象配置，任务 ID 仅支持 1–16 位字母、数字、下划线和短横线")
    return tasks


def _integer(config, key, default, minimum=1, maximum=100000000):
    try:
        value = int(config.get(key, default))
    except (ValueError, TypeError):
        raise ValueError(f"{key} 必须为整数") from None
    if not minimum <= value <= maximum:
        raise ValueError(f"{key} 必须介于 {minimum} 和 {maximum}")
    return value


@dataclass(frozen=True)
class SyncConfig:
    table_key: str
    target_table: str
    database_url: str = field(repr=False)
    base_url: str
    headers: dict = field(default_factory=dict, repr=False)
    request_params: dict = field(default_factory=dict, repr=False)
    method: str = "GET"
    records_path: str = "data"
    page_param: str = "page"
    page_size_param: str = "page_size"
    column_case: str = "lower"
    timeout: int = 60
    retry_times: int = 3
    page_size: int = 5000
    max_workers: int = 1
    part_rows: int = 100000
    min_rows: int = 1
    max_pages: int = 100000
    statement_timeout_ms: int = 3600000
    tmp_dir: str = "data/sync"

    @classmethod
    def from_env(cls, table_key, env=None):
        env = os.environ if env is None else env
        config = task_definitions(env).get(table_key)
        if config is None:
            raise ValueError("同步任务尚未在 DATA_SYNC_TASKS 中配置")
        allowed = {"name", "database_url_env", "headers_env", "base_url", "target_table",
                   "method", "records_path", "page_param", "page_size_param", "column_case",
                   "request_params", "timeout", "retry_times", "page_size", "max_workers",
                   "part_rows", "min_rows", "max_pages", "statement_timeout_ms"}
        if set(config) - allowed:
            raise ValueError("同步任务含未知配置字段")
        db_env = config.get("database_url_env", "DATA_SYNC_DATABASE_URL")
        if not isinstance(db_env, str) or not re.fullmatch(r"[A-Z_][A-Z0-9_]*", db_env):
            raise ValueError("database_url_env 必须为环境变量名称")
        database_url = env.get(db_env, "").strip()
        if not database_url:
            raise ValueError(f"缺少服务端配置：{db_env}")
        try:
            parsed = make_url(database_url)
            if parsed.get_backend_name() != "postgresql" or parsed.get_driver_name() != "psycopg2":
                raise ValueError()
        except Exception:
            raise ValueError("同步目标连接必须使用 PostgreSQL psycopg2") from None
        base_url = config.get("base_url", "")
        if not isinstance(base_url, str):
            raise ValueError("base_url 必须为 HTTP/HTTPS 地址")
        url = urlsplit(base_url)
        if url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password or url.query or url.fragment or any(c.isspace() for c in base_url):
            raise ValueError("base_url 必须为不含凭证、查询参数的 HTTP/HTTPS 地址")
        try:
            if url.port is not None and not 1 <= url.port <= 65535:
                raise ValueError()
        except ValueError:
            raise ValueError("base_url 端口无效") from None
        from .schema import split_table_name
        target = config.get("target_table", "")
        if not isinstance(target, str):
            raise ValueError("target_table 必须为表名")
        if any(not part or len(part.encode("utf-8")) > 63 or any(ord(c) < 32 for c in part)
               for part in split_table_name(target)):
            raise ValueError("target_table 必须包含有效的 Schema 和表名")
        method = config.get("method", "GET")
        if method not in {"GET", "POST"}:
            raise ValueError("同步源 method 只支持 GET 或 POST")
        params = config.get("request_params", {})
        if not isinstance(params, dict):
            raise ValueError("request_params 必须为对象")
        headers = {}
        header_env = config.get("headers_env")
        if header_env:
            if not isinstance(header_env, str) or not re.fullmatch(r"[A-Z_][A-Z0-9_]*", header_env):
                raise ValueError("headers_env 必须为环境变量名称")
            if not env.get(header_env):
                raise ValueError(f"缺少服务端配置：{header_env}")
            try:
                headers = json.loads(env[header_env])
            except (TypeError, ValueError):
                raise ValueError("同步源请求头必须为 JSON 对象") from None
        if not isinstance(headers, dict) or any(
            not isinstance(k, str) or not re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", k)
            or not isinstance(v, str) or any(ord(c) < 32 or ord(c) == 127 for c in v)
            for k, v in headers.items()
        ):
            raise ValueError("同步源请求头配置无效")
        strings = {key: config.get(key, default) for key, default in (
            ("records_path", "data"), ("page_param", "page"), ("page_size_param", "page_size"), ("column_case", "lower"))}
        if any(not isinstance(value, str) for value in strings.values()):
            raise ValueError("分页、记录路径和列名模式必须为字符串")
        if not strings["page_param"] or not strings["page_size_param"] or strings["page_param"] == strings["page_size_param"]:
            raise ValueError("分页参数名称必须非空且互不相同")
        if strings["column_case"] not in {"lower", "none"}:
            raise ValueError("column_case 只支持 lower 或 none")
        return cls(table_key=table_key, target_table=target, database_url=database_url,
            base_url=base_url, headers=headers, request_params=params, method=method, **strings,
            timeout=_integer(config, "timeout", 60, maximum=600),
            retry_times=_integer(config, "retry_times", 3, maximum=10),
            page_size=_integer(config, "page_size", 5000, maximum=100000),
            max_workers=_integer(config, "max_workers", 1, maximum=16),
            part_rows=_integer(config, "part_rows", 100000, maximum=1000000),
            min_rows=_integer(config, "min_rows", 1),
            max_pages=_integer(config, "max_pages", 100000, maximum=1000000),
            statement_timeout_ms=_integer(config, "statement_timeout_ms", 3600000, maximum=86400000),
            tmp_dir=str(Path(env.get("DATA_SYNC_TMP_DIR", "data/sync")).resolve()))


def configuration_status(table_key):
    try:
        cfg = SyncConfig.from_env(table_key)
        return {"ready": True, "message": "服务端配置已就绪", "target_table": cfg.target_table}
    except ValueError as exc:
        return {"ready": False, "message": str(exc), "target_table": ""}
