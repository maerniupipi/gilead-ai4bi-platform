import json
import math
import re
from typing import Any, Optional

import httpx

from ..workflow_run_ctx import WorkflowRunContext, resolve_dotted, substitute_template
from ._values import as_text


_PATH_PART = re.compile(r"(?:^|\.)([^.\[\]]+)|\[(\d+)\]")
_PLACEHOLDER = re.compile(r"\{\{\s*([^}]+?)\s*\}\}")


def _json_path_get(obj: Any, path: str) -> Any:
    p = (path or "").strip()
    if not p or p == "$":
        return obj
    if p.startswith("$"):
        p = p[1:]
    p = p.removeprefix(".")
    cur = obj
    end = 0
    parts = []
    for match in _PATH_PART.finditer(p):
        if match.start() != end:
            raise ValueError(f"不支持的 JSON Path: {path}")
        parts.append(match.group(1) if match.group(1) is not None else int(match.group(2)))
        end = match.end()
    if end != len(p) or not parts:
        raise ValueError(f"不支持的 JSON Path: {path}")
    for part in parts:
        if isinstance(cur, dict):
            cur = cur.get(str(part))
        elif isinstance(cur, list) and str(part).isdigit():
            index = int(part)
            cur = cur[index] if index < len(cur) else None
        else:
            return None
    return cur


def _render_json_value(ctx: WorkflowRunContext, value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _render_json_value(ctx, item) for key, item in value.items()}
    if isinstance(value, list):
        return [_render_json_value(ctx, item) for item in value]
    if isinstance(value, str):
        full = _PLACEHOLDER.fullmatch(value.strip())
        if full:
            return resolve_dotted(ctx, full.group(1))
        return _PLACEHOLDER.sub(lambda match: as_text(resolve_dotted(ctx, match.group(1))), value)
    return value


def build_api_request(ctx: WorkflowRunContext, cfg: dict) -> dict:
    method = (cfg.get("method") or "GET").strip().upper()
    if method not in ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"):
        raise ValueError(f"不支持的 HTTP 方法: {method}")
    base = substitute_template(ctx, (cfg.get("base_url") or "").strip())
    path = substitute_template(ctx, (cfg.get("path") or "").strip())
    url = base.rstrip("/") + "/" + path.lstrip("/") if path else base.rstrip("/")
    parsed_url = httpx.URL(url)
    if parsed_url.scheme not in ("http", "https") or not parsed_url.host:
        raise ValueError("外部 API 需配置有效的 http/https Base URL")

    headers: dict[str, str] = {}
    for h in cfg.get("headers") or []:
        key = (h.get("key") or "").strip()
        if key:
            headers[key] = substitute_template(ctx, as_text(h.get("value")))
    params: dict[str, str] = {}
    for q in cfg.get("query") or []:
        key = (q.get("key") or "").strip()
        if key:
            params[key] = substitute_template(ctx, as_text(q.get("value")))

    body_raw = cfg.get("body_template")
    content: Optional[bytes] = None
    json_body: Any = None
    has_json_body = False
    if body_raw is not None and body_raw != "" and method in ("POST", "PUT", "PATCH", "DELETE"):
        try:
            template = json.loads(body_raw) if isinstance(body_raw, str) else body_raw
        except json.JSONDecodeError:
            full = _PLACEHOLDER.fullmatch(body_raw.strip())
            if full:
                json_body = resolve_dotted(ctx, full.group(1))
                # Older script nodes export a serialized JSON request body.
                # Only a whole-body reference is decoded; string field values stay strings.
                if isinstance(json_body, str):
                    try:
                        json_body = json.loads(json_body)
                    except json.JSONDecodeError:
                        pass
                has_json_body = True
            else:
                rendered = substitute_template(ctx, body_raw)
                try:
                    json_body = json.loads(rendered)
                    has_json_body = True
                except json.JSONDecodeError as exc:
                    if body_raw.lstrip().startswith(("{", "[")):
                        raise ValueError("外部 API 请求体不是有效 JSON，请检查模板与引号") from exc
                    content = rendered.encode("utf-8")
        else:
            json_body = _render_json_value(ctx, template)
            has_json_body = True

    return {"method": method, "url": url, "headers": headers, "query": params,
            "body": json_body if has_json_body else content.decode("utf-8") if content is not None else None,
            "body_kind": "json" if has_json_body else "text" if content is not None else "none"}


async def execute(ctx: WorkflowRunContext, node: dict) -> dict:
    cfg = (node.get("data") or {}).get("api_config") or {}
    request = build_api_request(ctx, cfg)
    method, url = request["method"], request["url"]
    headers, params = request["headers"], request["query"]
    has_json_body = request["body_kind"] == "json"
    json_body = request["body"] if has_json_body else None
    content = request["body"].encode("utf-8") if request["body_kind"] == "text" else None
    default_timeout = 60
    try:
        seconds = float(cfg.get("timeout") if cfg.get("timeout") is not None else default_timeout)
    except (TypeError, ValueError) as exc:
        raise ValueError("外部 API 超时必须为 1–600 秒") from exc
    if not math.isfinite(seconds) or not 1 <= seconds <= 600:
        raise ValueError("外部 API 超时必须为 1–600 秒")
    timeout = httpx.Timeout(seconds, connect=min(5.0, seconds))
    async with httpx.AsyncClient(timeout=timeout) as client:
        if has_json_body:
            # httpx's json=None means no body, so encode null explicitly as well.
            if json_body is None:
                hdr = httpx.Headers(headers)
                hdr.setdefault("Content-Type", "application/json")
                resp = await client.request(method, url, headers=hdr, params=params, content=b"null")
            else:
                resp = await client.request(method, url, headers=headers, params=params, json=json_body)
        elif content is not None:
            hdr = httpx.Headers(headers)
            hdr.setdefault("Content-Type", "text/plain; charset=utf-8")
            resp = await client.request(method, url, headers=hdr, params=params, content=content)
        else:
            resp = await client.request(method, url, headers=headers, params=params)


    # Keep HTTP failure statuses inspectable so selector nodes can route on them.
    out: dict = {"status_code": resp.status_code, "response_body": resp.text}
    try:
        parsed = resp.json()
    except ValueError:
        parsed = None
    for ov in cfg.get("output_vars") or []:
        name = (ov.get("name") or "").strip()
        jp = (ov.get("json_path") or "").strip()
        if name and jp:
            if name in out:
                raise ValueError(f"外部 API 返回变量名称重复或保留: {name}")
            out[name] = _json_path_get(parsed, jp)
    return out
