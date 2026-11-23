"""将 AI 输出的 workflow_design 转为画布 workflow_json {nodes, edges}。"""

from __future__ import annotations

import copy
import json
import re
import uuid
from collections import defaultdict, deque
from typing import Any, Dict, List, Optional, Set, Tuple

_KIND_LABEL = {
    "start": "开始",
    "userInput": "用户输入",
    "llm": "LLM",
    "script": "脚本",
    "selector": "选择器",
    "agent": "智能体",
    "lab": "实验室",
    "externalApi": "外部API",
    "output": "输出",
}

_PARAM_PLACEHOLDER = re.compile(r"\{\{PARAM:([^}]+)\}\}")


def _new_id() -> str:
    return str(uuid.uuid4())


def _default_data(kind: str, label: str) -> Dict[str, Any]:
    base: Dict[str, Any] = {"kind": kind, "label": label}
    if kind == "llm":
        base["llm_config"] = {
            "provider_id": None,
            "model_name": "",
            "temperature": 0.7,
            "max_tokens": 2000,
            "top_p": 0.9,
            "context_vars": [],
            "system_prompt": "",
            "use_user_prompt_template": False,
            "user_prompt": "",
            "param_bindings": {},
        }
    elif kind == "script":
        base["script_config"] = {
            "code": (
                "def main(arg1: str):\n"
                '    return {\n'
                '        "result": arg1,\n'
                "    }\n"
            ),
            "input_vars": [{"name": "arg1", "source_mode": "ref", "ref": "", "type": "string"}],
            "output_vars": [{"name": "result", "type": "string"}],
        }
    elif kind == "agent":
        base["agent_config"] = {
            "target_app_id": None,
            "target_version_id": None,
            "input_mapping": [],
            "output_mapping": [],
            "sse_output_thoughts": True,
        }
    elif kind == "lab":
        base["lab_config"] = {"project_id": None, "input_mapping": [], "sse_output_thoughts": True}
    elif kind == "externalApi":
        base["api_config"] = {
            "method": "GET",
            "base_url": "",
            "path": "",
            "timeout": 60,
            "headers": [],
            "query": [],
            "output_vars": [],
        }
    elif kind == "selector":
        base["selector_config"] = {
            "cases": [
                {"id": "case-0", "conditions": [{"ref": "", "op": "starts_with", "value": ""}]},
                {"id": "case-1", "conditions": [{"ref": "", "op": "eq", "value": ""}]},
            ]
        }
    elif kind == "output":
        base["output_config"] = {"content_template": ""}
    elif kind == "userInput":
        base["fields"] = [
            {
                "variable": "query",
                "display": "用户问题",
                "type": "string",
                "required": True,
                "hidden": False,
                "source_mode": "runtime",
            }
        ]
    return base


def _deep_replace_params(obj: Any, filled: Dict[str, Any]) -> Any:
    if isinstance(obj, str):
        def repl(m: re.Match) -> str:
            key = m.group(1).strip()
            v = filled.get(key)
            return "" if v is None else str(v)

        return _PARAM_PLACEHOLDER.sub(repl, obj)
    if isinstance(obj, dict):
        return {k: _deep_replace_params(v, filled) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_deep_replace_params(x, filled) for x in obj]
    return obj


def _merge_config(kind: str, default_data: Dict[str, Any], cfg: Dict[str, Any]) -> None:
    if not cfg:
        return
    if kind == "llm" and "llm_config" in cfg:
        default_data["llm_config"] = {**default_data.get("llm_config", {}), **cfg["llm_config"]}
    elif kind == "script" and "script_config" in cfg:
        default_data["script_config"] = {**default_data.get("script_config", {}), **cfg["script_config"]}
    elif kind == "agent" and "agent_config" in cfg:
        default_data["agent_config"] = {**default_data.get("agent_config", {}), **cfg["agent_config"]}
    elif kind == "lab" and "lab_config" in cfg:
        default_data["lab_config"] = {**default_data.get("lab_config", {}), **cfg["lab_config"]}
    elif kind == "externalApi" and "api_config" in cfg:
        default_data["api_config"] = {**default_data.get("api_config", {}), **cfg["api_config"]}
    elif kind == "selector" and "selector_config" in cfg:
        default_data["selector_config"] = {**default_data.get("selector_config", {}), **cfg["selector_config"]}
    elif kind == "output":
        oc = default_data.setdefault("output_config", {})
        if "output_config" in cfg and isinstance(cfg["output_config"], dict):
            oc.update(cfg["output_config"])
        if "content_template" in cfg:
            oc["content_template"] = cfg["content_template"]
    elif kind == "userInput" and "fields" in cfg:
        default_data["fields"] = cfg["fields"]
    # 允许直接把 config 摊平在 cfg 根上（AI 简写）
    elif kind == "llm" and any(k in cfg for k in ("provider_id", "model_name", "system_prompt")):
        lc = default_data.setdefault("llm_config", {})
        for k in (
            "provider_id",
            "model_name",
            "temperature",
            "max_tokens",
            "top_p",
            "system_prompt",
            "context_vars",
            "use_user_prompt_template",
            "user_prompt",
            "param_bindings",
        ):
            if k in cfg:
                lc[k] = cfg[k]
    elif kind == "lab" and "project_id" in cfg:
        default_data.setdefault("lab_config", {})["project_id"] = cfg["project_id"]
        if "input_mapping" in cfg:
            default_data["lab_config"]["input_mapping"] = cfg["input_mapping"]


def _node_type_for_kind(kind: str) -> str:
    return "wfSelector" if kind == "selector" else "wfCard"


def _topo_layers(
    semantic_ids: List[str], edges: List[Dict[str, Any]]
) -> Dict[str, int]:
    """按拓扑分层（BFS），用于横坐标。"""
    adj: Dict[str, List[str]] = defaultdict(list)
    indeg: Dict[str, int] = defaultdict(int)
    nodes_set = set(semantic_ids)
    for e in edges:
        s, t = e.get("source"), e.get("target")
        if s in nodes_set and t in nodes_set:
            adj[s].append(t)
            indeg[t] += 1
    roots = [n for n in semantic_ids if indeg.get(n, 0) == 0]
    if not roots:
        roots = [semantic_ids[0]] if semantic_ids else []
    layer: Dict[str, int] = {}
    q = deque([(r, 0) for r in roots])
    seen = set()
    while q:
        nid, L = q.popleft()
        if nid in seen:
            continue
        seen.add(nid)
        layer[nid] = max(layer.get(nid, 0), L)
        for nxt in adj.get(nid, []):
            indeg[nxt] = max(0, indeg.get(nxt, 1) - 1)
            q.append((nxt, L + 1))
    for n in semantic_ids:
        layer.setdefault(n, 0)
    return layer


def build_workflow_from_design(
    workflow_design: Dict[str, Any],
    filled_params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    workflow_design:
      app_name, description (optional)
      nodes: [{ semantic_id, kind, label, config? }]
      edges: [{ source, target }]  # semantic_id
    """
    filled_params = filled_params or {}
    raw_nodes = workflow_design.get("nodes") or []
    raw_edges = workflow_design.get("edges") or []

    design = copy.deepcopy(workflow_design)
    design = _deep_replace_params(design, filled_params)
    raw_nodes = design.get("nodes") or []
    raw_edges = design.get("edges") or []

    sem_to_uuid: Dict[str, str] = {}
    labels_used: Set[str] = set()

    def alloc_label(base: str) -> str:
        b = (base or "节点").strip() or "节点"
        if b not in labels_used:
            labels_used.add(b)
            return b
        i = 2
        while f"{b}_{i}" in labels_used:
            i += 1
        out = f"{b}_{i}"
        labels_used.add(out)
        return out

    # 预分配 uuid
    for n in raw_nodes:
        sid = n.get("semantic_id") or n.get("id")
        if not sid:
            sid = f"n_{_new_id()[:8]}"
            n["semantic_id"] = sid
        sem_to_uuid[sid] = _new_id()

    semantic_order = [n.get("semantic_id") or n.get("id") for n in raw_nodes]
    layer = _topo_layers([s for s in semantic_order if s], raw_edges)

    # 同层多个节点纵向错开
    layer_counts: Dict[int, int] = defaultdict(int)
    nodes_out: List[Dict[str, Any]] = []
    for n in raw_nodes:
        sid = n.get("semantic_id") or n.get("id")
        kind = (n.get("kind") or "llm").strip()
        default_l = (n.get("label") or "").strip() or _KIND_LABEL.get(kind, kind)
        label = alloc_label(default_l)
        uid = sem_to_uuid[sid]
        L = layer.get(sid, 0)
        y_off = layer_counts[L] * 140
        layer_counts[L] += 1
        data = _default_data(kind, label)
        if n.get("description"):
            data["description"] = str(n.get("description") or "")[:500]
        if n.get("caption"):
            data["caption"] = str(n.get("caption") or "")[:80]
        cfg = n.get("config") if isinstance(n.get("config"), dict) else {}
        _merge_config(kind, data, cfg)
        nodes_out.append(
            {
                "id": uid,
                "type": _node_type_for_kind(kind),
                "position": {"x": 80 + L * 300, "y": 80 + y_off},
                "data": data,
            }
        )

    edges_out: List[Dict[str, Any]] = []
    for i, e in enumerate(raw_edges):
        s = e.get("source")
        t = e.get("target")
        su = sem_to_uuid.get(s)
        tu = sem_to_uuid.get(t)
        if not su or not tu:
            continue
        edges_out.append(
            {
                "id": e.get("id") or f"e_{_new_id()}",
                "source": su,
                "target": tu,
                "type": "wfPlus",
            }
        )

    return {"nodes": nodes_out, "edges": edges_out}
