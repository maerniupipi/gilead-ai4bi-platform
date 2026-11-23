"""
pytest 收集前加载与 FastAPI 一致的环境文件（config/environments/{APP_ENV}.env）。
"""
from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory

# Unit tests must not implicitly connect to the developer's configured MySQL
# database (PPT/template fallbacks can open a default session during tests).
_test_database = TemporaryDirectory(prefix='chatbi-unit-db-')
os.environ.setdefault('DATABASE_URL', 'sqlite:///' + str(Path(_test_database.name) / 'unit.sqlite3'))
os.environ.setdefault('DB_CREATE_ALL_ON_STARTUP', 'false')

from tests.env_setup import ensure_loaded

ensure_loaded()
