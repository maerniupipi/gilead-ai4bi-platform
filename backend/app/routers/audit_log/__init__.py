"""
审计日志路由包
"""
from fastapi import APIRouter
from .router import router as audit_log_router

router = APIRouter(prefix="/api")
router.include_router(audit_log_router, prefix="/audit-logs", tags=["审计日志"])
