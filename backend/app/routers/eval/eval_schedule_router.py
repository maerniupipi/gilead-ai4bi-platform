from typing import Optional, List
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ...core.database import get_db
from ...core.dependencies import get_current_user_id
from ...schemas.eval import EvalScheduleCreate, EvalScheduleUpdate, EvalScheduleResponse
from ...services.eval import eval_schedule_service

router = APIRouter(tags=["定时任务"])


@router.get("/spaces/{space_id}/eval/schedules", response_model=List[EvalScheduleResponse])
def list_schedules(
    space_id: int,
    suite_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    """获取定时任务列表"""
    return eval_schedule_service.list_schedules_service(db, space_id, suite_id)


@router.post("/spaces/{space_id}/eval/schedules", response_model=EvalScheduleResponse)
def create_schedule(
    space_id: int,
    data: EvalScheduleCreate,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """创建定时任务"""
    return eval_schedule_service.create_schedule_service(db, space_id, user_id, data.model_dump())


@router.put("/eval/schedules/{schedule_id}", response_model=EvalScheduleResponse)
def update_schedule(schedule_id: int, data: EvalScheduleUpdate, space_id: int = Query(...), db: Session = Depends(get_db)):
    """更新定时任务"""
    return eval_schedule_service.update_schedule_service(db, schedule_id, space_id, data.model_dump(exclude_unset=True))


@router.delete("/eval/schedules/{schedule_id}")
def delete_schedule(schedule_id: int, space_id: int = Query(...), db: Session = Depends(get_db)):
    """删除定时任务"""
    return eval_schedule_service.delete_schedule_service(db, schedule_id, space_id)


@router.post("/eval/schedules/{schedule_id}/trigger")
def trigger_schedule(schedule_id: int, space_id: int = Query(...), db: Session = Depends(get_db)):
    """手动触发执行"""
    return eval_schedule_service.trigger_schedule_service(db, schedule_id, space_id)
