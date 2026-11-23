"""
认证相关的路由
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ...core.database import get_db
from ...services.auth import AuthService
from ...schemas.auth import (
    InviteCodeVerifyRequest,
    InviteCodeVerifyResponse,
    SessionLoginResponse,
)

router = APIRouter(prefix="/api/auth", tags=["认证"])


@router.post("/login", response_model=SessionLoginResponse)
def session_login(db: Session = Depends(get_db)):
    """会话登录：无需邀请码，签发与历史流程兼容的 token"""
    service = AuthService(db)
    token = service.create_session_token()
    return SessionLoginResponse(token=token)


@router.post("/verify-invite-code", response_model=InviteCodeVerifyResponse)
def verify_invite_code(
    request: InviteCodeVerifyRequest,
    db: Session = Depends(get_db)
):
    """验证邀请码"""
    service = AuthService(db)
    valid, token = service.verify_invite_code(request.code)
    return InviteCodeVerifyResponse(valid=valid, token=token)
