"""实验室 / 网关：用请求体中的 features 替换提示词里同名的 {{ key }} 占位符。"""

from __future__ import annotations

import json
import re
from typing import Any, Dict

_PLACEHOLDER_RE = re.compile(r"\{\{\s*([^}]+?)\s*\}\}")

_MISSING = object()

# 由流水线实际结果生成，配置预替换时不能由请求 features 提供。
LAB_RUNTIME_FEATURE_KEYS = frozenset({"qs_recall"})


def without_runtime_features(features: Dict[str, Any]) -> Dict[str, Any]:
    result = {key: value for key, value in (features or {}).items() if key not in LAB_RUNTIME_FEATURE_KEYS}
    if isinstance(result.get("features"), dict):
        result["features"] = without_runtime_features(result["features"])
    return result


def _get_feature_value(features: Dict[str, Any], path_expr: str) -> Any:
    """
    按路径从 features 取值，供 replace_features_in_template 使用。

    - 支持点号路径：``{{ max_year }}``、``{{ features.max_year }}``（嵌套 dict）。
    - 兼容旧模板：占位符为 ``{{ features.xxx }}`` 但请求体为扁平 ``{ "max_year": 2026 }`` 时，
      若顶层不存在 ``features`` 键，则退化为从根上解析 ``xxx``（即去掉首段 ``features``）。
    - 兼容更旧行为：``{{ features.anything }}`` 且 ``features`` 为标量时，整段替换为该标量。
    """
    if not path_expr or not isinstance(features, dict):
        return _MISSING
    raw = path_expr.split("|", 1)[0].strip()
    if not raw:
        return _MISSING
    parts = [p.strip() for p in raw.split(".") if p.strip()]
    if not parts:
        return _MISSING

    def walk(obj: Any, segments: list[str]) -> Any:
        cur: Any = obj
        for p in segments:
            if isinstance(cur, dict) and p in cur:
                cur = cur[p]
            else:
                return _MISSING
        return cur

    v = walk(features, parts)
    if v is not _MISSING:
        return v

    # 扁平 body：模板写 {{ features.max_year }}，实际传 { "max_year": 2026 }
    if len(parts) >= 2 and parts[0] == "features" and "features" not in features:
        v2 = walk(features, parts[1:])
        if v2 is not _MISSING:
            return v2

    # 更旧：{{ features.xxx }} 且 "features" 为标量，整段占位符替换为该值
    fv = features.get("features")
    if len(parts) >= 2 and parts[0] == "features" and not isinstance(fv, dict) and fv is not None:
        return fv

    return _MISSING


def replace_features_in_template(template: str, features: Dict[str, Any]) -> str:
    if not template or not features:
        return template

    def repl(m: re.Match[str]) -> str:
        raw = m.group(1).strip()
        v = _get_feature_value(features, raw)
        if v is _MISSING:
            return m.group(0)
        if v is None:
            return ""
        if isinstance(v, (dict, list)):
            return json.dumps(v, ensure_ascii=False)
        return str(v)

    return _PLACEHOLDER_RE.sub(repl, template)


def apply_features_to_lab_config_prompts(cfg: Dict[str, Any], features: Dict[str, Any]) -> Dict[str, Any]:
    features = without_runtime_features(features)
    if not features:
        return cfg
    out = json.loads(json.dumps(cfg, ensure_ascii=False))
    adv = (out.get("request") or {}).get("advanced_config")
    if not isinstance(adv, dict):
        return out
    for block in adv.values():
        if isinstance(block, dict) and isinstance(block.get("prompt"), str):
            block["prompt"] = replace_features_in_template(block["prompt"], features)
    return out
