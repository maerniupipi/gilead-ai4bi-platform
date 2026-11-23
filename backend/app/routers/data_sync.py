"""Synchronization configuration uses the normal platform login identity."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..routers.chatbi.admin import key_admin
from ..schemas.data_sync import SyncTaskUpdate
from ..services.data_sync import service

router = APIRouter(prefix="/api/chatbi/data-sync", tags=["数据同步"], dependencies=[Depends(key_admin)])


@router.get("/tasks")
def tasks(db: Session = Depends(get_db)):
    return service.list_tasks(db)


@router.put("/tasks/{task_id}")
def update_task(task_id: str, body: SyncTaskUpdate, db: Session = Depends(get_db)):
    return service.update_task(db, task_id, body)


@router.post("/tasks/{task_id}/run", status_code=202)
def run(task_id: str, user_id: int = Depends(key_admin), db: Session = Depends(get_db)):
    return service.enqueue(db, task_id, requested_by=user_id)


@router.get("/runs")
def runs(task_id: str | None = None, status: str | None = None,
         offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)):
    return service.list_runs(db, task_id, status, offset, limit)


@router.get("/runs/{run_id}")
def detail(run_id: str, after_event_id: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=200),
           db: Session = Depends(get_db)):
    return service.run_detail(db, run_id, after_event_id, limit)
