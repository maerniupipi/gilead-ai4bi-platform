"""AI 创建助手：OpenAI tools 定义（按 Phase 开放）。"""

from typing import Any, Dict, List

_TOOLS_ALL: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "list_agent_apps",
            "description": "列出当前用户已创建的智能体应用，用于推荐子智能体复用或避免重复建设。",
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": "按名称或描述模糊过滤，可为空表示全部",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "最多返回条数，默认 20",
                        "default": 20,
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_lab_projects",
            "description": "列出 AutoBI 实验室项目，用于实验室节点绑定 project_id。",
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": "按名称过滤，可为空",
                    },
                    "limit": {"type": "integer", "default": 20},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_data_tables",
            "description": "查询知识库中已配置的表及字段，用于脚本/LLM 提示词中的字段命名。",
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": "按表名或字段名模糊过滤，可为空",
                    },
                    "limit": {"type": "integer", "default": 10},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_model_providers",
            "description": "列出系统已配置的模型供应商及可用模型名称，用于 LLM 节点配置。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]

_BY_NAME = {t["function"]["name"]: t for t in _TOOLS_ALL}


def get_tools_for_phase(phase: str) -> List[Dict[str, Any]]:
    """与设计文档 §9.4 矩阵一致。"""
    p = (phase or "").upper()
    if p in ("WELCOME", "EXPLORE", "CONFIRM"):
        return []
    if p == "CLARIFY":
        return [
            _BY_NAME["list_agent_apps"],
            _BY_NAME["list_lab_projects"],
            _BY_NAME["get_data_tables"],
        ]
    if p == "DESIGN":
        return list(_TOOLS_ALL)
    if p == "PARAMS":
        return [_BY_NAME["list_lab_projects"], _BY_NAME["get_model_providers"]]
    return []
