"""合并实验室默认 config 与项目 config_json（与前端 mergeAutobiLabConfig 行为一致）。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


def deep_merge_autobi_lab(base: Any, override: Any) -> Any:
    if not isinstance(base, dict):
        return override if override is not None else base
    if not isinstance(override, dict):
        return base
    out = dict(base)
    for k, ov in override.items():
        bv = base.get(k)
        if isinstance(bv, dict) and isinstance(ov, dict):
            out[k] = deep_merge_autobi_lab(bv, ov)
        else:
            out[k] = ov
    return out


def load_lab_default_config_file() -> Dict[str, Any]:
    p = Path(__file__).resolve().parent / "lab_default_config.json"
    if not p.is_file():
        return {
            "knowledge_base_id": None,
            "model_bindings": {},
            "request": {"messages": [], "stream": False, "advanced_config": {}},
        }
    return json.loads(p.read_text(encoding="utf-8"))


def merge_lab_config(project_cfg: Dict[str, Any]) -> Dict[str, Any]:
    base = load_lab_default_config_file()
    return deep_merge_autobi_lab(base, expand_legacy_config(project_cfg))


def expand_legacy_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Read compact projects in the same seven-step format as ordinary projects."""
    mode = config.get("lab_mode")
    if mode not in ("recall", "sql"):
        return config
    defaults = load_lab_default_config_file()
    advanced = defaults["request"]["advanced_config"]
    # These projects used only the SQL model. Do not enable an unbound model on upgrade.
    for name in ("knowledge_rewrite_config", "ner_retrieval_config", "bi_summary_config", "chart_drawing_config"):
        advanced[name]["enable"] = False
    expanded = deep_merge_autobi_lab(defaults, config)
    adv = expanded["request"]["advanced_config"]
    adv["output_stage"] = mode
    adv["data_scope_policy"] = "ddi"
    rules = expanded.pop("atomic_sql_rules", "")
    if rules:
        adv["nl2sql_config"]["prompt"] += "\n" + rules
    expanded.pop("lab_mode")
    return expanded
