import asyncio
import base64
import collections
import datetime
import decimal
import hashlib
import inspect
import json
import keyword
import math
import operator
import os
import random
import re
import statistics
import sys
import time
import urllib
import uuid
import itertools
import functools
import builtins
from types import SimpleNamespace
from collections import defaultdict, Counter
from typing import List, Dict, Optional, Any
from urllib import parse as urllib_parse

import sqlparse
from RestrictedPython import compile_restricted_exec, safe_globals
from RestrictedPython.Eval import default_guarded_getitem
from RestrictedPython.Guards import guarded_iter_unpack_sequence, guarded_unpack_sequence
from RestrictedPython.PrintCollector import PrintCollector

from ..workflow_run_ctx import WorkflowRunContext, resolve_dotted
from ._values import coerce_value


_COMMON_BUILTIN_NAMES = (
    "all",
    "any",
    "bytearray",
    "dict",
    "enumerate",
    "filter",
    "frozenset",
    "list",
    "map",
    "max",
    "memoryview",
    "min",
    "next",
    "object",
    "reversed",
    "set",
    "sum",
    "type",
)


_INPLACE_OPERATORS = {
    "+=": operator.iadd, "-=": operator.isub, "*=": operator.imul,
    "/=": operator.itruediv, "//=": operator.ifloordiv, "%=": operator.imod,
    "**=": operator.ipow, "<<=": operator.ilshift, ">>=": operator.irshift,
    "&=": operator.iand, "^=": operator.ixor, "|=": operator.ior,
    "@=": operator.imatmul,
}


def _default_input(ctx: WorkflowRunContext) -> Any:
    for value in (ctx.final_output, ctx.inputs.get("input"), ctx.inputs.get("message")):
        if value is not None:
            return value
    return ""


def _variable_rows(rows: Any, label: str) -> list:
    if not isinstance(rows, list):
        raise ValueError(f"{label}配置必须是数组")
    seen = set()
    result = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError(f"{label}配置必须是对象")
        name = row.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"{label}名称不能为空")
        name = name.strip()
        if name in seen:
            raise ValueError(f"{label}名称重复: {name}")
        if label == "输入变量" and (
            not name.isidentifier() or keyword.iskeyword(name) or name.startswith("_")
        ):
            raise ValueError(f"输入变量名称无效: {name}；请使用不以下划线开头的 Python 参数名")
        if "." in name:
            raise ValueError(f"{label}名称不能包含点号: {name}")
        seen.add(name)
        result.append((name, row))
    return result


def _validate_json_output(value: Any, path: str = "输出", ancestors=None) -> None:
    """Reject values that would fail or silently change in JSON workflow traces."""
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if math.isfinite(value):
            return
        raise ValueError(f"{path} 不是有效 JSON 数字；不能返回 NaN 或 Infinity")
    if not isinstance(value, (dict, list)):
        raise ValueError(f"{path} 不是有效 JSON 值（{type(value).__name__}）；请转换为文本、数字、布尔、对象或数组")
    ancestors = set() if ancestors is None else ancestors
    if id(value) in ancestors:
        raise ValueError(f"{path} 含循环引用，无法作为 JSON 输出")
    ancestors.add(id(value))
    try:
        if isinstance(value, dict):
            for key, child in value.items():
                if not isinstance(key, str):
                    raise ValueError(f"{path} 的 JSON 对象键必须是字符串")
                _validate_json_output(child, f"{path}.{key}", ancestors)
        else:
            for index, child in enumerate(value):
                _validate_json_output(child, f"{path}[{index}]", ancestors)
    finally:
        ancestors.remove(id(value))


def _runtime_import(name, globals=None, locals=None, fromlist=(), level=0):
    """Import any absolute module available in the workflow runtime."""
    if level != 0:
        raise ImportError("工作流脚本不支持相对导入，请使用绝对模块名")
    if not isinstance(name, str) or not name.strip():
        raise ImportError("导入模块名不能为空")
    try:
        return builtins.__import__(name, globals, locals, fromlist, level)
    except ModuleNotFoundError as exc:
        missing = exc.name or name
        raise ImportError(
            f"运行环境未安装模块: {missing}；可用模块以 Python 标准库、"
            "backend/requirements.txt 和工作流脚本任务模块清单为准"
        ) from exc


def _parse_thought_tag(text: str) -> dict:
    raw = str(text or "")
    m = re.match(r"^【Tag_([^】]+)】[:：]?(.*)$", raw, flags=re.S)
    if not m:
        return {"tag": "", "raw": raw, "payload": raw}
    return {"tag": m.group(1).strip(), "raw": raw, "payload": (m.group(2) or "").strip()}


def _run_restricted_script(code: str, kwargs: dict, legacy_params: SimpleNamespace) -> dict:
    if not isinstance(code, str) or not code.strip():
        raise ValueError("脚本代码不能为空；请定义 main(...)")
    r = compile_restricted_exec(code, filename="<workflow-script>")
    if r.errors:
        raise ValueError(f"脚本编译失败: {r.errors}")
    g = dict(safe_globals)
    g["__builtins__"] = dict(g.get("__builtins__") or {})
    g["__builtins__"]["__import__"] = _runtime_import
    g["__builtins__"].update(
        {name: getattr(builtins, name) for name in _COMMON_BUILTIN_NAMES}
    )
    g["_write_"] = lambda ob: ob
    g["_getiter_"] = iter
    g["_getitem_"] = default_guarded_getitem
    g["_unpack_sequence_"] = guarded_unpack_sequence
    g["_iter_unpack_sequence_"] = guarded_iter_unpack_sequence
    g["_print_"] = PrintCollector
    g["_inplacevar_"] = lambda op, left, right: _INPLACE_OPERATORS[op](left, right)
    g["__metaclass__"] = type
    g["__name__"] = "workflow_script"
    # 标准库
    g["json"] = json
    g["math"] = math
    g["re"] = re
    g["datetime"] = datetime
    g["decimal"] = decimal
    g["collections"] = collections
    g["os"] = os
    g["sys"] = sys
    g["time"] = time
    g["random"] = random
    g["itertools"] = itertools
    g["functools"] = functools
    g["statistics"] = statistics
    g["hashlib"] = hashlib
    g["uuid"] = uuid
    g["base64"] = base64
    g["sqlparse"] = sqlparse
    g["urllib"] = urllib
    # 常用类型
    g["defaultdict"] = defaultdict
    g["Counter"] = Counter
    g["List"] = List
    g["Dict"] = Dict
    g["Optional"] = Optional
    g["Any"] = Any
    g["session"] = None

    def thought(*args, **kwargs):
        if len(args) >= 2:
            text = args[1]
        elif args:
            text = args[0]
        else:
            text = kwargs.get("text", "")
        legacy_params._thought_events.append(_parse_thought_tag(str(text or "")))

    g["thought"] = thought
    g["cache_set"] = lambda key, value: legacy_params._legacy_cache.__setitem__(key, value)
    g["cache_get"] = lambda key, default=None: legacy_params._legacy_cache.get(key, default)
    # A single namespace also makes helpers available during top-level execution
    # (for example a module-level comprehension that calls an earlier function).
    exec(r.code, g, g)
    main = g.get("main")
    if main is not None and callable(main):
        try:
            inspect.signature(main).bind(**kwargs)
        except TypeError as exc:
            raise ValueError(f"main 参数与输入变量不匹配: {exc}；请检查输入变量名称与函数参数") from exc
        out = main(**kwargs)
    else:
        legacy_out: dict = {}
        legacy_funcs = [
            (name.removeprefix("execute_"), fn)
            for name, fn in g.items()
            if name.startswith("execute_") and callable(fn)
        ]
        if not legacy_funcs:
            raise ValueError("脚本必须定义可调用的 main(...) 或 execute_xxx(params)")
        for key, fn in legacy_funcs:
            legacy_out[key] = fn(legacy_params)
        out = legacy_out
    if not isinstance(out, dict):
        raise ValueError("main 必须返回 dict")
    return out


def resolve_script_inputs(ctx: WorkflowRunContext, cfg: dict) -> dict:
    """Resolve the executable input contract, also reused by trace snapshots."""
    kwargs: dict = {}
    for name, item in _variable_rows(cfg.get("input_vars") or [], "输入变量"):
        mode = (item.get("source_mode") or "ref").strip().lower()
        if mode == "const":
            value = item.get("const_value")
        elif mode == "ref":
            ref = (item.get("ref") or "").strip()
            value = resolve_dotted(ctx, ref) if ref else _default_input(ctx)
        else:
            raise ValueError(f"输入变量 {name} 的来源必须是 ref 或 const")
        kwargs[name] = coerce_value(value, item.get("type"), f"输入变量 {name}", coerce=mode == "const")
    return kwargs


async def execute(ctx: WorkflowRunContext, node: dict) -> dict:
    data = node.get("data") or {}
    cfg = data.get("script_config") or {}
    code = cfg.get("code") or ""
    kwargs = resolve_script_inputs(ctx, cfg)
    out_vars = _variable_rows(cfg.get("output_vars") or [], "输出变量")
    legacy_input = next((v for v in kwargs.values() if v is not None), None)
    if legacy_input is None:
        legacy_input = _default_input(ctx)
    legacy_values = {
        "input": legacy_input,
        "metadata": {
            "inputs": dict(ctx.inputs or {}),
            "messages": ctx.inputs.get("messages", []),
            "conversation_id": ctx.inputs.get("conversation_id"),
        },
        "_thought_events": ctx.thought_events,
        "_legacy_cache": ctx.legacy_cache,
    }
    # User parameters such as input and metadata are valid main(...) arguments.
    # Merge them instead of passing duplicate keywords to SimpleNamespace.
    legacy_values.update(kwargs)
    from ..script_process import run_script
    raw = await run_script(code, kwargs, legacy_values)
    if "result" not in raw and "output" in raw:
        raw["result"] = raw["output"]
    if out_vars:
        missing = [name for name, _ in out_vars if name not in raw]
        if missing:
            raise ValueError(f"脚本返回值缺少已声明的输出变量: {', '.join(missing)}；请检查 return 字典中的键")
        result = {
            name: coerce_value(raw[name], row.get("type"), f"输出变量 {name}", coerce=False)
            for name, row in out_vars
        }
    else:
        result = raw
    _validate_json_output(result)
    return result
