"""
认证相关的数据访问层
"""
from sqlalchemy.orm import Session
from datetime import datetime
from ...models.invite_code import InviteCode


class AuthRepository:
    """认证数据访问类"""

    def __init__(self, db: Session):
        self.db = db

    def get_invite_code_by_code(self, code: str) -> InviteCode:
        """根据邀请码查询"""
        return self.db.query(InviteCode).filter(
            InviteCode.code == code,
            InviteCode.is_deleted == False
        ).first()

    def create_invite_code(self, code: str, expires_at: datetime, is_active: bool = True) -> InviteCode:
        """创建邀请码"""
        invite_code = InviteCode(
            code=code,
            expires_at=expires_at,
            is_active=is_active
        )
        self.db.add(invite_code)
        self.db.commit()
        self.db.refresh(invite_code)
        return invite_code
