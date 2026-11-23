"""
LLM 驱动的评测用例自动生成服务

基于用户提供的场景描述，调用 LLM 批量生成评测用例（input_prompt + 期望输出 + 难度 + 分类）。
参考 procurement_esqg_tool 的多智能体生成思路，简化为单阶段通用生成：

  场景描述 → LLM → [{input_prompt, expected_output, difficulty, category}, ...]

对比 procurement_esqg_tool 的改进：
  - 通用化：不绑定特定行业（医药/金融/客服等），通过场景描述灵活适配
  - 单阶段：一次 LLM 调用完成生成，无需多智能体编排
  - 参考答案：可选同步生成 ground truth，作为评测的期望输出
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..xlsx_qa.llm_client import resolve_llm, chat_json, parse_json_response
from ...models.eval import EvalCase, EvalCaseGroundTruth, EvalSuite

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt 模板
# ---------------------------------------------------------------------------

GENERATE_CASES_SYSTEM = """# Role
你是一个专业的 AI 评测专家，擅长根据不同业务场景设计高质量、多样化的评测用例。你具备深厚的业务理解能力，能够从真实用户视角出发，生成自然、有代表性、能有效检验 AI 系统能力的评测问题。

# Task
根据用户提供的场景描述和参数，生成指定数量的评测用例。每个用例包含：
- input_prompt：输入提示词（用户会向 AI 提出的问题或指令）
- expected_output：期望的正确答案（如果用户要求生成参考答案）
- difficulty：难度等级（easy / medium / hard）
- category：问题分类

# 用例质量要求

## 难度定义
- **easy（基础）**：简单的事实查询、单项条件筛选、直接问答
- **medium（中等）**：多条件组合查询、分组统计、趋势分析、排序
- **hard（困难）**：多步推理、复杂统计（增长率/占比/排名）、需要综合判断的开放问题

## 输入提示词（input_prompt）要求
1. 使用自然语言，模拟真实用户的口吻
2. 问题明确、语义完整，不能模糊不清
3. 包含必要的上下文信息，使问题可独立理解
4. 覆盖不同的表达方式（疑问句、祈使句、陈述句等）
5. 对于含变量的场景，使用 {{变量名}} 标记模板变量

## 期望输出（expected_output）要求
1. 必须准确回答 input_prompt 提出的问题
2. 如果是 SQL 类型，输出的 SQL 语句必须语法正确且逻辑合理
3. 如果是 JSON 类型，输出的 JSON 必须结构清晰
4. 如果是数值类型，输出精确的数值或计算结果
5. 如果是文本类型，输出完整、准确的文本回答

## 多样性要求
1. 覆盖场景描述的各个子方向和边界情况
2. 问题类型多样化：聚合查询、条件筛选、排序排名、趋势对比、明细查询等
3. 表达方式多样化：不同问法、不同句式
4. 难度分布遵循用户指定的比例

# 输出格式
严格按照以下 JSON 格式输出，不要包含任何其他内容：

{
  "cases": [
    {
      "input_prompt": "用户输入的问题或指令",
      "expected_output": "期望的正确答案",
      "difficulty": "easy|medium|hard",
      "category": "问题分类"
    }
  ]
}

# 注意事项
1. 必须严格输出 JSON，字段名与示例完全一致
2. 生成数量必须等于用户指定的数量
3. 难度分布应尽量遵循用户指定的比例
4. 如果用户提供了具体场景上下文（如数据库表结构、业务规则等），必须在生成用例时考虑
5. 问题必须在该场景范围内，不能偏离主题"""

GENERATE_CASES_USER = """请根据以下场景生成评测用例。

## 场景描述
{scenario_description}

## 生成参数
- 数量：{count} 个
- 输出类型：{output_type}
- 难度分布：{difficulty_distribution}
- 是否生成参考答案：{generate_ground_truth}

{few_shot_section}

请生成 {count} 个评测用例。"""

FEW_SHOT_EXAMPLE = """## 参考示例
以下是一个类似场景的评测用例示例，供参考格式和风格：

{examples}"""

# ---------------------------------------------------------------------------
# 服务函数
# ---------------------------------------------------------------------------


async def generate_cases_service(
    db: Session,
    suite_id: int,
    params: Dict[str, Any],
) -> Dict[str, Any]:
    """LLM 自动生成评测用例。

    流程：
      1. 校验评测集存在
      2. 构建 prompt
      3. 调用 LLM 生成
      4. 解析 JSON 结果
      5. 批量写入数据库（用例 + 参考答案）
    """
    suite = db.query(EvalSuite).filter(EvalSuite.id == suite_id).first()
    if not suite:
        raise HTTPException(status_code=404, detail="评测集不存在")

    count = int(params.get("count", 10))
    if count < 1 or count > 50:
        raise HTTPException(status_code=400, detail="生成数量应在 1-50 之间")

    output_type = params.get("output_type", "mixed") or "mixed"
    scenario_description = params.get("scenario_description") or ""
    generate_ground_truth = params.get("generate_ground_truth", True)
    comparison_method = params.get("comparison_method") or suite.default_comparison_method or "exact"

    # 难度分布
    difficulty_dist = params.get("difficulty_distribution") or {"easy": 3, "medium": 4, "hard": 3}
    dist_desc = ", ".join(f"{k}: {v}" for k, v in difficulty_dist.items())

    # 构建 few-shot 示例（如果场景描述为空则给出通用示例）
    few_shot = ""
    if not scenario_description.strip():
        few_shot = FEW_SHOT_EXAMPLE.format(
            examples=json.dumps([
                {
                    "input_prompt": "查询本月销售额最高的前5个产品",
                    "expected_output": "本月销售额排名前5的产品为：1. 产品A (¥125,000) 2. 产品B (¥98,000) ...",
                    "difficulty": "medium",
                    "category": "销售分析",
                },
                {
                    "input_prompt": "统计各部门的员工数量",
                    "expected_output": "SELECT department, COUNT(*) as count FROM employees GROUP BY department",
                    "difficulty": "easy",
                    "category": "数据查询",
                },
                {
                    "input_prompt": "分析去年Q4与今年Q4的营收增长情况，按地区分别列出增长率",
                    "expected_output": "各区域Q4同比增长率：华东 +15.2%，华南 +8.7%，华北 +12.1%，西部 +5.3%",
                    "difficulty": "hard",
                    "category": "财务分析",
                },
            ], ensure_ascii=False, indent=2)
        )

    user_prompt = GENERATE_CASES_USER.format(
        scenario_description=scenario_description or "通用问答场景",
        count=count,
        output_type=output_type,
        difficulty_distribution=dist_desc,
        generate_ground_truth="是" if generate_ground_truth else "否",
        few_shot_section=few_shot,
    )

    # 调用 LLM
    try:
        choice = resolve_llm(db, provider_id=None, model=None)
        result = await chat_json(
            choice,
            system=GENERATE_CASES_SYSTEM,
            user=user_prompt,
            temperature=0.7,
            max_tokens=4000,
            timeout=120.0,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("LLM 生成用例失败")
        raise HTTPException(status_code=502, detail=f"LLM 调用失败: {e}")

    # 解析结果
    cases_data = result.get("cases", [])
    if not cases_data:
        # 尝试宽松解析
        logger.warning("LLM 返回的 cases 为空，尝试宽松解析原始响应")
        raise HTTPException(status_code=502, detail="LLM 未返回有效用例数据，请调整场景描述重试")

    if len(cases_data) < count:
        logger.info("LLM 生成 %d 条，请求 %d 条", len(cases_data), count)

    # 计算起始 sort_order
    from sqlalchemy import func
    max_order = (
        db.query(func.max(EvalCase.sort_order))
        .filter(EvalCase.suite_id == suite_id)
        .scalar()
    )
    next_order = int(max_order or 0) + 1

    created_cases = []
    for i, case_data in enumerate(cases_data):
        input_prompt = (case_data.get("input_prompt") or "").strip()
        if not input_prompt:
            continue

        difficulty = case_data.get("difficulty", "medium")
        if difficulty not in ("easy", "medium", "hard"):
            difficulty = "medium"

        expected_output_type = case_data.get("expected_output_type", output_type if output_type != "mixed" else "text")

        row = EvalCase(
            suite_id=suite_id,
            input_prompt=input_prompt,
            input_variables=case_data.get("input_variables"),
            expected_output_type=expected_output_type,
            difficulty=difficulty,
            category=case_data.get("category") or "",
            remark=case_data.get("remark"),
            sort_order=next_order + i,
            is_active=True,
        )
        db.add(row)
        db.flush()

        # 生成参考答案
        if generate_ground_truth:
            expected_output = (case_data.get("expected_output") or "").strip()
            if expected_output:
                gt = EvalCaseGroundTruth(
                    case_id=row.id,
                    version="v1.0",
                    ground_truth=expected_output,
                    ground_truth_type=expected_output_type,
                    comparison_method=comparison_method,
                    comparison_config=None,
                    is_active=True,
                )
                db.add(gt)

        created_cases.append({
            "id": row.id,
            "input_prompt": input_prompt,
            "expected_output_type": expected_output_type,
            "difficulty": difficulty,
            "category": case_data.get("category"),
            "remark": case_data.get("remark"),
        })

    db.commit()

    return {
        "ok": True,
        "suite_id": suite_id,
        "created_count": len(created_cases),
        "requested_count": count,
        "cases": created_cases,
    }
