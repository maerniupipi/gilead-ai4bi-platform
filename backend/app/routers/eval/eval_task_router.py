from typing import Optional
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from ...core.database import get_db
from ...core.execution import read_database
from ...core.dependencies import get_current_user_id
from ...schemas.eval import EvalTaskCreate, EvalTaskResponse
from ...services.eval import eval_task_service

router = APIRouter(tags=["评测任务"])


@router.get("/spaces/{space_id}/eval/tasks", response_model=dict)
def list_tasks(
    space_id: int,
    suite_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=2000),
    db: Session = Depends(get_db),
):
    """获取任务列表"""
    return eval_task_service.list_tasks_service(db, space_id, suite_id, status, keyword, skip, limit)


@router.post("/spaces/{space_id}/eval/tasks", response_model=EvalTaskResponse)
def create_task(
    space_id: int,
    data: EvalTaskCreate,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """创建评测任务"""
    return eval_task_service.create_task_service(db, space_id, user_id, data.model_dump())


@router.get("/eval/tasks/{task_id}", response_model=dict)
def get_task(task_id: int, space_id: int = Query(...), db: Session = Depends(get_db)):
    """获取任务详情"""
    return eval_task_service.get_task_service(db, task_id, space_id)


@router.put("/eval/tasks/{task_id}", response_model=dict)
def update_task(
    task_id: int,
    data: dict,
    space_id: int = Query(...),
    db: Session = Depends(get_db),
):
    """更新任务（名称和描述）"""
    return eval_task_service.update_task_service(db, task_id, space_id, data)


@router.post("/eval/tasks/{task_id}/start")
async def start_task(task_id: int, space_id: int = Query(...), db: Session = Depends(get_db)):
    """开始执行任务"""
    return await read_database(db, eval_task_service.start_task_service, task_id, space_id)


@router.post("/eval/tasks/{task_id}/pause")
def pause_task(task_id: int, space_id: int = Query(...), db: Session = Depends(get_db)):
    """暂停任务"""
    return eval_task_service.pause_task_service(db, task_id, space_id)


@router.post("/eval/tasks/{task_id}/resume")
async def resume_task(task_id: int, space_id: int = Query(...), db: Session = Depends(get_db)):
    """恢复任务"""
    return await read_database(db, eval_task_service.resume_task_service, task_id, space_id)


@router.post("/eval/tasks/{task_id}/cancel")
def cancel_task(task_id: int, space_id: int = Query(...), db: Session = Depends(get_db)):
    """取消任务"""
    return eval_task_service.cancel_task_service(db, task_id, space_id)


@router.post("/eval/tasks/{task_id}/retry-failed")
async def retry_failed(task_id: int, space_id: int = Query(...), db: Session = Depends(get_db)):
    """重试失败项"""
    return await read_database(db, eval_task_service.retry_failed_service, task_id, space_id)


@router.delete("/eval/tasks/{task_id}")
def delete_task(task_id: int, space_id: int = Query(...), db: Session = Depends(get_db)):
    """删除任务"""
    return eval_task_service.delete_task_service(db, task_id, space_id)


@router.get("/eval/tasks/stats")
def task_stats(
    space_id: int = Query(...),
    suite_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    """获取任务统计概览（按状态分组）"""
    return eval_task_service.task_stats_service(db, space_id, suite_id)


@router.get("/eval/tasks/{task_id}/progress")
def task_progress(task_id: int, request: Request, space_id: int = Query(...)):
    """任务进度 SSE 推送"""
    return eval_task_service.task_progress_service(task_id, space_id, request)


@router.get("/eval/tasks/{task_id}/sub-tasks")
def list_sub_tasks(task_id: int, space_id: int = Query(...), db: Session = Depends(get_db)):
    """获取子任务列表"""
    return eval_task_service.list_sub_tasks_service(db, task_id, space_id)


@router.get("/eval/tasks/{task_id}/summary")
def task_summary(task_id: int, space_id: int = Query(...), db: Session = Depends(get_db)):
    """获取任务统计概览"""
    return eval_task_service.task_summary_service(db, task_id, space_id)


@router.get("/eval/tasks/{task_id}/export")
def export_results(task_id: int, space_id: int = Query(...), db: Session = Depends(get_db)):
    """导出评测结果"""
    return eval_task_service.export_results_service(db, task_id, space_id)


@router.post("/eval/tasks/{task_id}/archive-failed")
def archive_failed_cases(
    task_id: int,
    space_id: int = Query(...),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """将失败用例归档为新的评测集"""
    return eval_task_service.archive_failed_cases_service(db, task_id, space_id, user_id)


@router.get("/eval/tasks/{task_id}/report")
def generate_report(task_id: int, space_id: int = Query(...), db: Session = Depends(get_db)):
    """生成评测报告"""
    return eval_task_service.generate_report_service(db, task_id, space_id)
