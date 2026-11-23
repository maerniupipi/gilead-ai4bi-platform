"""
评测目标适配器 — 统一调用不同类型的评测目标
"""
import asyncio
import json
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)


def _env_int(name: str, default: int, minimum: int = 1) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return max(minimum, int(raw))
    except ValueError:
        logger.warning("环境变量 %s=%r 不是整数，使用默认值 %s", name, raw, default)
        return default


_target_executor = ThreadPoolExecutor(
    max_workers=_env_int("EVAL_TARGET_THREAD_WORKERS", 4),
    thread_name_prefix="eval-target",
)


async def _run_target_blocking(fn, *args, **kwargs):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_target_executor, partial(fn, *args, **kwargs))


def shutdown_target_executor() -> None:
    _target_executor.shutdown(wait=False, cancel_futures=True)

# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------


async def call_target(
    target_type: str,
    target_config: Dict[str, Any],
    input_prompt: str,
    input_variables: Optional[Dict[str, Any]] = None,
    timeout_seconds: Optional[int] = None,
) -> Dict[str, Any]:
    """
    统一调用评测目标，返回标准结构：
    {
        "raw_response": str | None,
        "parsed_response": Any,
        "execution_time_ms": int,
        "error": str | None,
    }
    """
    async_dispatch = {}
    sync_dispatch = {
        "lab": _call_lab_sync,
        "agent": _call_agent,
        "api": _call_api,
        "xlsx_qa": _call_xlsx_qa,
    }

    # 渲染模板变量
    rendered_prompt = _render_template(input_prompt, input_variables or {})
    timeout = _coerce_timeout(timeout_seconds or target_config.get("timeout"), 180)
    target_config = {**(target_config or {}), "timeout": timeout}

    start = time.time()
    try:
        if target_type in async_dispatch:
            handler = async_dispatch[target_type]
            result = await asyncio.wait_for(
                handler(target_config, rendered_prompt, input_variables or {}),
                timeout=timeout,
            )
        elif target_type in sync_dispatch:
            handler = sync_dispatch[target_type]
            result = await asyncio.wait_for(
                _run_target_blocking(handler, target_config, rendered_prompt, input_variables or {}),
                timeout=timeout,
            )
        else:
            result = {
                "raw_response": None,
                "parsed_response": None,
                "execution_time_ms": 0,
                "error": f"不支持的目标类型: {target_type}",
            }
        result["execution_time_ms"] = int((time.time() - start) * 1000)
        return result
    except asyncio.TimeoutError:
        return {
            "raw_response": None,
            "parsed_response": None,
            "execution_time_ms": int((time.time() - start) * 1000),
            "error": f"目标执行超时（{timeout}秒）",
        }
    except Exception as e:  # noqa: BLE001
        logger.exception("call_target failed: type=%s error=%s", target_type, e)
        return {
            "raw_response": None,
            "parsed_response": None,
            "execution_time_ms": int((time.time() - start) * 1000),
            "error": str(e),
        }


def _coerce_timeout(value: Any, default: int) -> int:
    try:
        timeout = int(value)
    except (TypeError, ValueError):
        timeout = default
    return max(30, min(timeout, 600))


# ---------------------------------------------------------------------------
# agent adapter
# ---------------------------------------------------------------------------


def _call_agent(
    target_config: Dict[str, Any],
    input_prompt: str,
    input_variables: Dict[str, Any],
) -> Dict[str, Any]:
    """调用 Agent 平台 API。"""
    base_url = (target_config.get("base_url") or "").rstrip("/")
    api_access_id = target_config.get("api_access_id") or ""
    timeout = target_config.get("timeout", 60)

    if not base_url or not api_access_id:
        return {
            "raw_response": None,
            "parsed_response": None,
            "error": "agent 配置缺少 base_url 或 api_access_id",
        }

    url = f"{base_url}/api/v1/agent-apps/{api_access_id}/chat"

    payload = {
        "messages": [{"role": "user", "content": input_prompt}],
        "stream": False,
    }

    # 合并额外参数
    extra_params = target_config.get("extra_params")
    if extra_params and isinstance(extra_params, dict):
        payload.update(extra_params)

    headers = _build_headers(target_config)

    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as e:
        return {
            "raw_response": e.response.text,
            "parsed_response": None,
            "error": f"HTTP {e.response.status_code}: {e.response.text[:500]}",
        }
    except Exception as e:  # noqa: BLE001
        return {"raw_response": None, "parsed_response": None, "error": str(e)}

    raw = json.dumps(data, ensure_ascii=False)
    parsed = _extract_agent_response(data)

    return {"raw_response": raw, "parsed_response": parsed, "error": None}


def _extract_agent_response(data: Any) -> Any:
    """从 agent API 响应中提取内容。"""
    if isinstance(data, dict):
        # 尝试多种常见结构
        if "content" in data:
            return data["content"]
        if "message" in data and isinstance(data["message"], dict):
            return data["message"].get("content")
        if "data" in data:
            return _extract_agent_response(data["data"])
        if "choices" in data:
            choices = data["choices"]
            if choices and isinstance(choices, list):
                msg = choices[0].get("message", {})
                return msg.get("content")
    return data


# ---------------------------------------------------------------------------
# generic HTTP API adapter
# ---------------------------------------------------------------------------


def _call_api(
    target_config: Dict[str, Any],
    input_prompt: str,
    input_variables: Dict[str, Any],
) -> Dict[str, Any]:
    """调用通用 HTTP API。"""
    url = (target_config.get("url") or "").strip()
    if not url:
        return {"raw_response": None, "parsed_response": None, "error": "api 配置缺少 url"}

    method = (target_config.get("method") or "POST").upper()
    timeout = target_config.get("timeout", 60)
    headers = _build_headers(target_config)

    # 构建请求体
    body_template = target_config.get("body") or {}
    body = _render_dict_templates(body_template, {"input": input_prompt, **input_variables})

    # 如果有 response_jsonpath，记下来
    response_jsonpath = target_config.get("response_jsonpath")

    try:
        with httpx.Client(timeout=timeout) as client:
            if method == "GET":
                resp = client.get(url, headers=headers, params=body)
            else:
                resp = client.post(url, headers=headers, json=body)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as e:
        return {
            "raw_response": e.response.text,
            "parsed_response": None,
            "error": f"HTTP {e.response.status_code}: {e.response.text[:500]}",
        }
    except Exception as e:  # noqa: BLE001
        return {"raw_response": None, "parsed_response": None, "error": str(e)}

    raw = json.dumps(data, ensure_ascii=False)

    # 使用 JSONPath 提取
    if response_jsonpath:
        parsed = _extract_json_path(data, response_jsonpath)
    else:
        parsed = data

    return {"raw_response": raw, "parsed_response": parsed, "error": None}


# ---------------------------------------------------------------------------
# xlsx_qa adapter
# ---------------------------------------------------------------------------


def _call_xlsx_qa(
    target_config: Dict[str, Any],
    input_prompt: str,
    input_variables: Dict[str, Any],
) -> Dict[str, Any]:
    """调用 XLSX Q&A API。"""
    base_url = (target_config.get("base_url") or "").rstrip("/")
    module_id = target_config.get("module_id")
    timeout = target_config.get("timeout", 120)

    if not base_url or not module_id:
        return {
            "raw_response": None,
            "parsed_response": None,
            "error": "xlsx_qa 配置缺少 base_url 或 module_id",
        }

    # 先创建会话
    conv_url = f"{base_url}/api/v1/xlsx-qa/modules/{module_id}/conversations"
    ask_url_tpl = f"{base_url}/api/v1/xlsx-qa/conversations/{{conv_id}}/ask"

    headers = _build_headers(target_config)

    try:
        with httpx.Client(timeout=timeout) as client:
            # 创建会话
            conv_resp = client.post(conv_url, json={"title": "eval"}, headers=headers)
            conv_resp.raise_for_status()
            conv_data = conv_resp.json()
            conv_id = conv_data.get("id")

            if not conv_id:
                return {
                    "raw_response": json.dumps(conv_data, ensure_ascii=False),
                    "parsed_response": None,
                    "error": "创建会话失败：未返回 id",
                }

            # 提问
            ask_url = ask_url_tpl.format(conv_id=conv_id)
            ask_resp = client.post(
                ask_url,
                json={"question": input_prompt, "stream": False},
                headers=headers,
            )
            ask_resp.raise_for_status()
            data = ask_resp.json()
    except httpx.HTTPStatusError as e:
        return {
            "raw_response": e.response.text,
            "parsed_response": None,
            "error": f"HTTP {e.response.status_code}: {e.response.text[:500]}",
        }
    except Exception as e:  # noqa: BLE001
        return {"raw_response": None, "parsed_response": None, "error": str(e)}

    raw = json.dumps(data, ensure_ascii=False)
    # 提取摘要
    parsed = data.get("summary_markdown") or data.get("content") or data

    return {"raw_response": raw, "parsed_response": parsed, "error": None}


# ---------------------------------------------------------------------------
# lab adapter
# ---------------------------------------------------------------------------


async def _call_lab(
    target_config: Dict[str, Any],
    input_prompt: str,
    input_variables: Dict[str, Any],
) -> Dict[str, Any]:
    """调用实验室 NL-to-SQL 流水线，提取生成的 SQL。"""
    from ...core.database import SessionLocal
    from ...schemas.autobi_gateway import LabGatewayV2Request
    from ...services.autobi.lab_gateway_collect import run_lab_gateway_v2_collect

    api_access_id = (target_config.get("api_access_id") or "").strip()
    if not api_access_id:
        return {
            "raw_response": None,
            "parsed_response": None,
            "error": "lab 配置缺少 api_access_id",
        }

    db = SessionLocal()
    try:
        body = LabGatewayV2Request(content=input_prompt, id=api_access_id)
        lab_result = await run_lab_gateway_v2_collect(db, body)
    finally:
        db.close()

    if lab_result.get("error"):
        return {
            "raw_response": lab_result.get("summary", ""),
            "parsed_response": None,
            "error": lab_result["error"],
        }

    trace_id = lab_result.get("trace_id")
    summary = lab_result.get("summary", "")

    # 从 MySQL trace 中提取 step 14 (nl2sql) 生成的 SQL
    generated_sql = _extract_sql_from_trace(trace_id)

    parsed = {
        "generated_sql": generated_sql,
        "summary": summary,
        "trace_id": trace_id,
    }

    return {
        "raw_response": summary,
        "parsed_response": parsed,
        "error": None,
    }


def _call_lab_sync(
    target_config: Dict[str, Any],
    input_prompt: str,
    input_variables: Dict[str, Any],
) -> Dict[str, Any]:
    """在线程内运行 lab pipeline，避免评测直接占用 FastAPI 主事件循环。"""
    async def execute():
        from ...core.http_clients import close_http_clients
        from ...core.trace_writer import flush_traces
        try:
            return await _call_lab(target_config, input_prompt, input_variables)
        finally:
            await flush_traces()
            await close_http_clients()
    return asyncio.run(execute())


def _extract_sql_from_trace(trace_id: Optional[str]) -> Optional[str]:
    """从 trace 中提取最终执行的 SQL。

    优先取 step 15（SQL 权限改写）改写后的 SQL；
    若改写未启用/跳过则回退到 step 14（nl2sql）生成的原始 SQL。
    """
    if not trace_id:
        return None
    from ...core.redis_client import trace_get

    trace = trace_get(trace_id)
    if not trace:
        return None

    sql_step14 = None
    for step in trace.get("steps", []):
        sid = step.get("step_id")
        resp = step.get("response")
        if not resp:
            continue
        if sid == 14:
            sql_step14 = resp.get("sql")
        elif sid == 15:
            # step 15 执行过且未跳过 -> 使用改写后的 SQL
            if not resp.get("skipped") and resp.get("rewritten_sql"):
                return resp["rewritten_sql"]
    # 回退到 step 14 的原始 SQL
    return sql_step14


# ---------------------------------------------------------------------------
# utilities
# ---------------------------------------------------------------------------

_TEMPLATE_RE = re.compile(r"\{\{(\w+)\}\}")


def _render_template(template: str, variables: Dict[str, Any]) -> str:
    """将 {{key}} 替换为变量值。"""
    if not template or not variables:
        return template

    def _replace(m: re.Match) -> str:
        key = m.group(1)
        val = variables.get(key)
        if val is None:
            return m.group(0)  # 保留原样
        return str(val)

    return _TEMPLATE_RE.sub(_replace, template)


def _render_dict_templates(
    data: Any, variables: Dict[str, Any],
) -> Any:
    """递归渲染字典中的模板字符串。"""
    if isinstance(data, str):
        return _render_template(data, variables)
    if isinstance(data, dict):
        return {k: _render_dict_templates(v, variables) for k, v in data.items()}
    if isinstance(data, list):
        return [_render_dict_templates(item, variables) for item in data]
    return data


def _extract_json_path(data: Any, path: str) -> Any:
    """
    简单 JSONPath 提取，支持 $.key.subkey 格式。
    例如: "$.data.content" → data["data"]["content"]
    """
    if not path:
        return data

    path = path.strip()
    if path.startswith("$."):
        path = path[2:]
    elif path.startswith("$"):
        path = path[1:]

    parts = path.split(".")
    current = data

    for part in parts:
        if not part:
            continue
        if current is None:
            return None

        # 处理数组索引 key[0]
        idx_match = re.match(r"^(\w+)\[(\d+)\]$", part)
        if idx_match:
            key, idx = idx_match.group(1), int(idx_match.group(2))
            if isinstance(current, dict):
                current = current.get(key)
            else:
                return None
            if isinstance(current, list) and idx < len(current):
                current = current[idx]
            else:
                return None
        elif isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list):
            # 尝试作为数字索引
            try:
                idx = int(part)
                current = current[idx] if idx < len(current) else None
            except (ValueError, IndexError):
                return None
        else:
            return None

    return current


def _build_headers(target_config: Dict[str, Any]) -> Dict[str, str]:
    """构建请求头。"""
    headers = {"Content-Type": "application/json"}
    auth_token = target_config.get("auth_token")
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"
    extra_headers = target_config.get("headers")
    if extra_headers and isinstance(extra_headers, dict):
        headers.update(extra_headers)
    return headers
