"""
knowledge 大类路由聚合
- 所有"知识体系"相关的子域路由在此汇总
- main.py 只需 include 本文件导出的 router
"""
from fastapi import APIRouter

from .knowledge_base import router as knowledge_base_router
from .knowledge_access import router as knowledge_access_router
from .table_structure import router as table_structure_router
from .knowledge_term import router as knowledge_term_router
from .sample_library import router as sample_library_router
from .data_source import router as data_source_router
from .autobi_atomic import router as autobi_atomic_router

router = APIRouter(prefix="/api")
router.include_router(knowledge_base_router)
router.include_router(knowledge_access_router)
router.include_router(table_structure_router)
router.include_router(knowledge_term_router)
router.include_router(sample_library_router)
router.include_router(data_source_router)
router.include_router(autobi_atomic_router)
