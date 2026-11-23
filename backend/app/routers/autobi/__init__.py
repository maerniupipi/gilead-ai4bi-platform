from fastapi import APIRouter

from .router import router as autobi_inner
from .share_router import router as autobi_share_inner

# autobi_inner 已带 prefix="/api/autobi"，直接导出即可
# share_router 无 prefix，在此挂载
autobi_inner.include_router(
    autobi_share_inner,
    prefix="/share",
    tags=["AutoBI 实验室·分享"],
)

router = autobi_inner
