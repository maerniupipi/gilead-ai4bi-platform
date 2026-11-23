from fastapi import APIRouter

from .router import router as agent_apps_inner

router = APIRouter(prefix="/api")
router.include_router(agent_apps_inner, prefix="/agent_apps", tags=["智能体平台"])
