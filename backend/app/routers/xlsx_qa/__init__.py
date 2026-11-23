"""XLSX 表格智能问答路由聚合。"""
from fastapi import APIRouter

from .router import router as xlsx_qa_inner
from .share_router import router as xlsx_qa_share_inner

router = APIRouter(prefix="/api")
router.include_router(xlsx_qa_inner, prefix="/xlsx-qa", tags=["XLSX 表格智能问答"])
router.include_router(
    xlsx_qa_share_inner,
    prefix="/xlsx-qa/share",
    tags=["XLSX 表格智能问答·分享"],
)
