"""Conversions shared by node fields whose type is configured in the editor."""
from __future__ import annotations

import json
import math
import re
from typing import Any


def as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list, bool)):
        return json.dumps(value, ensure_ascii=False, allow_nan=False)
    return str(value)


def coerce_value(value: Any, field_type: str | None, field_name: str, *, coerce: bool = True) -> Any:
    """Parse editor constants and validate referenced values without losing false/0."""
    if value is None or not field_type:
        return value
    kind = field_type.strip().lower()
    list_match = re.fullmatch(r"(?:list|array)\s*<\s*(string|number|bool|boolean|object)\s*>", kind)
    if list_match:
        item_kind = "boolean" if list_match.group(1) == "bool" else list_match.group(1)
        kind = f"array_{item_kind}"
    kind = {"bool": "boolean", "list": "array", "integer": "number", "int": "number"}.get(kind, kind)
    try:
        if kind == "string":
            if not coerce and not isinstance(value, str):
                raise ValueError("需要文本")
            return as_text(value)
        if kind == "boolean":
            if isinstance(value, bool):
                return value
            if coerce and isinstance(value, str) and value.strip().lower() in ("true", "false"):
                return value.strip().lower() == "true"
            raise ValueError("需要 true 或 false")
        if kind == "number":
            if isinstance(value, bool):
                raise ValueError("布尔值不是数字")
            parsed = json.loads(value.strip()) if coerce and isinstance(value, str) else value
            if not isinstance(parsed, (int, float)) or isinstance(parsed, bool) or not math.isfinite(parsed):
                raise ValueError("需要有限数字")
            return parsed
        if kind == "object" or kind == "array" or kind.startswith("array_"):
            parsed = json.loads(value) if coerce and isinstance(value, str) else value
            expected = dict if kind == "object" else list
            if not isinstance(parsed, expected):
                raise ValueError("需要 JSON 对象" if expected is dict else "需要 JSON 数组")
            if kind.startswith("array_"):
                item_kind = kind[len("array_"):]
                return [coerce_value(item, item_kind, f"{field_name}[{i}]", coerce=coerce) for i, item in enumerate(parsed)]
            return parsed
        raise ValueError(f"不支持的类型 {field_type}")
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"字段 {field_name} 必须符合 {field_type} 类型: {exc}") from exc
