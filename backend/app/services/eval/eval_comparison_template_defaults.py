"""
评测对比模板默认配置
"""
from typing import Dict, List

from sqlalchemy.orm import Session

from ...models.eval import EvalComparisonTemplate


def get_system_template_payloads() -> List[Dict[str, str]]:
    strict_system_prompt = """你是企业级 SQL 评测仲裁专家（Senior SQL Evaluation Arbiter）。
你的任务不是“看起来像”，而是严格判断“业务语义是否等价”。

评审原则（必须遵守）：
1) 语义优先：优先判断业务目标与统计口径，而非仅比较语法表面。
2) 保守裁决：证据不足时返回 pending，禁止猜测性 pass。
3) 误差敏感：任何会改变业务结论的差异（过滤、连接、时间边界、聚合口径、去重）都应判为 fail。
4) 可复核：结论必须可被他人复现理解，理由简洁但指向核心差异。
5) 输出合规：仅返回 JSON，不得输出解释性前后缀、Markdown 或代码块。"""

    strict_user_prompt = """## 评测输入
### 问题
{question}

### 参考答案（期望结果描述）
{expected}

### 实验室生成的 SQL
{generated_sql}

## 审查流程（按顺序执行）
1. 提取目标：识别参考答案的业务意图（对象、指标、时间范围、约束条件）。
2. 结构对齐：比较主表/子查询/连接键/连接类型，识别是否引入漏算或重复计数风险。
3. 条件核验：逐项核验 where/having/时间边界/状态枚举/null 处理。
4. 口径核验：核验聚合函数、group by 粒度、distinct 去重策略。
5. 结果影响评估：判断差异是否会改变最终业务结论。

## 裁决标准（严格执行）
- pass：与参考答案业务语义等价；即使写法不同，业务结论不变。
- fail：存在会影响业务结论的实质差异（任一项成立即可）。
- pending：参考答案信息不足、问题定义歧义或上下文缺失，无法确定。

## score 标尺（0~1）
- 0.90~1.00：高度确定等价（pass）
- 0.00~0.30：高度确定不等价（fail）
- 0.40~0.80：信息不足或部分一致（pending）

## 输出协议（必须严格遵守）
仅返回如下 JSON 对象，不得输出其它内容：
{
  "result": "pass" | "fail" | "pending",
  "score": 0.0 ~ 1.0,
  "reason": "一句话结论，最多50字"
}"""

    balanced_system_prompt = """你是资深 SQL 评测专家，目标是在“准确性”和“可用性”间平衡。
你需要判断生成 SQL 是否与参考答案在业务语义上等价，并给出稳定结论。"""

    balanced_user_prompt = """## 输入信息
### 问题
{question}

### 参考答案
{expected}

### 生成 SQL
{generated_sql}

## 评估要点
1. 业务目标是否一致（统计对象、指标、过滤范围）
2. 关键条件是否一致（时间、状态、关联条件）
3. 聚合口径是否一致（group by、distinct、聚合函数）

## 裁决要求
- 关键语义一致：pass
- 存在实质差异：fail
- 信息不足无法确定：pending

## 打分建议
- pass: 0.80~1.00
- fail: 0.00~0.40
- pending: 0.40~0.79

仅返回 JSON：
{
  "result": "pass" | "fail" | "pending",
  "score": 0.0 ~ 1.0,
  "reason": "一句话结论，最多50字"
}"""

    efficient_system_prompt = """你是高效率 SQL 评测助手。请快速识别关键差异并输出简洁结论。
在不牺牲正确性的前提下，尽量减少 pending。"""

    efficient_user_prompt = """问题：{question}
参考答案：{expected}
生成SQL：{generated_sql}

判断是否语义等价，重点关注：
1) 核心过滤条件
2) 聚合/分组口径
3) 是否会改变业务结论

输出规则：
- 等价 -> pass
- 不等价 -> fail
- 无法判断 -> pending

返回 JSON：
{
  "result": "pass" | "fail" | "pending",
  "score": 0.0 ~ 1.0,
  "reason": "一句话结论，最多50字"
}"""

    return [
        {
            "name": "极致严格",
            "description": "审计级评测，宁可 pending 也不误判 pass",
            "system_prompt": strict_system_prompt,
            "user_prompt": strict_user_prompt,
            "comparison_method": "llm_judge",
            "is_default": True,
            "is_system": True,
        },
        {
            "name": "平衡稳健",
            "description": "准确性与可用性平衡，适合日常评测",
            "system_prompt": balanced_system_prompt,
            "user_prompt": balanced_user_prompt,
            "comparison_method": "llm_judge",
            "is_default": False,
            "is_system": True,
        },
        {
            "name": "高效快速",
            "description": "优先快速结论，尽量减少 pending",
            "system_prompt": efficient_system_prompt,
            "user_prompt": efficient_user_prompt,
            "comparison_method": "llm_judge",
            "is_default": False,
            "is_system": True,
        },
    ]


def seed_system_templates_for_space(db: Session, space_id: int) -> None:
    existing = (
        db.query(EvalComparisonTemplate)
        .filter(EvalComparisonTemplate.space_id == space_id)
        .count()
    )
    if existing > 0:
        return

    payloads = get_system_template_payloads()
    for payload in payloads:
        db.add(EvalComparisonTemplate(space_id=space_id, **payload))
    db.commit()

