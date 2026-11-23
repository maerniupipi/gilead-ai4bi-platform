import re

from ..workflow_run_ctx import WorkflowRunContext, substitute_llm_prompt, resolve_dotted
from ....schemas.chat import ChatRequest
from ....services.chat.service import ChatService
from ._values import as_text
from ....core.model_observation import model_scope


def _build_bindings_from_input_params(ctx: WorkflowRunContext, input_params: list) -> dict:
    """根据 input_params 配置构建_param_bindings。"""
    bindings = {}
    if not input_params:
        return bindings
    for p in input_params:
        if not isinstance(p, dict):
            continue
        variable = (p.get("variable") or "").strip()
        if not variable:
            continue
        if variable in bindings:
            raise ValueError(f"LLM 输入参数名称重复: {variable}")
        source_mode = (p.get("source_mode") or "ref").strip().lower()
        if source_mode == "const":
            raw = p.get("default")
            bindings[variable] = {"source_mode": "const", "const_value": raw if raw is not None else ""}
        else:
            ref = (p.get("ref") or "").strip()
            bindings[variable] = {"source_mode": "ref", "ref": ref}
    return bindings


def _get_input_text_from_bindings(ctx: WorkflowRunContext, bindings: dict) -> str:
    """从 bindings 中获取第一个输入参数的值作为用户输入文本。"""
    for name, spec in bindings.items():
        if not isinstance(spec, dict):
            continue
        if spec.get("source_mode") == "const":
            return as_text(spec.get("const_value", ""))
        ref = (spec.get("ref") or "").strip()
        if ref:
            return as_text(resolve_dotted(ctx, ref))
    return ""


def _has_placeholder(template: str) -> bool:
    """检查模板是否包含 {{xxx}} 占位符。"""
    return bool(re.search(r"\{\{\s*[^}]+?\s*\}\}|\$\{\s*[A-Za-z_][A-Za-z0-9_]*\s*\}", template or ""))


def build_llm_request(ctx: WorkflowRunContext, cfg: dict) -> ChatRequest:
    provider_id = cfg.get("provider_id")
    model_name = (cfg.get("model_name") or "").strip()
    if provider_id is None or not model_name:
        raise ValueError("LLM 节点未配置 provider_id 或 model_name")

    input_params = cfg.get("input_params") if isinstance(cfg.get("input_params"), list) else []
    custom_bindings = _build_bindings_from_input_params(ctx, input_params)

    existing_bindings = cfg.get("param_bindings") if isinstance(cfg.get("param_bindings"), dict) else {}
    # Named slots may have an empty editor row; it must not erase an actual input binding.
    bindings = dict(custom_bindings)
    for name, spec in existing_bindings.items():
        if name not in bindings or (isinstance(spec, dict) and (
            spec.get("source_mode") == "const" or (spec.get("ref") or "").strip()
        )):
            bindings[name] = spec

    system_prompt = substitute_llm_prompt(ctx, cfg.get("system_prompt") or "", bindings)

    use_user_tmpl = bool(cfg.get("use_user_prompt_template"))
    user_prompt_tmpl = (cfg.get("user_prompt") or "").strip()

    if use_user_tmpl:
        if user_prompt_tmpl and _has_placeholder(user_prompt_tmpl):
            user_message = substitute_llm_prompt(ctx, user_prompt_tmpl, bindings).strip()
            if not user_message:
                user_message = "."
        elif user_prompt_tmpl:
            input_text = _get_input_text_from_bindings(ctx, bindings)
            if input_text:
                user_message = f"{user_prompt_tmpl}\n\n{input_text}"
            else:
                user_message = user_prompt_tmpl
        else:
            input_text = _get_input_text_from_bindings(ctx, bindings)
            user_message = input_text or "."
        system_for_api = system_prompt.strip() if system_prompt.strip() else None
    else:
        input_text = _get_input_text_from_bindings(ctx, bindings)
        if input_text:
            user_message = input_text
        else:
            user_message = system_prompt.strip() if system_prompt.strip() else "."
        system_for_api = system_prompt.strip() if system_prompt.strip() else None

    return ChatRequest(
        provider_id=int(provider_id),
        model=model_name,
        message=user_message,
        system=system_for_api,
        temperature=cfg.get("temperature", 0.7),
        max_tokens=cfg.get("max_tokens", 2000),
        top_p=cfg.get("top_p", 0.9),
        stop_words=cfg.get("stop_words") or None,
    )


def _strip_code_fence(text: str) -> str:
    """剥离 LLM 输出外围的 markdown 代码围栏（```json ... ```），避免下游 json.loads 失败。"""
    s = (text or "").strip()
    if not s.startswith("`"):
        return text or ""
    m = re.match(r"^`{3,}[a-zA-Z0-9_-]*\s*\n?(.*?)\n?`{3,}\s*$", s, re.DOTALL)
    return m.group(1).strip() if m else s

async def execute(ctx: WorkflowRunContext, node: dict) -> dict:
    cfg = (node.get("data") or {}).get("llm_config") or {}
    req = build_llm_request(ctx, cfg)
    # Saved canvases may still contain retry_count/retry_interval. They no longer
    # affect execution: one node invocation always means one provider request.
    with model_scope(trace_id=ctx.trace_id or ctx.run_id, app_id=ctx.agent_app_id,
                     version_id=ctx.version_id, node_id=node.get('id'),
                     node_label=(node.get('data') or {}).get('label')):
        resp = await ChatService.send_chat(ctx.db, req)
    return {"text": _strip_code_fence(resp.content or "")}
