"""
评测集服务层
"""
import copy
import os
import secrets
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from ...models.eval import (
    EvalSuite,
    EvalSuiteTag,
    EvalTag,
    EvalFolder,
    EvalCase,
    EvalCaseGroundTruth,
    EvalOutputTemplate,
    EvalTask,
)
from ...schemas.eval import EvalShareIssueOut


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _suite_to_dict(
    row: EvalSuite,
    tags: Optional[List[Dict[str, Any]]] = None,
    case_count: int = 0,
    last_pass_rate: Optional[float] = None,
) -> Dict[str, Any]:
    d: Dict[str, Any] = {
        "id": row.id,
        "space_id": row.space_id,
        "folder_id": row.folder_id,
        "name": row.name,
        "description": row.description,
        "version": row.version if row.version is not None else "v1.0",
        "default_task_source_type": row.default_task_source_type if row.default_task_source_type is not None else "agent",
        "default_task_source_id": row.default_task_source_id,
        "default_task_source_config": row.default_task_source_config,
        "default_comparison_method": row.default_comparison_method if row.default_comparison_method is not None else "exact",
        "default_comparison_config": row.default_comparison_config,
        "status": row.status,
        "created_by": row.created_by,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "case_count": case_count,
        "last_pass_rate": last_pass_rate,
    }
    if tags is not None:
        d["tags"] = tags
    return d


def _get_tags_for_suite(db: Session, suite_id: int) -> List[Dict[str, Any]]:
    """获取评测集关联的标签。"""
    rows = (
        db.query(EvalTag)
        .join(EvalSuiteTag, EvalSuiteTag.tag_id == EvalTag.id)
        .filter(EvalSuiteTag.suite_id == suite_id)
        .all()
    )
    return [{"id": t.id, "name": t.name, "color": t.color} for t in rows]


def _get_case_counts(db: Session, suite_ids: List[int]) -> Dict[int, int]:
    """批量获取评测集的用例数量。"""
    if not suite_ids:
        return {}
    rows = (
        db.query(EvalCase.suite_id, func.count(EvalCase.id))
        .filter(EvalCase.suite_id.in_(suite_ids))
        .group_by(EvalCase.suite_id)
        .all()
    )
    return {sid: cnt for sid, cnt in rows}


def _get_last_pass_rates(db: Session, suite_ids: List[int]) -> Dict[int, Optional[float]]:
    """批量获取评测集最近一次任务通过率。"""
    if not suite_ids:
        return {}
    from ...models.eval import EvalTask as ET
    # 子查询：每个 suite 最新完成的 task
    latest_tasks = (
        db.query(
            ET.suite_id,
            func.max(ET.id).label("task_id"),
        )
        .filter(
            ET.suite_id.in_(suite_ids),
            ET.status.in_(["completed", "partial"]),
        )
        .group_by(ET.suite_id)
        .subquery()
    )
    rows = (
        db.query(ET.suite_id, ET.passed_cases, ET.total_cases, ET.error_cases)
        .join(latest_tasks, ET.id == latest_tasks.c.task_id)
        .all()
    )
    result: Dict[int, Optional[float]] = {}
    for sid, passed, total, errors in rows:
        non_error = int(total or 0) - int(errors or 0)
        if non_error > 0:
            result[sid] = round(int(passed or 0) / non_error, 4)
        else:
            result[sid] = None
    return result


def _sync_tags(db: Session, suite_id: int, tag_ids: List[int]) -> None:
    """同步评测集标签（全量替换）。"""
    # 删除旧关联
    db.query(EvalSuiteTag).filter(EvalSuiteTag.suite_id == suite_id).delete()
    # 添加新关联
    for tid in tag_ids:
        db.add(EvalSuiteTag(suite_id=suite_id, tag_id=tid))


def _validate_folder(db: Session, folder_id: int, space_id: int) -> None:
    folder = db.query(EvalFolder).filter(
        EvalFolder.id == folder_id,
        EvalFolder.space_id == space_id,
    ).first()
    if not folder:
        raise HTTPException(status_code=404, detail="文件夹不存在")


def _ensure_default_folder(db: Session, space_id: int) -> int:
    """获取或创建空间下的默认评测文件夹，避免 folder_id 为空导致写库失败。"""
    folder = (
        db.query(EvalFolder)
        .filter(EvalFolder.space_id == space_id, EvalFolder.is_system.is_(True))
        .order_by(EvalFolder.sort_order.asc(), EvalFolder.id.asc())
        .first()
    )
    if folder:
        return int(folder.id)

    folder = (
        db.query(EvalFolder)
        .filter(EvalFolder.space_id == space_id)
        .order_by(EvalFolder.sort_order.asc(), EvalFolder.id.asc())
        .first()
    )
    if folder:
        return int(folder.id)

    folder = EvalFolder(
        space_id=space_id,
        parent_id=None,
        name="默认文件夹",
        description="系统默认评测集文件夹",
        sort_order=0,
        is_system=True,
    )
    db.add(folder)
    db.flush()
    return int(folder.id)


# ---------------------------------------------------------------------------
# service functions
# ---------------------------------------------------------------------------

def list_suites_service(
    db: Session,
    space_id: int,
    folder_id: Optional[int] = None,
    status: Optional[str] = None,
    tag_id: Optional[int] = None,
    skip: int = 0,
    limit: int = 50,
    keyword: Optional[str] = None,
) -> Dict[str, Any]:
    """列出评测集，支持筛选和分页。"""
    q = db.query(EvalSuite).filter(EvalSuite.space_id == space_id)

    if folder_id is not None:
        q = q.filter(EvalSuite.folder_id == folder_id)

    if keyword:
        q = q.filter(EvalSuite.name.contains(keyword))

    if status:
        q = q.filter(EvalSuite.status == status)

    if tag_id:
        suite_ids_with_tag = (
            db.query(EvalSuiteTag.suite_id)
            .filter(EvalSuiteTag.tag_id == tag_id)
            .subquery()
        )
        q = q.filter(EvalSuite.id.in_(suite_ids_with_tag))

    # 总数
    total = q.count()

    # 分页
    rows = q.order_by(EvalSuite.updated_at.desc()).offset(skip).limit(limit).all()

    # 批量获取 case_count 和 last_pass_rate
    suite_ids = [r.id for r in rows]
    case_counts = _get_case_counts(db, suite_ids)
    pass_rates = _get_last_pass_rates(db, suite_ids)

    items = [_suite_to_dict(r, tags=_get_tags_for_suite(db, r.id), case_count=case_counts.get(r.id, 0), last_pass_rate=pass_rates.get(r.id)) for r in rows]

    return {"items": items, "total": total, "skip": skip, "limit": limit}


def get_suite_service(db: Session, suite_id: int, space_id: int) -> Dict[str, Any]:
    """获取评测集详情（含标签）。"""
    row = db.query(EvalSuite).filter(
        EvalSuite.id == suite_id,
        EvalSuite.space_id == space_id,
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="评测集不存在")

    tags = _get_tags_for_suite(db, suite_id)
    case_count = db.query(func.count(EvalCase.id)).filter(EvalCase.suite_id == suite_id).scalar() or 0
    return _suite_to_dict(row, tags=tags, case_count=case_count)


def create_suite_service(
    db: Session, space_id: int, user_id: int, data: Dict[str, Any],
) -> Dict[str, Any]:
    """创建评测集。"""
    name = (data.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="评测集名称不能为空")

    folder_id = data.get("folder_id") or _ensure_default_folder(db, space_id)
    if folder_id:
        _validate_folder(db, folder_id, space_id)

    row = EvalSuite(
        space_id=space_id,
        folder_id=folder_id,
        name=name,
        description=data.get("description"),
        version=data.get("version", "v1.0"),
        default_task_source_type=data.get("default_task_source_type", "agent"),
        default_task_source_id=data.get("default_task_source_id"),
        default_task_source_config=data.get("default_task_source_config"),
        default_comparison_method=data.get("default_comparison_method", "exact"),
        default_comparison_config=data.get("default_comparison_config"),
        status=data.get("status", "draft"),
        created_by=user_id,
    )
    db.add(row)
    db.flush()  # 获取 id

    # 处理标签
    tag_ids = data.get("tag_ids", [])
    if tag_ids:
        _sync_tags(db, row.id, tag_ids)

    db.commit()
    db.refresh(row)
    return get_suite_service(db, row.id, space_id)


def update_suite_service(
    db: Session, suite_id: int, space_id: int, data: Dict[str, Any],
) -> Dict[str, Any]:
    """更新评测集。"""
    row = db.query(EvalSuite).filter(
        EvalSuite.id == suite_id,
        EvalSuite.space_id == space_id,
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="评测集不存在")

    if "name" in data and data["name"] is not None:
        name = (data["name"] or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="评测集名称不能为空")
        row.name = name

    if "description" in data and data["description"] is not None:
        row.description = data["description"]

    if "folder_id" in data and data["folder_id"] is not None:
        _validate_folder(db, data["folder_id"], space_id)
        row.folder_id = data["folder_id"]

    if "version" in data and data["version"] is not None:
        row.version = data["version"]

    if "default_task_source_type" in data and data["default_task_source_type"] is not None:
        row.default_task_source_type = data["default_task_source_type"]

    if "default_task_source_id" in data:
        row.default_task_source_id = data["default_task_source_id"]

    if "default_task_source_config" in data:
        row.default_task_source_config = data["default_task_source_config"]

    if "default_comparison_method" in data and data["default_comparison_method"] is not None:
        row.default_comparison_method = data["default_comparison_method"]

    if "default_comparison_config" in data:
        row.default_comparison_config = data["default_comparison_config"]

    if "status" in data and data["status"] is not None:
        row.status = data["status"]

    if "tag_ids" in data and data["tag_ids"] is not None:
        _sync_tags(db, suite_id, data["tag_ids"])

    db.commit()
    db.refresh(row)
    return get_suite_service(db, suite_id, space_id)


def delete_suite_service(db: Session, suite_id: int, space_id: int) -> Dict[str, Any]:
    """删除评测集（级联删除用例、参考答案、输出模板、标签关联）。"""
    row = db.query(EvalSuite).filter(
        EvalSuite.id == suite_id,
        EvalSuite.space_id == space_id,
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="评测集不存在")

    # 检查是否有运行中或待运行的任务
    active_task_count = (
        db.query(EvalTask)
        .filter(
            EvalTask.suite_id == suite_id,
            EvalTask.status.in_(["running", "pending", "starting", "scheduled"]),
        )
        .count()
    )
    if active_task_count > 0:
        raise HTTPException(
            status_code=400,
            detail=f"评测集中有 {active_task_count} 个正在运行或待运行的任务，请先取消或等待完成后再删除",
        )

    # 删除关联数据
    case_ids = [c[0] for c in db.query(EvalCase.id).filter(EvalCase.suite_id == suite_id).all()]
    if case_ids:
        db.query(EvalCaseGroundTruth).filter(EvalCaseGroundTruth.case_id.in_(case_ids)).delete(
            synchronize_session=False
        )
        db.query(EvalCase).filter(EvalCase.id.in_(case_ids)).delete(synchronize_session=False)

    db.query(EvalOutputTemplate).filter(EvalOutputTemplate.suite_id == suite_id).delete()
    db.query(EvalSuiteTag).filter(EvalSuiteTag.suite_id == suite_id).delete()

    db.delete(row)
    db.commit()
    return {"ok": True}


def copy_suite_service(
    db: Session, suite_id: int, space_id: int, user_id: int,
) -> Dict[str, Any]:
    """深拷贝评测集（含用例和参考答案）。"""
    src = db.query(EvalSuite).filter(
        EvalSuite.id == suite_id,
        EvalSuite.space_id == space_id,
    ).first()
    if not src:
        raise HTTPException(status_code=404, detail="评测集不存在")

    # 复制评测集 — 生成唯一名称
    base_name = f"{src.name} (副本)"
    candidate = base_name
    counter = 2
    while (
        db.query(EvalSuite)
        .filter(EvalSuite.space_id == space_id, EvalSuite.name == candidate)
        .first()
    ):
        candidate = f"{base_name}{counter}"
        counter += 1

    new_suite = EvalSuite(
        space_id=src.space_id,
        folder_id=src.folder_id,
        name=candidate,
        description=src.description,
        version=src.version,
        default_task_source_type=src.default_task_source_type,
        default_task_source_id=src.default_task_source_id,
        default_task_source_config=copy.deepcopy(src.default_task_source_config),
        default_comparison_method=src.default_comparison_method,
        default_comparison_config=copy.deepcopy(src.default_comparison_config),
        status="draft",
        created_by=user_id,
    )
    db.add(new_suite)
    db.flush()

    # 复制标签
    src_tags = db.query(EvalSuiteTag).filter(EvalSuiteTag.suite_id == suite_id).all()
    for st in src_tags:
        db.add(EvalSuiteTag(suite_id=new_suite.id, tag_id=st.tag_id))

    # 复制用例
    src_cases = db.query(EvalCase).filter(EvalCase.suite_id == suite_id).all()
    case_id_map: Dict[int, int] = {}  # old_id -> new_id
    for sc in src_cases:
        new_case = EvalCase(
            suite_id=new_suite.id,
            input_prompt=sc.input_prompt,
            input_variables=copy.deepcopy(sc.input_variables),
            expected_output_type=sc.expected_output_type,
            difficulty=sc.difficulty,
            category=sc.category,
            remark=sc.remark,
            sort_order=sc.sort_order,
            is_active=sc.is_active,
        )
        db.add(new_case)
        db.flush()
        case_id_map[sc.id] = new_case.id

    # 复制参考答案
    if case_id_map:
        old_case_ids = list(case_id_map.keys())
        src_gts = (
            db.query(EvalCaseGroundTruth)
            .filter(EvalCaseGroundTruth.case_id.in_(old_case_ids))
            .all()
        )
        for gt in src_gts:
            new_gt = EvalCaseGroundTruth(
                case_id=case_id_map[gt.case_id],
                version=gt.version,
                ground_truth=gt.ground_truth,
                ground_truth_type=gt.ground_truth_type,
                comparison_method=gt.comparison_method,
                comparison_config=copy.deepcopy(gt.comparison_config),
                is_active=gt.is_active,
            )
            db.add(new_gt)

    # 复制输出模板
    src_templates = (
        db.query(EvalOutputTemplate).filter(EvalOutputTemplate.suite_id == suite_id).all()
    )
    for tmpl in src_templates:
        new_tmpl = EvalOutputTemplate(
            suite_id=new_suite.id,
            name=tmpl.name,
            fields=copy.deepcopy(tmpl.fields),
            is_default=tmpl.is_default,
        )
        db.add(new_tmpl)

    db.commit()
    db.refresh(new_suite)
    return get_suite_service(db, new_suite.id, space_id)


def export_suite_service(db: Session, suite_id: int, space_id: int) -> Dict[str, Any]:
    """导出评测集（含用例和参考答案）。"""
    suite = get_suite_service(db, suite_id, space_id)
    if not suite:
        raise HTTPException(status_code=404, detail="评测集不存在")

    cases = (
        db.query(EvalCase)
        .filter(EvalCase.suite_id == suite_id)
        .order_by(EvalCase.sort_order.asc(), EvalCase.id.asc())
        .all()
    )

    case_list = []
    for c in cases:
        gts = (
            db.query(EvalCaseGroundTruth)
            .filter(EvalCaseGroundTruth.case_id == c.id, EvalCaseGroundTruth.is_active.is_(True))
            .all()
        )
        case_list.append({
            "input_prompt": c.input_prompt,
            "input_variables": c.input_variables,
            "expected_output_type": c.expected_output_type,
            "difficulty": c.difficulty,
            "category": c.category,
            "remark": c.remark,
            "ground_truths": [
                {
                    "ground_truth": gt.ground_truth,
                    "ground_truth_type": gt.ground_truth_type,
                    "comparison_method": gt.comparison_method,
                    "comparison_config": gt.comparison_config,
                    "version": gt.version,
                }
                for gt in gts
            ],
        })

    return {
        "suite": suite,
        "cases": case_list,
    }


# ---------------------------------------------------------------------------
# share token
# ---------------------------------------------------------------------------

def get_suite_by_share_token(db: Session, token: str) -> Optional[EvalSuite]:
    """通过分享 token 获取评测集。"""
    if not token or not str(token).strip():
        return None
    t = str(token).strip()
    return db.query(EvalSuite).filter(EvalSuite.share_token == t).first()


def issue_share_token_service(
    db: Session,
    suite_id: int,
    space_id: int,
    *,
    rotate: bool = False,
) -> EvalShareIssueOut:
    """为评测集生成或复用 share_token。"""
    row = db.query(EvalSuite).filter(
        EvalSuite.id == suite_id,
        EvalSuite.space_id == space_id,
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="评测集不存在")
    if rotate or not row.share_token:
        row.share_token = secrets.token_urlsafe(32)
        db.commit()
        db.refresh(row)
    token = (row.share_token or "").strip()
    if not token:
        row.share_token = secrets.token_urlsafe(32)
        db.commit()
        db.refresh(row)
        token = row.share_token or ""
    base = (os.getenv("EVAL_SHARE_PUBLIC_BASE_URL") or "").strip() or None
    return EvalShareIssueOut(token=token, share_public_base_url=base)


def revoke_share_token_service(db: Session, suite_id: int, space_id: int) -> None:
    """撤销评测集的分享 token。"""
    row = db.query(EvalSuite).filter(
        EvalSuite.id == suite_id,
        EvalSuite.space_id == space_id,
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="评测集不存在")
    row.share_token = None
    db.commit()
