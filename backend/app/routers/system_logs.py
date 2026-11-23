from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session
from ..core.database import get_db
from ..core.permissions import require_platform_user
from ..services.system_logs import list_logs

def platform_user(request: Request, db: Session = Depends(get_db)):
    return require_platform_user(request, db)


router = APIRouter(prefix='/api/system-logs', tags=['系统日志'], dependencies=[Depends(platform_user)])


@router.get('')
def logs(page: int = Query(1, ge=1), page_size: int = Query(50,ge=1,le=100),
         level: str | None = None, keyword: str | None = Query(None,max_length=300),
         request_id: str | None = None, conversation_id: str | None = None,
         message_id: str | None = None, trace_id: str | None = None, user_id: str | None = None,
         service: str | None = None, start_at: int | None = None, end_at: int | None = None,
         db: Session = Depends(get_db)):
    return list_logs(db,page=page,page_size=page_size,level=level,keyword=keyword,
        request_id=request_id,conversation_id=conversation_id,message_id=message_id,
        trace_id=trace_id,user_id=user_id,service=service,start_at=start_at,end_at=end_at)
