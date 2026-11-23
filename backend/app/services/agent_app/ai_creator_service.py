"""AI 智能体创建助手：对话 + 工具循环 + JSON 回复解析（增强版）。

借鉴 nanobot 的设计：
- 结构化错误恢复：JSON 解析失败时尝试修复 + 重试
- 上下文治理：token 估算 + 消息裁剪，避免超出窗口
- 内存 consolidation：collected_info 作为跨轮次结构化的需求摘要
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from ...schemas.agent_app import (
    AiChatRequest,
    AiChatResponse,
    ParamSchemaItem,
    ReplyOption,
    ToolCallLog,
)
from ...services.chat.service import ChatService
from . import ai_creator_prompts as prompts
from .tool_definitions import get_tools_for_phase
from .tool_executor import AiCreatorToolExecutor

logger = logging.getLogger(__name__)

# ============================================================
# JSON 解析（鲁棒增强版）
# ============================================================

# 匹配 ```json ... ``` 或 ``` ... ``` 代码围栏
JSON_BLOCK = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.IGNORECASE)
# 匹配文本中最外层的 { ... } JSON 对象
JSON_OBJECT = re.compile(r"\{[\s\S]*\}")


def _strip_json_fence(text: str) -> str:
    """移除 markdown 代码围栏标记。"""
    t = (text or "").strip()
    m = JSON_BLOCK.search(t)
    if m:
        return m.group(1).strip()
    # 如果没有围栏，尝试提取文本中的 JSON 对象
    m2 = JSON_OBJECT.search(t)
    if m2 and m2.group() != t:
        return m2.group().strip()
    return t


def _fix_json_common_issues(text: str) -> str:
    """修复 LLM 输出中常见的 JSON 格式问题。

    类似 nanobot 的结构化错误恢复思路：不直接 fail，
    而是尝试修复已知的常见问题。
    """
    t = text.strip()

    # 1. 移除 BOM 和不可见控制字符（保留换行和常见空白）
    t = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", t)

    # 2. 移除尾部逗号（最常见的问题）
    #    "key": "value",\n  }  ->  "key": "value"\n  }
    t = re.sub(r",(\s*[}\]])", r"\1", t)

    # 3. 修复单引号 JSON（Python 风格 -> JS 风格）
    #    只在明显是键值对上下文中的单引号才替换
    #    简单策略：如果字符串包含大量单引号且少量双引号，全部替换
    if t.count("'") > t.count('"') * 2:
        # 保守策略：只替换键和字符串值的引号
        # 'key': -> "key":
        t = re.sub(r"'([^']*)'(\s*):", r'"\1"\2:', t)
        # : 'value' -> : "value"
        t = re.sub(r":\s*'([^']*)'", r': "\1"', t)

    # 4. 截断到最后一个完整的顶层 }
    #    找到最后一个 }，检查前面的结构是否完整
    last_brace = t.rfind("}")
    if last_brace > 0:
        # 检查截断后的大括号是否平衡
        truncated = t[: last_brace + 1]
        if truncated.count("{") == truncated.count("}"):
            t = truncated

    return t


def _parse_reply_json(text: str) -> Dict[str, Any]:
    """解析 LLM 回复中的 JSON，先尝试直接解析，失败后修复再试。"""
    clean = _strip_json_fence(text)

    # 尝试 1：直接解析
    try:
        return json.loads(clean)
    except (json.JSONDecodeError, TypeError):
        pass

    # 尝试 2：修复常见问题后解析
    fixed = _fix_json_common_issues(clean)
    if fixed != clean:
        try:
            result = json.loads(fixed)
            logger.info("ai_creator: JSON repaired successfully after fixing common issues")
            return result
        except (json.JSONDecodeError, TypeError):
            pass

    # 尝试 3：最后尝试用原始 clean 文本再解析一次
    # （让异常自然传播，调用方处理）
    return json.loads(clean)


# ============================================================
# Token 估算与消息管理（借鉴 nanobot 的 context governance）
# ============================================================

def _estimate_tokens(text: str) -> int:
    """粗略估算文本的 token 数（4 字符 ≈ 1 token）。"""
    return max(1, len(text) // 4)


def _estimate_messages_tokens(messages: List[Dict[str, Any]]) -> int:
    """估算消息列表的总 token 数。"""
    total = 0
    for m in messages:
        content = str(m.get("content") or "")
        total += _estimate_tokens(content)
        # 工具调用额外开销
        for tc in m.get("tool_calls") or []:
            tc_str = json.dumps(tc, ensure_ascii=False, default=str)
            total += _estimate_tokens(tc_str)
    return total


def _build_messages_with_budget(
    req: AiChatRequest,
    max_input_tokens: int = 16000,
    keep_recent: int = 12,
) -> List[Dict[str, Any]]:
    """构建消息列表，在接近 token 预算时裁剪旧消息。

    类似 nanobot 的 snip_history：保留最近的 N 条消息，
    确保不超过模型的上下文窗口。
    """
    system = prompts.build_system(
        req.phase,
        req.collected_info,
        req.workflow_design,
        req.filled_params,
    )
    out: List[Dict[str, Any]] = [{"role": "system", "content": system}]
    system_tokens = _estimate_tokens(system)

    # 从最新到最旧添加消息，直到接近 token 预算
    available_tokens = max_input_tokens - system_tokens - 1000  # 预留 1000 给回复
    history = list(req.messages)
    history.reverse()  # 从最新开始

    recent: List[Dict[str, Any]] = []
    used_tokens = 0
    for m in history:
        role = m.role if m.role in ("user", "assistant") else "user"
        content = m.content or ""
        msg_tokens = _estimate_tokens(content)
        if used_tokens + msg_tokens > available_tokens:
            break
        recent.append({"role": role, "content": content})
        used_tokens += msg_tokens

    recent.reverse()  # 恢复时间顺序
    out.extend(recent)

    # 如果截断了消息，保证至少保留 keep_recent 条
    if len(recent) < keep_recent and len(history) >= keep_recent:
        recent_only = [
            {"role": m.role if m.role in ("user", "assistant") else "user", "content": m.content or ""}
            for m in list(req.messages)[-keep_recent:]
        ]
        out = [{"role": "system", "content": system}] + recent_only

    return out


# ============================================================
# 工具调用辅助
# ============================================================

def _tool_summary_and_preview(tool_name: str, result: Dict[str, Any]) -> tuple[str, List[Dict[str, Any]]]:
    """生成工具调用的摘要和预览数据。"""
    if result.get("status") == "failed" or result.get("error"):
        return ("查询失败", [])
    if tool_name == "list_agent_apps":
        apps = result.get("apps") or []
        prev = [{"id": a.get("id"), "name": a.get("name")} for a in apps[:8]]
        return (f"找到 {len(apps)} 个智能体应用", prev)
    if tool_name == "list_lab_projects":
        prj = result.get("projects") or []
        prev = [{"id": p.get("id"), "name": p.get("name")} for p in prj[:8]]
        return (f"找到 {len(prj)} 个实验室项目", prev)
    if tool_name == "get_data_tables":
        tabs = result.get("tables") or []
        prev = [
            {"table_name": t.get("table_name"), "knowledge_base_name": t.get("knowledge_base_name")}
            for t in tabs[:8]
        ]
        return (f"找到 {len(tabs)} 张相关表", prev)
    if tool_name == "get_model_providers":
        provs = result.get("providers") or []
        n = sum(len(p.get("models") or []) for p in provs)
        prev = [{"provider_id": p.get("provider_id"), "provider_name": p.get("provider_name")} for p in provs[:6]]
        return (f"共 {len(provs)} 个供应商、约 {n} 个模型", prev)
    return ("完成", [])


def _normalize_assistant_message(msg: Dict[str, Any]) -> Dict[str, Any]:
    """确保可 JSON 序列化写回 messages。"""
    clean: Dict[str, Any] = {"role": "assistant", "content": msg.get("content") or ""}
    if msg.get("tool_calls"):
        clean["tool_calls"] = msg["tool_calls"]
    return clean


# ============================================================
# Workflow Design 规范化
# ============================================================

def _safe_json(obj: Any, max_len: int = 1600) -> str:
    try:
        text = json.dumps(obj, ensure_ascii=False, default=str, indent=2)
    except TypeError:
        text = str(obj)
    if len(text) > max_len:
        return text[:max_len] + "\n...(截断)"
    return text


def _find_node(nodes: List[Dict[str, Any]], kind: str) -> Dict[str, Any] | None:
    for node in nodes:
        if isinstance(node, dict) and node.get("kind") == kind:
            return node
    return None


def _unique_semantic_id(nodes: List[Dict[str, Any]], base: str) -> str:
    used = {str(n.get("semantic_id") or n.get("id") or "") for n in nodes if isinstance(n, dict)}
    if base not in used:
        return base
    i = 2
    while f"{base}_{i}" in used:
        i += 1
    return f"{base}_{i}"


def _build_llm_system_prompt(wd: Dict[str, Any], node: Dict[str, Any]) -> str:
    """从 Agent Spec 构建 LLM 节点的完整 system_prompt。

    使用 workflow_design 中的 agent_profile、operating_model、quality_plan
    来生成结构化的节点 system_prompt。
    """
    profile = wd.get("agent_profile") or {}
    operating = wd.get("operating_model") or {}
    quality = wd.get("quality_plan") or {}
    app_name = wd.get("app_name") or "智能体"
    node_label = node.get("label") or "任务执行"
    node_desc = node.get("description") or ""

    parts = []

    # 1. 角色
    role = profile.get("role") or f"{app_name} 执行节点"
    parts.append(f"# 角色\n你是「{app_name}」工作流中的「{node_label}」节点。{role}。")

    # 2. 输入
    parts.append(f"\n# 输入\n- 用户原始输入（通过 {{query}} 变量传入）\n- 上游节点的分析结果（如有）")

    # 3. 任务
    mission = profile.get("mission") or wd.get("description") or "根据用户输入和上游分析结果完成任务。"
    parts.append(f"\n# 任务\n{mission}")
    if node_desc:
        parts.append(f"\n本节点具体职责：{node_desc}")

    # 4. 流程
    plan_policy = operating.get("plan_policy") or "简单任务直接执行；复杂任务先拆解步骤再逐步完成。"
    parts.append(f"\n# 执行流程\n{plan_policy}")
    parts.append("步骤：\n1. 明确当前任务的目标和约束\n2. 检查所需信息是否齐全，不全则说明缺口\n3. 按计划执行\n4. 输出前自检")

    # 5. 约束
    non_goals = profile.get("non_goals") or []
    parts.append(f"\n# 约束与边界")
    parts.append(f"- 权限边界：{operating.get('permission_boundary') or '不越权读取数据，不编造未执行的操作'}")
    if non_goals:
        parts.append(f"- 明确不做的：{'；'.join(non_goals)}")
    parts.append(f"- 上下文策略：{operating.get('context_strategy') or '仅使用当前输入和上游节点结果'}")
    parts.append(f"- 工具策略：{operating.get('tool_policy') or '仅在配置了工具时调用，失败时返回可理解的错误'}")
    parts.append(f"- 记忆策略：{operating.get('memory_policy') or '不记忆敏感信息'}")
    if profile.get("escalation_policy"):
        parts.append(f"- 转人工条件：{profile['escalation_policy']}")

    # 6. 输出格式
    output_contract = operating.get("output_contract") or "输出结论、依据和下一步建议，确保结构清晰。"
    parts.append(f"\n# 输出格式\n{output_contract}")

    # 7. 失败策略
    failure_policy = operating.get("failure_policy") or "信息不足时说明缺口，工具失败时提供降级建议。"
    parts.append(f"\n# 失败处理\n{failure_policy}")

    # 8. 质量标准
    if quality:
        ac = quality.get("acceptance_criteria") or []
        gc = quality.get("golden_cases") or []
        ec = quality.get("edge_cases") or []
        parts.append(f"\n# 质量标准")
        if ac:
            parts.append(f"验收标准：{'；'.join(ac)}")
        if gc:
            parts.append(f"典型用例：{'；'.join(gc)}")
        if ec:
            parts.append(f"边界情况：{'；'.join(ec)}")

    return "\n".join(parts)


def _normalize_workflow_design(workflow_design: Dict[str, Any]) -> Dict[str, Any]:
    """把模型输出的 workflow_design 补齐为完整的 Agent Spec + 画布设计。

    增强点：
    - 保留 LLM 已输出的 agent_profile / operating_model / quality_plan
    - 缺失时生成更丰富的默认值（结合 app_name 等元信息）
    - LLM 节点的 system_prompt 从 Agent Spec 自动派生
    """
    if not isinstance(workflow_design, dict):
        return workflow_design

    wd = dict(workflow_design)
    nodes = [dict(n) for n in (wd.get("nodes") or []) if isinstance(n, dict)]
    edges = [dict(e) for e in (wd.get("edges") or []) if isinstance(e, dict)]

    app_name = wd.get("app_name") or "业务智能体"
    description = wd.get("description") or "根据用户输入完成任务并输出结果"

    # ---- Agent Spec 补齐 ----
    if not wd.get("agent_profile"):
        wd["agent_profile"] = {
            "role": app_name,
            "mission": description,
            "target_users": "业务用户",
            "primary_scenarios": ["自然语言任务处理"],
            "non_goals": ["不处理未授权数据", "不编造外部系统或工具结果"],
            "escalation_policy": "输入不足、权限不足、工具失败或结论不确定时，明确说明缺口并请求补充信息。",
        }
    if not wd.get("operating_model"):
        wd["operating_model"] = {
            "plan_policy": "简单任务直接执行；复杂任务先拆解步骤并保留关键依据。",
            "context_strategy": "优先使用用户输入、上游节点结果和平台工具返回的信息；避免引入无关上下文。",
            "tool_policy": "仅在节点已配置工具、子智能体、实验室或 API 时调用；调用失败时返回可理解的失败原因。",
            "memory_policy": "不默认记忆敏感信息；长期偏好或业务规则由用户明确提供。",
            "permission_boundary": "不越权读取数据，不伪造已执行的外部操作。",
            "failure_policy": "缺少关键参数时要求补充；外部依赖失败时提供降级建议。",
            "output_contract": "输出结论、依据、下一步；涉及结构化结果时保持字段名稳定。",
        }
    if not wd.get("quality_plan"):
        wd["quality_plan"] = {
            "acceptance_criteria": ["正确理解用户目标", "输出结构稳定", "信息不足时不编造", "工具失败时有降级处理"],
            "golden_cases": ["用户给出完整需求时直接产出结果"],
            "edge_cases": ["用户输入含糊不清", "外部工具无返回结果", "用户请求超出智能体权限范围"],
            "observability": "保留每个节点的输入输出，便于调试和回放执行过程。",
        }

    # ---- 确保必需节点存在 ----
    start = _find_node(nodes, "start")
    if not start:
        start = {"semantic_id": _unique_semantic_id(nodes, "start"), "kind": "start", "label": "开始"}
        nodes.insert(0, start)

    user_input = _find_node(nodes, "userInput")
    if not user_input:
        user_input = {
            "semantic_id": _unique_semantic_id(nodes, "user_input"),
            "kind": "userInput",
            "label": "用户输入",
            "config": {
                "fields": [
                    {
                        "variable": "query",
                        "display": "用户需求",
                        "type": "string",
                        "required": True,
                        "description": "用户希望智能体完成的任务、问题或上下文。",
                    }
                ]
            },
        }
        nodes.insert(1, user_input)

    llm_nodes = [n for n in nodes if n.get("kind") == "llm"]
    if not llm_nodes:
        llm_nodes = [
            {
                "semantic_id": _unique_semantic_id(nodes, "core_agent"),
                "kind": "llm",
                "label": "任务执行",
                "description": f"{app_name}的核心执行节点：理解需求、规划步骤、执行任务、自检输出。",
                "config": {"llm_config": {}},
            }
        ]
        nodes.append(llm_nodes[0])

    output = _find_node(nodes, "output")
    if not output:
        last_llm_label = llm_nodes[-1].get("label") or "任务执行"
        output = {
            "semantic_id": _unique_semantic_id(nodes, "output"),
            "kind": "output",
            "label": "输出",
            "config": {"output_config": {"content_template": f"{{{{{last_llm_label}.text}}}}"}},
        }
        nodes.append(output)

    # ---- 补全节点配置 ----
    requires_params = set(wd.get("requires_params") or [])

    for node in nodes:
        if "semantic_id" not in node:
            node["semantic_id"] = _unique_semantic_id(nodes, str(node.get("kind") or "node"))
        node.setdefault("label", node.get("kind") or "节点")
        cfg = node.setdefault("config", {})
        if not isinstance(cfg, dict):
            cfg = {}
            node["config"] = cfg

        # 设置默认描述
        if not node.get("description"):
            kind = node.get("kind")
            if kind == "llm":
                label = node.get("label", "")
                if "需求分析" in label or "意图" in label:
                    node["description"] = "分析用户意图，澄清模糊点，判断参数完整性，评估任务风险等级。"
                elif "规划" in label or "拆解" in label:
                    node["description"] = "将用户需求拆解为可执行的步骤，确定需要调用的工具或子智能体。"
                elif "审校" in label or "校验" in label or "检查" in label:
                    node["description"] = "对执行结果进行事实核查、格式校验和缺口识别，确保输出质量。"
                elif "执行" in label:
                    node["description"] = "根据规划和上下文执行核心任务，调用配置的工具和子智能体。"
                else:
                    node["description"] = f"按 Agent Spec 执行任务，包含计划、执行、自检与失败处理。"

        # LLM 节点配置
        if node.get("kind") == "llm":
            lc = cfg.setdefault("llm_config", {})
            if isinstance(lc, dict):
                lc.setdefault("temperature", 0.4)
                lc.setdefault("max_tokens", 2000)
                lc.setdefault("top_p", 0.9)
                if lc.get("provider_id") in (None, ""):
                    lc["provider_id"] = "{{PARAM:llm.provider_id}}"
                    requires_params.add("llm.provider_id")
                if not (lc.get("model_name") or "").strip():
                    lc["model_name"] = "{{PARAM:llm.model_name}}"
                    requires_params.add("llm.model_name")
                lc.setdefault("use_user_prompt_template", True)
                # 智能默认的 param_bindings：绑定用户输入
                if not lc.get("param_bindings"):
                    input_label = user_input.get("label") or "用户输入"
                    lc["param_bindings"] = {
                        "query": {
                            "source_mode": "ref",
                            "ref": f"{input_label}.query",
                        }
                    }
                # system_prompt：优先保留 LLM 的输出，否则从 Agent Spec 派生
                if not (lc.get("system_prompt") or "").strip():
                    lc["system_prompt"] = _build_llm_system_prompt(wd, node)
                # user_prompt 模板
                if not (lc.get("user_prompt") or "").strip():
                    lc["user_prompt"] = "用户输入：{{query}}\n\n请按系统提示词执行任务。如果缺少关键信息，明确指出需要什么。"

        # userInput 节点字段
        if node.get("kind") == "userInput":
            cfg.setdefault("fields", cfg.get("fields") or node.get("fields") or [])

    # ---- 自动生成边（仅当 LLM 没有提供时） ----
    if not edges:
        ordered = [start, user_input] + llm_nodes + [output]
        edges = [
            {"source": ordered[i].get("semantic_id"), "target": ordered[i + 1].get("semantic_id")}
            for i in range(len(ordered) - 1)
        ]

    wd["nodes"] = nodes
    wd["edges"] = edges
    wd["requires_params"] = sorted(requires_params)

    profile = wd.get("agent_profile") or {}
    wd.setdefault(
        "implementation_notes",
        f"由 AI 创建助手基于深度需求分析生成。"
        f"共 {len(nodes)} 个节点，{len(edges)} 条边。"
        f"设计原则：{profile.get('role', '')} — {profile.get('mission', '')}",
    )
    if profile and not wd.get("description"):
        wd["description"] = profile.get("mission") or ""

    return wd


# ============================================================
# Fallback 选项（LLM 未返回选项时的降级方案）
# ============================================================

def _fallback_choice_options(phase: str) -> List[ReplyOption]:
    """LLM 未返回选项时的降级选项。"""
    p = (phase or "").upper()
    if p == "WELCOME":
        return [
            ReplyOption(
                id="data_analysis",
                label="数据分析与报表（推荐）",
                description="用自然语言查询业务数据，自动生成图表、趋势解读和异常预警。适合销售、运营、财务等需要高频看数的场景。",
            ),
            ReplyOption(
                id="knowledge_qa",
                label="知识检索与问答",
                description="基于规章制度、产品文档、FAQ 等知识库，精准回答业务问题并注明出处。适合制度查询、新人培训、经验查找。",
            ),
            ReplyOption(
                id="customer_service",
                label="智能客服",
                description="回答客户关于产品、订单、售后等常见问题，复杂问题自动转人工。适合客服、电商、SaaS 等场景。",
            ),
            ReplyOption(
                id="content_generation",
                label="内容生成与报告",
                description="根据需求自动撰写周报、方案、文案、PPT 等结构化文档。适合需要定期产出的岗位。",
            ),
            ReplyOption(
                id="workflow_automation",
                label="流程自动化",
                description="多步骤任务编排：收集信息→处理分析→审批确认→生成结果。适合有固定 SOP 的重复运营动作。",
            ),
            ReplyOption(id="other", label="以上都不准确", description="我描述自己的需求。", is_other=True),
        ]
    if p == "EXPLORE":
        return [
            ReplyOption(
                id="data_analysis",
                label="数据分析助手（推荐）",
                description="围绕数据查询、指标解释和报告生成设计——用户用自然语言提问，后台自动查库、分析、出图、写结论。",
            ),
            ReplyOption(
                id="knowledge_qa",
                label="知识问答助手",
                description="围绕制度、文档、FAQ 和经验知识检索设计——重点控制依据来源和引用溯源，确保回答可验证。",
            ),
            ReplyOption(
                id="workflow_automation",
                label="流程自动化助手",
                description="围绕收集信息、调用工具、分支判断和生成结果设计——适合需要多步骤处理的重复运营动作。",
            ),
            ReplyOption(
                id="multi_agent",
                label="多智能体编排",
                description="复用已有智能体或实验室能力，通过一个主智能体调度多个子智能体协同完成复杂任务。",
            ),
            ReplyOption(
                id="content_generation",
                label="内容生成助手",
                description="围绕报告撰写、文案生成、PPT 制作等内容创作场景设计——输入要求，输出结构化文档。",
            ),
            ReplyOption(id="other", label="以上都不准确", description="我想自己描述需求。", is_other=True),
        ]
    return [
        ReplyOption(
            id="low_friction",
            label="尽量少填（推荐）",
            description="把输入压缩成少数字段，由智能体自动理解意图、规划步骤和追问补充。适合大多数场景。",
        ),
        ReplyOption(
            id="structured_input",
            label="结构化填写",
            description="让用户按字段填写目标、约束、数据范围等，输出更稳定但操作稍重。适合需要精确控制的场景。",
        ),
        ReplyOption(
            id="human_review",
            label="关键节点人工确认",
            description="分析方案经用户确认后再执行，适合涉及金额、对外沟通、权限操作或敏感数据的任务。",
        ),
        ReplyOption(
            id="full_auto",
            label="全自动执行",
            description="智能体理解需求后直接执行全流程并返回结果，适合低风险、高频重复的任务。",
        ),
        ReplyOption(id="other", label="其他方式", description="我想补充不同的交互方式。", is_other=True),
    ]


def _normalize_choice_reply(
    phase: str,
    reply_type: str,
    content: str,
    opts: List[ReplyOption],
    has_workflow_design: bool,
) -> tuple[str, str, List[ReplyOption]]:
    """规范化选项回复：确保 EXPLORE/CLARIFY 阶段始终有选项。"""
    p = (phase or "").upper()
    if p not in ("WELCOME", "EXPLORE", "CLARIFY") or has_workflow_design:
        return reply_type, content, opts

    normalized = list(opts or [])
    if not normalized:
        normalized = _fallback_choice_options(p)
        reply_type = "options"
        if content:
            content = content.rstrip() + "\n\n我先给你几个最可能的方向，选一个最接近的即可继续。"
        else:
            content = "我先把需求拆成几个方向，选一个最接近的即可。"
    elif reply_type != "options":
        reply_type = "options"

    # 确保有 "其他" 选项
    has_other = any(o.is_other or o.id == "other" for o in normalized)
    if not has_other:
        normalized.append(
            ReplyOption(
                id="other",
                label="以上都不准确",
                description="我补充说明我的需求。",
                is_other=True,
            )
        )

    # 限制选项数量
    if len(normalized) > 6:
        other = next((o for o in normalized if o.is_other or o.id == "other"), None)
        normalized = normalized[:5]
        if other and all(o.id != other.id for o in normalized):
            normalized.append(other)

    return reply_type, content, normalized


# ============================================================
# 主循环
# ============================================================

async def run_ai_creator_chat(db: Session, req: AiChatRequest) -> AiChatResponse:
    """执行 AI 创建者对话：工具调用循环 + JSON 解析。

    增强点：
    - JSON 解析鲁棒性：尝试修复常见格式问题
    - 上下文治理：token 感知的消息裁剪
    - 工具缓存：跨轮次缓存（利用 req.tool_cache）
    """
    executor = AiCreatorToolExecutor(db)
    tools = get_tools_for_phase(req.phase)
    messages = _build_messages_with_budget(req)
    tool_calls_log: List[ToolCallLog] = []

    max_rounds = 8
    for round_idx in range(max_rounds):
        msg = await ChatService.chat_completion_openai(
            db,
            provider_id=req.creator_model.provider_id,
            model=req.creator_model.model_name,
            messages=messages,
            tools=tools if tools else None,
            temperature=0.4,
            max_tokens=8192,
        )

        # ---- 处理工具调用 ----
        tcalls = msg.get("tool_calls")
        if tcalls:
            messages.append(_normalize_assistant_message(msg))
            for tc in tcalls:
                tid = tc.get("id") or ""
                fn = (tc.get("function") or {}).get("name") or ""
                raw_args = (tc.get("function") or {}).get("arguments") or "{}"
                try:
                    args = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args)
                except json.JSONDecodeError:
                    args = {}

                # 检查工具缓存
                cache_key = f"{fn}:{json.dumps(args, sort_keys=True, ensure_ascii=False)}"
                tool_cache = getattr(req, "tool_cache", None) or {}
                if cache_key in tool_cache and isinstance(tool_cache[cache_key], dict):
                    result = tool_cache[cache_key]
                else:
                    result = executor.run(fn, args)
                    # 写入缓存
                    if isinstance(tool_cache, dict):
                        tool_cache[cache_key] = result

                ok = not result.get("error") and result.get("status") != "failed"
                summary, preview = _tool_summary_and_preview(fn, result)

                log = ToolCallLog(
                    tool=fn,
                    args=args,
                    status="success" if ok else "failed",
                    summary=summary,
                    result_preview=preview,
                )
                if not ok:
                    log.error = str(result.get("error") or "failed")
                tool_calls_log.append(log)

                # 截断工具结果（类似 nanobot 的 tool_result_budget）
                result_str = json.dumps(result, ensure_ascii=False, default=str)
                if len(result_str) > 8000:
                    result_str = result_str[:8000] + "\n...(结果已截断)"

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tid,
                        "content": result_str,
                    }
                )
            continue

        # ---- 解析模型回复 ----
        content = msg.get("content") or ""
        try:
            data = _parse_reply_json(content)
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning("ai_creator parse error (round %d): %s", round_idx + 1, str(e)[:200])

            # A malformed response is a failure, not another model request.
            return AiChatResponse(
                session_id=req.session_id,
                phase=req.phase,
                next_phase=None,
                thinking="",
                reply_type="text",
                content="模型未返回合法 JSON。",
                tool_calls=tool_calls_log,
                parse_error=str(e)[:500],
            )

        # ---- 解析成功，构建响应 ----
        opts = [
            ReplyOption(
                id=o.get("id", str(i)),
                label=o.get("label", ""),
                description=o.get("description"),
                is_other=bool(o.get("is_other")),
            )
            for i, o in enumerate(data.get("options") or [])
            if isinstance(o, dict)
        ]
        pschema = [
            ParamSchemaItem(
                key=p.get("key", ""),
                label=p.get("label", ""),
                description=p.get("description"),
                type=p.get("type") or "string",
                required=bool(p.get("required", True)),
                placeholder=p.get("placeholder"),
                default=p.get("default"),
            )
            for p in (data.get("params_schema") or [])
            if isinstance(p, dict) and p.get("key")
        ]

        wf = data.get("workflow_design")
        if wf is not None and not isinstance(wf, dict):
            wf = None
        elif isinstance(wf, dict):
            wf = _normalize_workflow_design(wf)

        reply_type = str(data.get("reply_type") or "text")
        content = str(data.get("content") or "")
        reply_type, content, opts = _normalize_choice_reply(
            str(data.get("phase") or req.phase),
            reply_type,
            content,
            opts,
            isinstance(wf, dict),
        )

        next_phase = data.get("next_phase")
        if (
            isinstance(wf, dict)
            and wf.get("requires_params")
            and reply_type == "workflow_preview"
        ):
            next_phase = "PARAMS"

        return AiChatResponse(
            session_id=req.session_id,
            phase=str(data.get("phase") or req.phase),
            next_phase=next_phase,
            thinking=str(data.get("thinking") or ""),
            reply_type=reply_type,
            content=content,
            options=opts,
            workflow_design=wf,
            params_schema=pschema,
            collected_info_update=data.get("collected_info_update") or {},
            tool_calls=tool_calls_log,
        )

    # 超过最大轮次
    return AiChatResponse(
        session_id=req.session_id,
        phase=req.phase,
        reply_type="text",
        content="工具调用轮次过多，已中止，请尝试简化需求后重试。",
        tool_calls=tool_calls_log,
    )
