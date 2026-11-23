"""
评测对比服务层 — 执行实际输出与参考答案的对比
"""
import json
import logging
import re
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from ...models.eval import EvalComparison, EvalCaseGroundTruth, EvalRun
from ...core.llm_policy import model_thinking_payload

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------


def run_comparison(
    db: Session,
    run_id: int,
    *,
    force_llm_judge: bool = False,
    timeout_seconds: Optional[int] = None,
    retry_count: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """为单个运行记录执行对比。返回对比结果列表。"""
    run = db.query(EvalRun).filter(EvalRun.id == run_id).first()
    if not run:
        return []

    # 找到该用例的所有活跃参考答案
    gts = (
        db.query(EvalCaseGroundTruth)
        .filter(
            EvalCaseGroundTruth.case_id == run.case_id,
            EvalCaseGroundTruth.is_active.is_(True),
        )
        .all()
    )

    if not gts:
        comparison = EvalComparison(
            run_id=run_id,
            ground_truth_id=0,
            comparison_method="llm_judge" if force_llm_judge else "missing_ground_truth",
            is_correct=None,
            score=None,
            comparison_detail={"error": "无活跃参考答案，无法执行 LLM 评判"},
            llm_judge_raw_output=None,
        )
        db.add(comparison)
        db.commit()
        return [{
            "ground_truth_id": 0,
            "comparison_method": comparison.comparison_method,
            "is_correct": None,
            "score": None,
            "detail": comparison.comparison_detail,
        }]

    gt_items = [
        {
            "id": gt.id,
            "ground_truth": gt.ground_truth,
            "comparison_config": dict(gt.comparison_config or {}),
            "comparison_method": gt.comparison_method,
        }
        for gt in gts
    ]

    # 获取用例的原始问题（LLM judge 需要）
    from ...models.eval import EvalCase, EvalComparisonTemplate, EvalSubTask, EvalTask
    case = db.query(EvalCase).filter(EvalCase.id == run.case_id).first()
    question = case.input_prompt if case else ""

    # 获取子任务的模型配置
    sub_task = db.query(EvalSubTask).filter(EvalSubTask.id == run.sub_task_id).first()
    target_config = sub_task.target_config if sub_task else {}
    task = db.query(EvalTask).filter(EvalTask.id == sub_task.task_id).first() if sub_task else None
    template = (
        db.query(EvalComparisonTemplate)
        .filter(EvalComparisonTemplate.id == task.output_template_id)
        .first()
        if task and task.output_template_id else None
    )

    actual_output = _extract_actual_output(run)
    target_config = dict(target_config or {})
    template_prompts = None
    if template:
        template_prompts = {
            "system_prompt": template.system_prompt,
            "user_prompt": template.user_prompt,
        }

    # 释放前面查询占用的连接。后续 LLM judge 可能等待几十到几百秒，
    # 期间不能持有主库连接，否则评测并发会拖死其它接口。
    db.commit()

    results = []

    for gt in gt_items:
        comparison_config = dict(gt["comparison_config"] or {})
        comparison_method = (
            "llm_judge"
            if force_llm_judge or template_prompts or target_config.get("llm_provider_id") or target_config.get("llm_model")
            else gt["comparison_method"]
        )
        # LLM judge 需要原始问题和模型配置
        if comparison_method == "llm_judge":
            comparison_config = {
                **comparison_config,
                "question": question,
                "llm_provider_id": target_config.get("llm_provider_id"),
                "llm_model": target_config.get("llm_model"),
                "timeout_seconds": timeout_seconds,
                "retry_count": retry_count,
            }
            if template_prompts:
                comparison_config.update(template_prompts)

        result = execute_comparison(
            actual_output=actual_output,
            ground_truth=gt["ground_truth"],
            method=comparison_method,
            config=comparison_config,
        )

        # 保存对比记录
        comparison = EvalComparison(
            run_id=run_id,
            ground_truth_id=gt["id"],
            comparison_method=comparison_method,
            is_correct=result.get("is_correct"),
            score=result.get("score"),
            comparison_detail=result.get("detail"),
            llm_judge_raw_output=result.get("llm_raw_output"),
        )
        db.add(comparison)
        results.append({
            "ground_truth_id": gt["id"],
            "comparison_method": comparison_method,
            "is_correct": result.get("is_correct"),
            "score": result.get("score"),
            "detail": result.get("detail"),
        })

    db.commit()
    return results


def batch_recompare(db: Session, run_ids: List[int]) -> Dict[str, Any]:
    """批量重新对比。"""
    if not run_ids:
        return {"ok": True, "recomputed": 0}

    # 删除旧对比记录
    db.query(EvalComparison).filter(EvalComparison.run_id.in_(run_ids)).delete(
        synchronize_session=False
    )
    db.commit()

    recomputed = 0
    for run_id in run_ids:
        results = run_comparison(db, run_id)
        if results:
            recomputed += 1

    return {"ok": True, "recomputed": recomputed}


def execute_comparison(
    actual_output: Any,
    ground_truth: str,
    method: str,
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    执行对比，返回：
    {
        "is_correct": bool | None,
        "score": float | None,
        "detail": dict,
        "llm_raw_output": str | None,
    }
    """
    config = config or {}

    dispatch = {
        "exact": _compare_exact,
        "contains": _compare_contains,
        "regex": _compare_regex,
        "semantic": _compare_semantic,
        "sql_execute": _compare_sql_execute,
        "llm_judge": _compare_llm_judge,
        "multi_level": _compare_multi_level,
    }

    handler = dispatch.get(method)
    if not handler:
        return {
            "is_correct": None,
            "score": None,
            "detail": {"error": f"不支持的对比方式: {method}"},
            "llm_raw_output": None,
        }

    try:
        return handler(actual_output, ground_truth, config)
    except Exception as e:  # noqa: BLE001
        logger.exception("execute_comparison failed: method=%s error=%s", method, e)
        return {
            "is_correct": None,
            "score": None,
            "detail": {"error": str(e)},
            "llm_raw_output": None,
        }


# ---------------------------------------------------------------------------
# comparison methods
# ---------------------------------------------------------------------------


def _compare_exact(
    actual: Any, expected: str, config: Dict[str, Any],
) -> Dict[str, Any]:
    """精确匹配。"""
    actual_str = _extract_sql(actual)
    expected_str = _normalize_str(expected)

    ignore_case = config.get("ignore_case", True)
    ignore_whitespace = config.get("ignore_whitespace", True)

    if ignore_whitespace:
        actual_str = re.sub(r"\s+", " ", actual_str).strip()
        expected_str = re.sub(r"\s+", " ", expected_str).strip()

    if ignore_case:
        is_correct = actual_str.lower() == expected_str.lower()
    else:
        is_correct = actual_str == expected_str

    return {
        "is_correct": is_correct,
        "score": 1.0 if is_correct else 0.0,
        "detail": {
            "actual_normalized": actual_str[:500],
            "expected_normalized": expected_str[:500],
        },
        "llm_raw_output": None,
    }


def _compare_contains(
    actual: Any, expected: str, config: Dict[str, Any],
) -> Dict[str, Any]:
    """包含匹配。"""
    actual_str = _extract_sql(actual)
    expected_str = _normalize_str(expected)

    ignore_case = config.get("ignore_case", True)

    if ignore_case:
        is_correct = expected_str.lower() in actual_str.lower()
    else:
        is_correct = expected_str in actual_str

    return {
        "is_correct": is_correct,
        "score": 1.0 if is_correct else 0.0,
        "detail": {
            "actual_normalized": actual_str[:500],
            "expected_normalized": expected_str[:500],
        },
        "llm_raw_output": None,
    }


def _compare_regex(
    actual: Any, expected: str, config: Dict[str, Any],
) -> Dict[str, Any]:
    """正则表达式匹配。"""
    actual_str = _extract_sql(actual)
    pattern = expected.strip()

    flags = 0
    if config.get("ignore_case", True):
        flags |= re.IGNORECASE

    try:
        match = re.search(pattern, actual_str, flags)
        is_correct = match is not None
    except re.error as e:
        return {
            "is_correct": None,
            "score": None,
            "detail": {"error": f"正则表达式错误: {e}"},
            "llm_raw_output": None,
        }

    return {
        "is_correct": is_correct,
        "score": 1.0 if is_correct else 0.0,
        "detail": {
            "pattern": pattern,
            "matched": match.group() if match else None,
        },
        "llm_raw_output": None,
    }


def _compare_semantic(
    actual: Any, expected: str, config: Dict[str, Any],
) -> Dict[str, Any]:
    """语义相似度对比（桩函数 — 需要 embedding 服务）。"""
    return {
        "is_correct": None,
        "score": None,
        "detail": {"error": "语义对比功能尚未实现，需要 embedding 服务支持"},
        "llm_raw_output": None,
    }


def _compare_sql_execute(
    actual: Any, expected: str, config: Dict[str, Any],
) -> Dict[str, Any]:
    """SQL 执行对比（桩函数 — 需要数据源）。"""
    return {
        "is_correct": None,
        "score": None,
        "detail": {"error": "SQL 执行对比功能尚未实现，需要数据源支持"},
        "llm_raw_output": None,
    }


def _compare_llm_judge(
    actual: Any, expected: str, config: Dict[str, Any],
) -> Dict[str, Any]:
    """LLM 评判：用大模型对比生成的 SQL 与预期答案是否逻辑等价。"""
    # 从 actual 中提取 generated_sql
    generated_sql = _extract_sql(actual)

    question = config.get("question", "")
    provider_id = config.get("llm_provider_id")
    model = config.get("llm_model")
    system_prompt = config.get("system_prompt")
    user_prompt = config.get("user_prompt")
    timeout_seconds = config.get("timeout_seconds")
    retry_count = config.get("retry_count")

    return _llm_judge_call_sync(
        question,
        expected,
        generated_sql or "",
        provider_id,
        model,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        timeout_seconds=timeout_seconds,
        retry_count=retry_count,
    )


def _llm_judge_call_sync(
    question: str, expected: str, generated_sql: str,
    provider_id: Optional[int] = None, model_name: Optional[str] = None,
    system_prompt: Optional[str] = None, user_prompt: Optional[str] = None,
    timeout_seconds: Optional[int] = None, retry_count: Optional[int] = None,
) -> Dict[str, Any]:
    """同步调用 LLM 进行 SQL 逻辑对比（使用 httpx.Client）。"""
    from ...core.model_stream import complete_sync

    from ...core.database import SessionLocal
    from ...repositories.model_provider import ModelProviderRepository

    # 获取 LLM 配置
    db = SessionLocal()
    try:
        provider = None
        if provider_id:
            provider = ModelProviderRepository.get_by_id(db, provider_id)
        if not provider:
            for p in ModelProviderRepository.get_all(db):
                if getattr(p, "is_active", False) and (getattr(p, "protocol", "openai") == "openai"):
                    provider = p
                    break
        if not provider or not provider.api_key:
            return {
                "is_correct": None,
                "score": None,
                "detail": {"error": "未找到可用的模型供应商"},
                "llm_raw_output": None,
            }
        base_url = provider.base_url
        api_key = provider.api_key
        model = model_name or _parse_first_model(provider.models) or "gpt-4o-mini"
    finally:
        db.close()

    default_system_prompt = """你是企业级 SQL 评测仲裁专家（Senior SQL Evaluation Arbiter）。
你的任务不是“看起来像”，而是严格判断“业务语义是否等价”。

评审原则（必须遵守）：
1) 语义优先：优先判断业务目标与统计口径，而非仅比较语法表面。
2) 保守裁决：证据不足时返回 pending，禁止猜测性 pass。
3) 误差敏感：任何会改变业务结论的差异（过滤、连接、时间边界、聚合口径、去重）都应判为 fail。
4) 可复核：结论必须可被他人复现理解，理由简洁但指向核心差异。
5) 输出合规：仅返回 JSON，不得输出解释性前后缀、Markdown 或代码块。"""

    default_user_prompt = """## 评测输入
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

    system_prompt = system_prompt or default_system_prompt
    user_prompt = _render_judge_prompt(
        user_prompt or default_user_prompt,
        question=question,
        expected=expected,
        generated_sql=generated_sql,
    )

    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.1,
        "max_tokens": 5000,
        "stream": False,
    }

    llm_timeout = _coerce_int(timeout_seconds, 90, minimum=30, maximum=600)
    try:
        data = complete_sync(url, model_thinking_payload(payload, provider), headers,
            timeout=float(llm_timeout), operation='eval.judge', provider_id=getattr(provider, 'id', provider_id),
            provider=getattr(provider, 'name', None))
        content = data['choices'][0]['message'].get('content') or ''
    except Exception as error:
        return {
            'is_correct': None, 'score': None,
            'detail': {'error': f'LLM 调用失败: {error}', 'attempts': 1},
            'llm_raw_output': str(error),
        }

    # 解析 JSON 响应
    parsed = _loose_parse_json(content)
    result_str = (parsed.get("result") or "").lower()
    score = parsed.get("score")
    reason = str(parsed.get("reason", "") or "").strip()
    if len(reason) > 50:
        reason = reason[:50]

    is_correct = None
    if result_str == "pass":
        is_correct = True
    elif result_str == "fail":
        is_correct = False

    if score is not None:
        try:
            score = float(score)
        except (TypeError, ValueError):
            score = None

    return {
        "is_correct": is_correct,
        "score": score,
        "detail": {
            "result": result_str,
            "reason": reason,
            "generated_sql": generated_sql[:2000],
        },
        "llm_raw_output": content,
    }


def _parse_first_model(raw: Optional[str]) -> Optional[str]:
    """从供应商 models 字段中取第一个模型名。"""
    if not raw:
        return None
    try:
        obj = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return raw.split(",")[0].strip() if raw else None
    if isinstance(obj, list) and obj:
        return str(obj[0]).strip()
    if isinstance(obj, dict):
        vals = obj.get("models") or obj.get("list") or []
        if isinstance(vals, list) and vals:
            return str(vals[0]).strip()
    return None


def _coerce_int(value: Any, default: int, *, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


def _render_judge_prompt(template: str, **values: str) -> str:
    """Render known judge placeholders without interpreting JSON braces."""
    text = template or ""
    for key, value in values.items():
        safe_value = "" if value is None else str(value)
        text = text.replace("{" + key + "}", safe_value)
        text = text.replace("{{" + key + "}}", safe_value)
    return text


def _loose_parse_json(content: str) -> Dict[str, Any]:
    """宽松解析 JSON（兼容 ```json 代码块等）。"""
    if not content:
        return {}
    text = content.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    code_fence = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)
    m = code_fence.search(text)
    if m:
        inner = m.group(1).strip()
        try:
            return json.loads(inner)
        except json.JSONDecodeError:
            text = inner

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass

    return {}


def _compare_multi_level(
    actual: Any, expected: str, config: Dict[str, Any],
) -> Dict[str, Any]:
    """多级对比：依次尝试 exact → contains → semantic，取最优。"""
    levels = config.get("levels", ["exact", "contains"])

    best_result: Optional[Dict[str, Any]] = None
    best_score = -1.0

    level_dispatch = {
        "exact": _compare_exact,
        "contains": _compare_contains,
        "regex": _compare_regex,
    }

    for level in levels:
        handler = level_dispatch.get(level)
        if not handler:
            continue
        result = handler(actual, expected, config)
        score = result.get("score")
        if score is not None and score > best_score:
            best_score = score
            best_result = result
            if score >= 1.0:
                break  # 完全匹配，无需继续

    if best_result:
        best_result["detail"] = {**(best_result.get("detail") or {}), "levels_tried": levels}
        return best_result

    return {
        "is_correct": None,
        "score": None,
        "detail": {"error": "多级对比未产生有效结果", "levels_tried": levels},
        "llm_raw_output": None,
    }


# ---------------------------------------------------------------------------
# utilities
# ---------------------------------------------------------------------------


def _normalize_str(val: Any) -> str:
    """将任意类型转为字符串。"""
    if val is None:
        return ""
    if isinstance(val, str):
        return val
    if isinstance(val, (dict, list)):
        import json
        return json.dumps(val, ensure_ascii=False)
    return str(val)


def _extract_sql(actual: Any) -> str:
    """从 actual 输出中提取 SQL。优先取 generated_sql 字段，否则回退到整个值。"""
    if isinstance(actual, dict):
        sql = actual.get("generated_sql") or actual.get("sql") or ""
        if sql:
            return sql
    if isinstance(actual, str):
        return actual
    return _normalize_str(actual)


def _extract_actual_output(run: EvalRun) -> Any:
    """从运行记录中提取实际输出。"""
    if run.parsed_response is not None:
        return run.parsed_response
    if run.raw_response:
        return run.raw_response
    return None


# ---------------------------------------------------------------------------
# run / comparison query helpers (used by router)
# ---------------------------------------------------------------------------

def list_runs_service(
    db: Session, sub_task_id: int, status: str = None,
    skip: int = 0, limit: int = 50,
) -> Dict[str, Any]:
    """获取子任务的运行记录列表（含对比结果摘要）。"""
    from ...models.eval import EvalRun

    q = db.query(EvalRun).filter(EvalRun.sub_task_id == sub_task_id)
    if status:
        q = q.filter(EvalRun.status == status)
    total = q.count()
    items = q.order_by(EvalRun.id.asc()).offset(skip).limit(limit).all()

    # 批量查询对比记录
    run_ids = [r.id for r in items]
    comps = {}
    if run_ids:
        comp_rows = (
            db.query(EvalComparison)
            .filter(EvalComparison.run_id.in_(run_ids))
            .all()
        )
        for c in comp_rows:
            comps[c.run_id] = c

    result_items = []
    for r in items:
        d = _run_to_dict(r)
        comp = comps.get(r.id)
        if comp:
            detail = comp.comparison_detail or {}
            d["comparison_result"] = "pass" if comp.is_correct else ("fail" if comp.is_correct is False else "pending")
            d["comparison_score"] = float(comp.score) if comp.score is not None else None
            d["comparison_reason"] = detail.get("reason") or ""
            d["comparison_method"] = comp.comparison_method
            d["llm_judge_raw_output"] = comp.llm_judge_raw_output
            d["manual_is_correct"] = detail.get("manual_is_correct")
            d["manual_note"] = detail.get("manual_note") or ""
            d["fix_status"] = "已修复" if detail.get("fix_status") == "fixed" else "未修复"
            d["fixer_username"] = detail.get("fixed_by_username") or detail.get("manual_corrected_by_username")
        else:
            d["comparison_result"] = None
            d["comparison_score"] = None
            d["comparison_reason"] = None
            d["comparison_method"] = None
            d["llm_judge_raw_output"] = None
            d["manual_is_correct"] = None
            d["manual_note"] = None
            d["fix_status"] = None
            d["fixer_username"] = None
        result_items.append(d)

    return {
        "total": total,
        "items": result_items,
    }


def get_run_service(db: Session, run_id: int) -> Dict[str, Any]:
    """获取单条运行记录详情（含对比信息）。"""
    from ...models.eval import EvalRun

    run = db.query(EvalRun).filter(EvalRun.id == run_id).first()
    if not run:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="运行记录不存在")

    result = _run_to_dict(run)

    # 附加对比信息
    comp = db.query(EvalComparison).filter(EvalComparison.run_id == run_id).first()
    if comp:
        result["comparison"] = {
            "id": comp.id,
            "method": comp.comparison_method,
            "is_correct": comp.is_correct,
            "score": float(comp.score) if comp.score is not None else None,
            "detail": comp.comparison_detail,
        }
    else:
        result["comparison"] = None

    return result


def manual_correct_service(db: Session, run_id: int, data, user_id: int) -> Dict[str, Any]:
    """人工标注。"""
    from ...models.eval import EvalRun
    from ...models.user import User

    run = db.query(EvalRun).filter(EvalRun.id == run_id).first()
    if not run:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="运行记录不存在")

    user = db.query(User).filter(User.id == user_id).first()
    username = (
        (getattr(user, "display_name", None) or getattr(user, "username", None) or f"user#{user_id}")
        if user_id else ""
    )

    # 更新对比结果
    comp = db.query(EvalComparison).filter(EvalComparison.run_id == run_id).first()
    if comp:
        prev_is_correct = comp.is_correct
        comp.is_correct = data.is_correct
        detail = {
            **(comp.comparison_detail or {}),
            "manual_note": data.note,
            "manual_corrected": True,
            "manual_is_correct": data.is_correct,
            "manual_corrected_by_user_id": user_id,
            "manual_corrected_by_username": username,
        }
        # “修复状态改成正确”视作修复成功，记录修复人
        if prev_is_correct is False and data.is_correct is True:
            detail["fix_status"] = "fixed"
            detail["fixed_by_user_id"] = user_id
            detail["fixed_by_username"] = username
        elif data.is_correct is False:
            detail["fix_status"] = "unfixed"
        comp.comparison_detail = detail
    else:
        # 没有对比记录时创建一条人工标注
        detail = {
            "manual_note": data.note,
            "manual_corrected": True,
            "manual_is_correct": data.is_correct,
            "manual_corrected_by_user_id": user_id,
            "manual_corrected_by_username": username,
            "fix_status": "fixed" if data.is_correct else "unfixed",
        }
        if data.is_correct:
            detail["fixed_by_user_id"] = user_id
            detail["fixed_by_username"] = username
        comp = EvalComparison(
            run_id=run_id,
            ground_truth_id=0,
            comparison_method="manual",
            is_correct=data.is_correct,
            score=1.0 if data.is_correct else 0.0,
            comparison_detail=detail,
        )
        db.add(comp)

    db.commit()
    return {"ok": True}


def get_comparison_service(db: Session, run_id: int) -> Dict[str, Any]:
    """获取对比详情。"""
    comp = db.query(EvalComparison).filter(EvalComparison.run_id == run_id).first()
    if not comp:
        return {"run_id": run_id, "comparison": None}
    return {
        "run_id": run_id,
        "comparison": {
            "id": comp.id,
            "ground_truth_id": comp.ground_truth_id,
            "method": comp.comparison_method,
            "is_correct": comp.is_correct,
            "score": float(comp.score) if comp.score is not None else None,
            "detail": comp.comparison_detail,
        },
    }


def _run_to_dict(run: EvalRun) -> Dict[str, Any]:
    """将 EvalRun 转为字典。"""
    # 提取实际输出
    actual_output = None
    if run.parsed_response is not None:
        if isinstance(run.parsed_response, dict):
            actual_output = run.parsed_response.get("generated_sql") or run.parsed_response.get("answer") or run.parsed_response.get("result") or str(run.parsed_response)
        else:
            actual_output = str(run.parsed_response)
    elif run.raw_response:
        actual_output = run.raw_response

    trace_id = None
    if isinstance(run.parsed_response, dict):
        trace_id = run.parsed_response.get("trace_id")

    return {
        "id": run.id,
        "sub_task_id": run.sub_task_id,
        "case_id": run.case_id,
        "status": run.status,
        "actual_output": actual_output,
        "raw_response": run.raw_response,
        "parsed_response": run.parsed_response,
        "trace_id": trace_id,
        "error_message": run.error_message,
        "execution_time_ms": run.execution_time_ms,
        "attempt": run.attempt,
        "started_at": str(run.started_at) if run.started_at else None,
        "completed_at": str(run.completed_at) if run.completed_at else None,
        "created_at": str(run.created_at) if run.created_at else None,
    }
