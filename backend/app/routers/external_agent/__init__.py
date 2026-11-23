from fastapi import APIRouter

from .router import router as external_agent_router

router = APIRouter(prefix="/api/external", tags=["外部智能体调用"])
router.include_router(external_agent_router)
