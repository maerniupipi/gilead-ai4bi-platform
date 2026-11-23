"""
按 APP_ENV 加载 backend/config/environments/{dev|uat|prod}.env。

须在读取 DATABASE_URL / REDIS_* 等环境变量的模块（如 database、redis_client）
之前调用一次；FastAPI 入口 main.py 已最先调用。
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

_VALID = frozenset({"dev", "uat", "prod"})
_LOADED = False
_LAST_PATH: Path | None = None


def _backend_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def normalize_app_env(raw: str | None) -> str:
    v = (raw or "dev").strip().lower()
    if v not in _VALID:
        logger.warning("APP_ENV=%r 无效，有效值为 dev/uat/prod，已回退为 dev", raw)
        return "dev"
    return v


def resolve_env_file(app_env: str | None = None) -> Path:
    env = normalize_app_env(app_env if app_env is not None else os.getenv("APP_ENV"))
    return _backend_root() / "config" / "environments" / f"{env}.env"


def load_app_environment(*, app_env: str | None = None, override: bool = False) -> Path | None:
    """
    加载环境变量文件。幂等：重复调用仅第一次生效。

    优先级：
    1. 若设置了 DOTENV_PATH 且文件存在，则加载该路径（便于容器挂载单文件）。
    2. 默认开发环境先加载本机 .env.local，再加载 config/environments/dev.env。
    3. 其他环境加载 config/environments/{APP_ENV}.env（APP_ENV 默认 dev）。

    若目标文件不存在：记录告警并跳过，完全依赖进程已注入的环境变量（CI/K8s 场景）。
    """
    global _LOADED, _LAST_PATH
    if _LOADED:
        return _LAST_PATH

    dotenv_path = (os.getenv("DOTENV_PATH") or "").strip()
    if dotenv_path:
        p = Path(dotenv_path).expanduser().resolve()
        if p.is_file():
            load_dotenv(p, override=override)
            ae = normalize_app_env(os.getenv("APP_ENV"))
            os.environ.setdefault("APP_ENV", ae)
            _LOADED = True
            _LAST_PATH = p
            logger.info("已从 DOTENV_PATH 加载环境: %s", p)
            return p
        logger.warning("DOTENV_PATH 指向的文件不存在: %s，将尝试默认路径", p)

    env_name = normalize_app_env(app_env if app_env is not None else os.getenv("APP_ENV"))
    os.environ["APP_ENV"] = env_name

    # Per-machine integration settings take precedence over dev defaults; an
    # explicitly supplied process environment or DOTENV_PATH still takes precedence.
    if env_name == "dev":
        load_dotenv(_backend_root() / ".env.local", override=override)

    path = _backend_root() / "config" / "environments" / f"{env_name}.env"
    if path.is_file():
        load_dotenv(path, override=override)
        _LOADED = True
        _LAST_PATH = path
        logger.info("已加载环境配置 APP_ENV=%s -> %s", env_name, path)
        return path

    logger.info(
        "未找到环境文件 %s，使用进程已有环境变量。"
        "本地可: cp config/environments/%s.env.example config/environments/%s.env",
        path,
        env_name,
        env_name,
    )
    _LOADED = True
    _LAST_PATH = None
    return None
