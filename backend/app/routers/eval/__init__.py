"""
评测中心路由 - 汇总所有评测子路由
"""
from fastapi import APIRouter
from .eval_folder_router import router as folder_router
from .eval_suite_router import router as suite_router
from .eval_case_router import router as case_router
from .eval_ground_truth_router import router as ground_truth_router
from .eval_output_template_router import router as template_router
from .eval_tag_router import router as tag_router
from .eval_task_router import router as task_router
from .eval_run_router import router as run_router
from .eval_schedule_router import router as schedule_router
from .eval_comparison_template_router import router as comparison_template_router
from .eval_share_router import router as eval_share_router
from .eval_config_router import router as config_router

router = APIRouter(prefix="/api")
router.include_router(folder_router)
router.include_router(suite_router)
router.include_router(case_router)
router.include_router(ground_truth_router)
router.include_router(template_router)
router.include_router(tag_router)
router.include_router(task_router)
router.include_router(run_router)
router.include_router(schedule_router)
router.include_router(comparison_template_router)
router.include_router(eval_share_router, prefix="/eval/share", tags=["评测中心·分享"])
router.include_router(config_router)
