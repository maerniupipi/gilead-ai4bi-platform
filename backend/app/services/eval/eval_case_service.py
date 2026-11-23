"""
评测用例服务层
"""
import copy
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from ...models.eval import EvalCase, EvalCaseGroundTruth, EvalSuite


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _case_to_dict(row: EvalCase, ground_truths: Optional[List[Dict]] = None) -> Dict[str, Any]:
    d: Dict[str, Any] = {
        "id": row.id,
        "suite_id": row.suite_id,
        "input_prompt": row.input_prompt,
        "input_variables": row.input_variables,
        "expected_output_type": row.expected_output_type,
        "difficulty": row.difficulty,
        "category": row.category,
        "remark": row.remark,
        "sort_order": row.sort_order,
        "is_active": row.is_active,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }
    if ground_truths is not None:
        d["ground_truths"] = ground_truths
    return d


def _gt_to_dict(row: EvalCaseGroundTruth) -> Dict[str, Any]:
    return {
        "id": row.id,
        "case_id": row.case_id,
        "version": row.version,
        "ground_truth": row.ground_truth,
        "ground_truth_type": row.ground_truth_type,
        "comparison_method": row.comparison_method,
        "comparison_config": row.comparison_config,
        "is_active": row.is_active,
    }


def _validate_suite(db: Session, suite_id: int) -> EvalSuite:
    suite = db.query(EvalSuite).filter(EvalSuite.id == suite_id).first()
    if not suite:
        raise HTTPException(status_code=404, detail="评测集不存在")
    return suite


def _get_ground_truths_for_cases(
    db: Session, case_ids: List[int],
) -> Dict[int, List[Dict[str, Any]]]:
    """批量获取用例的参考答案，按 case_id 分组。"""
    if not case_ids:
        return {}
    rows = (
        db.query(EvalCaseGroundTruth)
        .filter(EvalCaseGroundTruth.case_id.in_(case_ids))
        .order_by(EvalCaseGroundTruth.id.asc())
        .all()
    )
    result: Dict[int, List[Dict[str, Any]]] = {}
    for r in rows:
        result.setdefault(r.case_id, []).append(_gt_to_dict(r))
    return result


def _create_ground_truths(db: Session, case_id: int, gt_list: List[Dict[str, Any]]) -> None:
    """为用例创建参考答案。"""
    for gt_data in gt_list:
        ground_truth = (gt_data.get("ground_truth") or "").strip()
        if not ground_truth:
            continue
        row = EvalCaseGroundTruth(
            case_id=case_id,
            version=gt_data.get("version", "v1.0"),
            ground_truth=ground_truth,
            ground_truth_type=gt_data.get("ground_truth_type", "text"),
            comparison_method=gt_data.get("comparison_method", "exact"),
            comparison_config=gt_data.get("comparison_config"),
            is_active=gt_data.get("is_active", True),
        )
        db.add(row)


# ---------------------------------------------------------------------------
# service functions
# ---------------------------------------------------------------------------

def list_cases_service(
    db: Session,
    suite_id: int,
    filters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """列出评测集下的用例，支持筛选。"""
    _validate_suite(db, suite_id)
    filters = filters or {}

    q = db.query(EvalCase).filter(EvalCase.suite_id == suite_id)

    if "difficulty" in filters and filters["difficulty"]:
        q = q.filter(EvalCase.difficulty == filters["difficulty"])

    if "category" in filters and filters["category"]:
        q = q.filter(EvalCase.category == filters["category"])

    if "is_active" in filters and filters["is_active"] is not None:
        q = q.filter(EvalCase.is_active == filters["is_active"])

    if "keyword" in filters and filters["keyword"]:
        kw = f"%{filters['keyword'].strip()}%"
        q = q.filter(EvalCase.input_prompt.like(kw))

    skip = filters.get("skip", 0)
    limit = filters.get("limit", 100)

    total = q.count()
    rows = q.order_by(EvalCase.sort_order.asc(), EvalCase.id.asc()).offset(skip).limit(limit).all()

    case_ids = [r.id for r in rows]
    gt_map = _get_ground_truths_for_cases(db, case_ids)

    items = [
        _case_to_dict(r, ground_truths=gt_map.get(r.id, []))
        for r in rows
    ]

    return {"items": items, "total": total, "skip": skip, "limit": limit}


def create_case_service(
    db: Session, suite_id: int, data: Dict[str, Any],
) -> Dict[str, Any]:
    """创建用例。"""
    suite = _validate_suite(db, suite_id)
    default_comparison_method = suite.default_comparison_method or "exact"

    input_prompt = (data.get("input_prompt") or "").strip()
    if not input_prompt:
        raise HTTPException(status_code=400, detail="输入提示词不能为空")

    # 计算 sort_order
    max_order = (
        db.query(func.max(EvalCase.sort_order))
        .filter(EvalCase.suite_id == suite_id)
        .scalar()
    )
    next_order = int(max_order or 0) + 1

    row = EvalCase(
        suite_id=suite_id,
        input_prompt=input_prompt,
        input_variables=data.get("input_variables"),
        expected_output_type=data.get("expected_output_type", "text"),
        difficulty=data.get("difficulty", "medium"),
        category=data.get("category"),
        remark=data.get("remark"),
        sort_order=data.get("sort_order", next_order),
        is_active=data.get("is_active", True),
    )
    db.add(row)
    db.flush()

    # 创建参考答案
    gt_list = data.get("ground_truths", [])
    if not gt_list:
        expected = data.get("expected_output") or data.get("expected_answer") or ""
        if expected.strip():
            gt_list = [{
                "ground_truth": expected.strip(),
                "comparison_method": data.get("comparison_method", default_comparison_method),
            }]
    if gt_list:
        _create_ground_truths(db, row.id, gt_list)

    db.commit()
    db.refresh(row)

    gt_map = _get_ground_truths_for_cases(db, [row.id])
    return _case_to_dict(row, ground_truths=gt_map.get(row.id, []))


def update_case_service(
    db: Session, case_id: int, suite_id: int, data: Dict[str, Any],
) -> Dict[str, Any]:
    """更新用例。"""
    row = db.query(EvalCase).filter(
        EvalCase.id == case_id,
        EvalCase.suite_id == suite_id,
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="评测用例不存在")
    suite = _validate_suite(db, suite_id)
    default_comparison_method = suite.default_comparison_method or "exact"

    if "input_prompt" in data:
        ip = (data["input_prompt"] or "").strip()
        if not ip:
            raise HTTPException(status_code=400, detail="输入提示词不能为空")
        row.input_prompt = ip

    if "input_variables" in data:
        row.input_variables = data["input_variables"]

    if "expected_output_type" in data:
        row.expected_output_type = data["expected_output_type"]

    if "difficulty" in data:
        row.difficulty = data["difficulty"]

    if "category" in data:
        row.category = data["category"]

    if "remark" in data:
        row.remark = data["remark"]

    if "sort_order" in data:
        row.sort_order = data["sort_order"]

    if "is_active" in data:
        row.is_active = bool(data["is_active"])

    # expected_output 映射到第一个参考答案
    if "expected_output" in data:
        expected_output = data["expected_output"]
        gt_list = db.query(EvalCaseGroundTruth).filter(
            EvalCaseGroundTruth.case_id == case_id,
            EvalCaseGroundTruth.is_active == True,
        ).order_by(EvalCaseGroundTruth.id.asc()).all()
        if gt_list:
            gt = gt_list[0]
            gt.ground_truth = expected_output
        elif expected_output:
            new_gt = EvalCaseGroundTruth(
                case_id=case_id,
                ground_truth=expected_output,
                ground_truth_type=data.get("expected_output_type", "text"),
                comparison_method=data.get("comparison_method", default_comparison_method),
            )
            db.add(new_gt)

    db.commit()
    db.refresh(row)

    gt_map = _get_ground_truths_for_cases(db, [row.id])
    return _case_to_dict(row, ground_truths=gt_map.get(row.id, []))


def delete_case_service(db: Session, case_id: int, suite_id: int) -> Dict[str, Any]:
    """删除用例（级联删除参考答案）。"""
    row = db.query(EvalCase).filter(
        EvalCase.id == case_id,
        EvalCase.suite_id == suite_id,
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="评测用例不存在")

    # 删除参考答案
    db.query(EvalCaseGroundTruth).filter(EvalCaseGroundTruth.case_id == case_id).delete()
    db.delete(row)
    db.commit()
    return {"ok": True}


def batch_delete_cases_service(
    db: Session, case_ids: List[int], suite_id: int,
) -> Dict[str, Any]:
    """批量删除用例。"""
    if not case_ids:
        raise HTTPException(status_code=400, detail="用例ID列表不能为空")

    rows = (
        db.query(EvalCase)
        .filter(EvalCase.id.in_(case_ids), EvalCase.suite_id == suite_id)
        .all()
    )
    found_ids = [r.id for r in rows]
    if not found_ids:
        raise HTTPException(status_code=404, detail="未找到匹配的用例")

    # 删除参考答案
    db.query(EvalCaseGroundTruth).filter(
        EvalCaseGroundTruth.case_id.in_(found_ids)
    ).delete(synchronize_session=False)

    # 删除用例
    db.query(EvalCase).filter(EvalCase.id.in_(found_ids)).delete(synchronize_session=False)
    db.commit()

    return {"ok": True, "deleted_count": len(found_ids)}


def batch_update_cases_service(
    db: Session, case_ids: List[int], suite_id: int, data: Dict[str, Any],
) -> Dict[str, Any]:
    """批量更新用例。"""
    if not case_ids:
        raise HTTPException(status_code=400, detail="用例ID列表不能为空")

    rows = (
        db.query(EvalCase)
        .filter(EvalCase.id.in_(case_ids), EvalCase.suite_id == suite_id)
        .all()
    )
    if not rows:
        raise HTTPException(status_code=404, detail="未找到匹配的用例")

    update_fields = {}
    for key in ("difficulty", "category", "is_active", "expected_output_type"):
        if key in data:
            update_fields[key] = data[key]

    for row in rows:
        for k, v in update_fields.items():
            setattr(row, k, v)

    db.commit()
    return {"ok": True, "updated_count": len(rows)}


# generate_cases_service 已迁移至 eval_case_generate_service.py（异步 LLM 调用）
# 此处保留转发以保持向后兼容，新代码请直接导入 eval_case_generate_service


def import_cases_service(
    db: Session, suite_id: int, data: Dict[str, Any],
) -> Dict[str, Any]:
    """批量导入用例。"""
    suite = _validate_suite(db, suite_id)
    default_comparison_method = suite.default_comparison_method or "exact"

    cases_data = data.get("cases", [])
    if not cases_data:
        raise HTTPException(status_code=400, detail="导入数据不能为空")

    import_mode = data.get("import_mode", "skip")  # skip | overwrite | insert
    skip_duplicates = import_mode == "skip"
    overwrite_duplicates = import_mode == "overwrite"

    # 计算起始 sort_order
    max_order = (
        db.query(func.max(EvalCase.sort_order))
        .filter(EvalCase.suite_id == suite_id)
        .scalar()
    )
    next_order = int(max_order or 0) + 1

    created_count = 0
    updated_count = 0
    skipped_count = 0

    for i, case_data in enumerate(cases_data):
        input_prompt = (case_data.get("input_prompt") or "").strip()
        if not input_prompt:
            continue

        gt_list = case_data.get("ground_truths", [])
        if not gt_list and case_data.get("expected_answer"):
            gt_list = [{
                "ground_truth": str(case_data["expected_answer"]),
                "comparison_method": case_data.get("comparison_method", default_comparison_method),
            }]

        # 查找是否已存在相同 input_prompt 的用例
        existing = (
            db.query(EvalCase)
            .filter(EvalCase.suite_id == suite_id, EvalCase.input_prompt == input_prompt)
            .first()
        )

        if existing:
            if skip_duplicates:
                skipped_count += 1
                continue
            if overwrite_duplicates:
                existing.expected_output_type = case_data.get("expected_output_type", existing.expected_output_type)
                existing.difficulty = case_data.get("difficulty", existing.difficulty)
                existing.category = case_data.get("category", existing.category)
                existing.remark = case_data.get("remark", existing.remark)
                # 更新参考答案
                db.query(EvalCaseGroundTruth).filter(EvalCaseGroundTruth.case_id == existing.id).delete()
                if gt_list:
                    _create_ground_truths(db, existing.id, gt_list)
                db.flush()
                updated_count += 1
                continue

        row = EvalCase(
            suite_id=suite_id,
            input_prompt=input_prompt,
            input_variables=case_data.get("input_variables"),
            expected_output_type=case_data.get("expected_output_type", "text"),
            difficulty=case_data.get("difficulty", "medium"),
            category=case_data.get("category"),
            remark=case_data.get("remark"),
            sort_order=next_order + i,
            is_active=case_data.get("is_active", True),
        )
        db.add(row)
        db.flush()

        if gt_list:
            _create_ground_truths(db, row.id, gt_list)

        created_count += 1

    db.commit()
    return {
        "ok": True,
        "created_count": created_count,
        "updated_count": updated_count,
        "skipped_count": skipped_count,
    }


def import_preview_service(db: Session, data: Dict[str, Any]) -> Dict[str, Any]:
    """预览导入数据，校验格式。"""
    cases_data = data.get("cases", [])
    if not cases_data:
        raise HTTPException(status_code=400, detail="导入数据不能为空")

    valid_cases = []
    errors = []

    for i, case_data in enumerate(cases_data):
        row_num = i + 1
        input_prompt = (case_data.get("input_prompt") or "").strip()
        if not input_prompt:
            errors.append({"row": row_num, "error": "input_prompt 为空"})
            continue

        valid_cases.append({
            "row": row_num,
            "input_prompt": input_prompt,
            "input_variables": case_data.get("input_variables"),
            "expected_output_type": case_data.get("expected_output_type", "text"),
            "difficulty": case_data.get("difficulty", "medium"),
            "category": case_data.get("category"),
            "remark": case_data.get("remark"),
            "ground_truths": case_data.get("ground_truths", []),
        })

    return {
        "valid_count": len(valid_cases),
        "error_count": len(errors),
        "valid_cases": valid_cases,
        "errors": errors,
    }


def export_cases_service(db: Session, suite_id: int) -> Dict[str, Any]:
    """导出评测集所有用例。"""
    _validate_suite(db, suite_id)

    rows = (
        db.query(EvalCase)
        .filter(EvalCase.suite_id == suite_id)
        .order_by(EvalCase.sort_order.asc(), EvalCase.id.asc())
        .all()
    )

    case_ids = [r.id for r in rows]
    gt_map = _get_ground_truths_for_cases(db, case_ids)

    cases = []
    for r in rows:
        cases.append({
            "input_prompt": r.input_prompt,
            "input_variables": r.input_variables,
            "expected_output_type": r.expected_output_type,
            "difficulty": r.difficulty,
            "category": r.category,
            "remark": r.remark,
            "sort_order": r.sort_order,
            "is_active": r.is_active,
            "ground_truths": gt_map.get(r.id, []),
        })

    suite = db.query(EvalSuite).filter(EvalSuite.id == suite_id).first()
    return {
        "suite_name": suite.name if suite else "",
        "suite_version": suite.version if suite else "",
        "case_count": len(cases),
        "cases": cases,
    }


def batch_create_cases_service(
    db: Session, suite_id: int, data: list,
) -> Dict[str, Any]:
    """批量创建用例。"""
    _validate_suite(db, suite_id)

    created = []
    for item in data:
        case = EvalCase(
            suite_id=suite_id,
            input_prompt=item.input_prompt,
            input_variables=item.input_variables,
            expected_output_type=item.expected_output_type,
            difficulty=item.difficulty,
            category=item.category,
            remark=item.remark,
            sort_order=item.sort_order,
            is_active=item.is_active,
        )
        db.add(case)
        db.flush()
        created.append(_case_to_dict(case))

    db.commit()
    return {"created": len(created), "items": created}


def download_import_template_service() -> Dict[str, Any]:
    """返回导入模板说明。"""
    return {
        "fields": [
            {"name": "input_prompt", "required": True, "description": "输入提示词"},
            {"name": "expected_answer", "required": False, "description": "期望答案"},
            {"name": "expected_output_type", "required": False, "description": "期望输出类型: text/sql/json/number/boolean", "default": "text"},
            {"name": "difficulty", "required": False, "description": "难度: easy/medium/hard", "default": "medium"},
            {"name": "category", "required": False, "description": "问题分类"},
            {"name": "remark", "required": False, "description": "备注"},
            {"name": "comparison_method", "required": False, "description": "对比方式: exact/regex/semantic/sql_execute/llm_judge", "default": "exact"},
        ],
        "example": [
            {
                "input_prompt": "查询2024年销售额最高的产品",
                "expected_answer": "产品A: 1000万",
                "expected_output_type": "text",
                "difficulty": "medium",
                "category": "金融",
                "remark": "用于校验聚合与排序能力",
                "comparison_method": "exact",
            }
        ],
    }
