"""供独立运行的测试脚本在导入业务模块前加载环境。"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def ensure_loaded(app_env: str | None = None) -> None:
    root = Path(__file__).resolve().parent.parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    if app_env:
        os.environ["APP_ENV"] = app_env
    else:
        os.environ.setdefault("APP_ENV", "dev")
    from app.core.env_loader import load_app_environment

    load_app_environment(app_env=app_env)
