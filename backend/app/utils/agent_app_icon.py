"""智能体应用 icon：兼容 MySQL utf8（非 utf8mb4）列，避免 4 字节字符写入失败。"""

from __future__ import annotations

from typing import Optional

# 不含补充平面字符，单字符 UTF-8 最长 3 字节，可写入 utf8 列
DEFAULT_AGENT_APP_ICON = "*"
_MAX_ICON_CHARS = 4


def normalize_agent_app_icon(raw: Optional[str]) -> str:
    """
    - 仅保留 Unicode 基本多文种平面（ord <= 0xFFFF），过滤补充平面字符
    - 最多保留 _MAX_ICON_CHARS 个字符
    """
    if raw is None:
        return DEFAULT_AGENT_APP_ICON
    s = str(raw).strip()
    if not s:
        return DEFAULT_AGENT_APP_ICON
    out: list[str] = []
    for ch in s:
        if ord(ch) > 0xFFFF:
            continue
        out.append(ch)
        if len(out) >= _MAX_ICON_CHARS:
            break
    return "".join(out) if out else DEFAULT_AGENT_APP_ICON
