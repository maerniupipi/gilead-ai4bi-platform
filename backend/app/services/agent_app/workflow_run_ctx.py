"""工作流单次执行上下文与变量解析。"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy.orm import Session
from ..conversation_history import history_context_values

_VAR_PATTERN = re.compile(r"\{\{\s*([^}]+?)\s*\}\}")
# 仅英文标识的命名占位（如 {{input}}）；含「节点.字段」的引用仍走 _VAR_PATTERN + resolve_dotted
_NAMED_SLOT_PATTERN = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")
_LEGACY_DOLLAR_SLOT_PATTERN = re.compile(r"\$\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}")


@dataclass
class WorkflowRunContext:
    db: Session
    run_id: str
    agent_app_id: int
    version_id: int
    inputs: Dict[str, Any]
    call_stack: List[Tuple[int, int]]
    nodes_by_id: Dict[str, dict]
    nodes: List[dict]
    edges: List[dict]
    var_to_id: Dict[str, str]
    id_to_var: Dict[str, str]
    context: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    final_output: Optional[str] = None
    steps: List[dict] = field(default_factory=list)
    thought_events: List[dict] = field(default_factory=list)
    legacy_cache: Dict[str, Any] = field(default_factory=dict)
    stream: bool = False
    skipped_node_ids: Set[str] = field(default_factory=set)
    # Internal presentation state; never exported or serialized in workflow events.
    result_collector: Any = None
    trace_id: Optional[str] = None


def _kind_stem(kind: str) -> str:
    return {
        "llm": "LLM",
        "script": "脚本",
        "agent": "智能体",
        "lab": "实验室",
        "atomic": "原子能力",
        "externalApi": "外部API",
        "selector": "选择器",
    }.get(kind or "", kind or "node")


def build_var_name_maps(nodes: List[dict]) -> Tuple[Dict[str, str], Dict[str, str]]:
    """
    计算「节点名称/变量名」到 node_id 的映射，以及 node_id 的主显示名。

    新规则：
    - 主命名空间优先使用 data.label（即前端节点名称），更符合可视化配置习惯；
    - start 节点固定为「开始」；
    - 旧数据中的 data.var_name 作为兼容别名（alias）保留可解析能力。
    """
    used_primary: Set[str] = set()
    id_to_var: Dict[str, str] = {}  # node_id -> 主名称（用于 exports 键）
    alias_pairs: List[Tuple[str, str]] = []  # (alias, node_id)

    for n in nodes:
        nid = n.get("id")
        if not nid:
            continue
        data = n.get("data") or {}
        kind = data.get("kind") or ""
        label = (data.get("label") or "").strip()
        raw_var = (data.get("var_name") or "").strip()
        if kind == "start":
            primary = "开始"
        elif label:
            primary = label
        elif raw_var:
            primary = raw_var
        else:
            primary = ""
        if primary:
            if primary in used_primary:
                raise ValueError(f"节点名称重复: {primary}")
            used_primary.add(primary)
            id_to_var[nid] = primary
        if raw_var:
            alias_pairs.append((raw_var, nid))

    counters: Dict[str, int] = {}
    for n in nodes:
        nid = n.get("id")
        if not nid or nid in id_to_var:
            continue
        data = n.get("data") or {}
        kind = data.get("kind") or ""
        if kind == "userInput":
            candidate = "用户输入"
            if candidate in used_primary:
                i = 2
                while f"{candidate}_{i}" in used_primary:
                    i += 1
                candidate = f"{candidate}_{i}"
        elif kind == "output":
            candidate = "输出"
            if candidate in used_primary:
                i = 2
                while f"{candidate}_{i}" in used_primary:
                    i += 1
                candidate = f"{candidate}_{i}"
        else:
            stem = _kind_stem(kind)
            counters[stem] = counters.get(stem, 0) + 1
            candidate = f"{stem}_{counters[stem]}"
            while candidate in used_primary:
                counters[stem] += 1
                candidate = f"{stem}_{counters[stem]}"
        used_primary.add(candidate)
        id_to_var[nid] = candidate

    var_to_id = {v: k for k, v in id_to_var.items()}
    for alias, nid in alias_pairs:
        if alias in var_to_id and var_to_id[alias] != nid:
            raise ValueError(f"变量名冲突: {alias}")
        var_to_id[alias] = nid
    return var_to_id, id_to_var


def resolve_dotted(ctx: WorkflowRunContext, ref: str) -> Any:
    ref = (ref or "").strip()
    if ref == 'history_question':
        return history_context_values(ctx.inputs)['history_question']
    if "." not in ref:
        raise ValueError(f"无效变量引用（需要「变量名.字段」）: {ref}")
    # Match the longest node name so a user-visible label may itself contain dots.
    names = [name for name in ctx.var_to_id if ref.startswith(name + ".")]
    if names:
        var_name = max(names, key=len)
        nid = ctx.var_to_id[var_name]
        if nid not in ctx.context:
            if nid in ctx.skipped_node_ids:
                return None
            raise ValueError(f"引用的上游节点尚未执行或当前分支未执行: {var_name}")
        path = ref[len(var_name) + 1:]
        cur: Any = ctx.context[nid]
    elif ref.startswith("metadata.") and "metadata" in ctx.inputs:
        path = ref[len("metadata."):]
        cur = ctx.inputs["metadata"]
    else:
        raise ValueError(f"未找到变量名: {ref.split('.', 1)[0]}")
    parts = re.sub(r"\[(\d+)\]", r".\1", path).split(".")
    for p in parts:
        if cur is None:
            return None
        if isinstance(cur, dict):
            if p not in cur:
                raise ValueError(f"变量引用字段不存在: {ref}（缺少 {p}）")
            cur = cur[p]
        elif isinstance(cur, (list, tuple)) and p.isdigit():
            index = int(p)
            if index >= len(cur):
                raise ValueError(f"变量引用数组下标越界: {ref}")
            cur = cur[index]
        else:
            raise ValueError(f"无法从非对象上取字段: {p}")
    return cur


def substitute_template(ctx: WorkflowRunContext, template: str) -> str:
    if not template:
        return ""

    def repl(m: re.Match) -> str:
        key = m.group(1).strip()
        val = resolve_dotted(ctx, key)
        return template_text(val)

    return _VAR_PATTERN.sub(repl, template)


def template_text(value: Any) -> str:
    """Use JSON for structured values, so prompts and API templates stay interoperable."""
    if value is None:
        return ""
    if isinstance(value, (dict, list, bool)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def substitute_llm_prompt(
    ctx: WorkflowRunContext, template: str, param_bindings: Optional[Dict[str, Any]] = None
) -> str:
    """
    LLM 节点模板：先替换命名占位 {{name}}（ASCII 标识），再替换 {{节点.字段}}。
    param_bindings[name] 支持 source_mode: ref|const，以及 ref / const_value。
    """
    if not template:
        return ""
    bindings = param_bindings or {}

    def resolve_named_value(name: str) -> Any:
        if name == 'history_question':
            return history_context_values(ctx.inputs)['history_question']
        spec = bindings.get(name) or {}
        if isinstance(spec, dict):
            mode = (spec.get("source_mode") or "ref").strip().lower()
            if mode == "const":
                return spec.get("const_value")
            ref = (spec.get("ref") or "").strip()
            if ref:
                return resolve_dotted(ctx, ref)
        if name in ctx.inputs:
            return ctx.inputs.get(name)
        for bag in reversed(list(ctx.context.values())):
            if isinstance(bag, dict) and name in bag:
                return bag.get(name)
        return None

    def repl(m: re.Match) -> str:
        name = (m.group(1) or m.group(2)).strip()
        val = resolve_named_value(name) if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) else resolve_dotted(ctx, name)
        return template_text(val)

    # Replace only the original template; user values may contain literal braces.
    return re.sub(r"\{\{\s*([^}]+?)\s*\}\}|\$\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}", repl, template)


def reachable_from(start_id: str, edges: List[dict]) -> Set[str]:
    from collections import defaultdict, deque

    adj: Dict[str, List[str]] = defaultdict(list)
    for e in edges or []:
        s, t = e.get("source"), e.get("target")
        if s and t:
            adj[s].append(t)
    seen = {start_id}
    dq = deque([start_id])
    while dq:
        u = dq.popleft()
        for v in adj[u]:
            if v not in seen:
                seen.add(v)
                dq.append(v)
    return seen


def topological_order(node_ids: Set[str], edges: List[dict]) -> List[str]:
    from collections import defaultdict, deque

    indeg: Dict[str, int] = {nid: 0 for nid in node_ids}
    adj: Dict[str, List[str]] = defaultdict(list)
    for e in edges or []:
        s, t = e.get("source"), e.get("target")
        if s in node_ids and t in node_ids:
            adj[s].append(t)
            indeg[t] = indeg.get(t, 0) + 1
    q = deque([nid for nid in node_ids if indeg.get(nid, 0) == 0])
    out: List[str] = []
    while q:
        u = q.popleft()
        out.append(u)
        for v in adj[u]:
            indeg[v] -= 1
            if indeg[v] == 0:
                q.append(v)
    if len(out) != len(node_ids):
        raise ValueError("工作流存在环或存在无法排序的节点")
    return out


def flatten_exports(
    context: Dict[str, Dict[str, Any]], id_to_var: Dict[str, str], final_output: Optional[str]
) -> Dict[str, Any]:
    """供智能体节点 output_mapping：var.field -> 值，以及 output -> 最终文本。"""
    exp: Dict[str, Any] = {}
    if final_output is not None:
        exp["output"] = final_output
    for nid, bag in context.items():
        vn = id_to_var.get(nid, nid)
        if not isinstance(bag, dict):
            continue
        for k, val in bag.items():
            exp[f"{vn}.{k}"] = val
    return exp
