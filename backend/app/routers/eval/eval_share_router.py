"""
评测中心 · 外链分享（免登录）

仅凭 `eval_suites.share_token` 访问；支持用例的读取、编辑和删除。
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session

from ...core.database import get_db
from ...models.eval import EvalSuite
from ...services.eval.eval_suite_service import (
    get_suite_by_share_token,
    get_suite_service,
)
from ...services.eval.eval_case_service import (
    list_cases_service,
    create_case_service,
    update_case_service,
    delete_case_service,
)
from ...services.eval.eval_task_service import (
    list_tasks_service,
    get_task_service,
    list_sub_tasks_service,
    task_summary_service,
    generate_report_service,
)
from ...schemas.eval import EvalCaseCreate, EvalCaseUpdate
from ...services.eval.eval_comparison_service import (
    list_runs_service,
    get_run_service,
    get_comparison_service,
)

router = APIRouter()


def _suite_from_token(db: Session, token: str) -> EvalSuite:
    """通过分享 token 获取评测集，无效则 404。"""
    m = get_suite_by_share_token(db, token)
    if not m:
        raise HTTPException(status_code=404, detail="分享链接无效或已失效")
    return m


# ---------------------------------------------------------------------------
# 评测集
# ---------------------------------------------------------------------------

@router.get("/{token}/suite")
def share_get_suite(token: str, db: Session = Depends(get_db)):
    """获取评测集详情"""
    suite = _suite_from_token(db, token)
    return get_suite_service(db, suite.id, suite.space_id)


# ---------------------------------------------------------------------------
# 用例
# ---------------------------------------------------------------------------

@router.get("/{token}/cases")
def share_list_cases(
    token: str,
    is_active: Optional[bool] = Query(None),
    difficulty: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """获取用例列表"""
    suite = _suite_from_token(db, token)
    return list_cases_service(
        db, suite.id, {
            "is_active": is_active,
            "difficulty": difficulty,
            "category": category,
            "keyword": keyword,
            "skip": skip,
            "limit": limit,
        }
    )


@router.post("/{token}/cases")
def share_create_case(token: str, data: EvalCaseCreate, db: Session = Depends(get_db)):
    """新增用例"""
    suite = _suite_from_token(db, token)
    return create_case_service(db, suite.id, data.model_dump(exclude_unset=True))


@router.put("/{token}/cases/{case_id}")
def share_update_case(token: str, case_id: int, data: EvalCaseUpdate, db: Session = Depends(get_db)):
    """更新用例"""
    suite = _suite_from_token(db, token)
    return update_case_service(db, case_id, suite.id, data.model_dump(exclude_unset=True))


@router.delete("/{token}/cases/{case_id}")
def share_delete_case(token: str, case_id: int, db: Session = Depends(get_db)):
    """删除用例"""
    suite = _suite_from_token(db, token)
    return delete_case_service(db, case_id, suite.id)


# ---------------------------------------------------------------------------
# 任务
# ---------------------------------------------------------------------------

@router.get("/{token}/tasks")
def share_list_tasks(
    token: str,
    status: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """获取任务列表"""
    suite = _suite_from_token(db, token)
    return list_tasks_service(
        db, suite.space_id, suite.id, status, keyword, skip, limit,
    )


@router.get("/{token}/tasks/{task_id}")
def share_get_task(token: str, task_id: int, db: Session = Depends(get_db)):
    """获取任务详情"""
    suite = _suite_from_token(db, token)
    return get_task_service(db, task_id, suite.space_id)


@router.get("/{token}/tasks/{task_id}/sub-tasks")
def share_list_sub_tasks(token: str, task_id: int, db: Session = Depends(get_db)):
    """获取子任务列表"""
    suite = _suite_from_token(db, token)
    return list_sub_tasks_service(db, task_id, suite.space_id)


@router.get("/{token}/tasks/{task_id}/summary")
def share_task_summary(token: str, task_id: int, db: Session = Depends(get_db)):
    """获取任务统计概览"""
    suite = _suite_from_token(db, token)
    return task_summary_service(db, task_id, suite.space_id)


@router.get("/{token}/tasks/{task_id}/report")
def share_task_report(token: str, task_id: int, db: Session = Depends(get_db)):
    """生成评测报告"""
    suite = _suite_from_token(db, token)
    return generate_report_service(db, task_id, suite.space_id)


# ---------------------------------------------------------------------------
# 运行记录
# ---------------------------------------------------------------------------

@router.get("/{token}/sub-tasks/{sub_task_id}/runs")
def share_list_runs(
    token: str,
    sub_task_id: int,
    status: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """获取运行记录列表"""
    _suite_from_token(db, token)
    return list_runs_service(db, sub_task_id, status, skip, limit)


@router.get("/{token}/runs/{run_id}")
def share_get_run(token: str, run_id: int, db: Session = Depends(get_db)):
    """获取运行记录详情"""
    _suite_from_token(db, token)
    return get_run_service(db, run_id)


@router.get("/{token}/comparisons/{run_id}")
def share_get_comparison(token: str, run_id: int, db: Session = Depends(get_db)):
    """获取对比详情"""
    _suite_from_token(db, token)
    return get_comparison_service(db, run_id)
