"""
简单测试认证功能（不依赖FastAPI）
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.auth_fixtures import auth_database
from app.services.auth.service import AuthService

def test_auth_service(auth_database):
    """测试认证服务"""
    print("\n=== 测试认证服务 ===\n")

    db = auth_database()
    try:
        service = AuthService(db)

        # 测试1: 有效邀请码
        print("1. 测试有效邀请码 (test2024):")
        valid, token = service.verify_invite_code("test2024")
        print(f"   有效: {valid}")
        print(f"   Token: {token[:20]}..." if token else "   Token: None")
        assert valid == True
        assert len(token) > 0
        print("   ✅ 通过\n")

        # 测试2: 后门邀请码
        print("2. 测试后门邀请码 (shenzhoushuma666):")
        valid, token = service.verify_invite_code("shenzhoushuma666")
        print(f"   有效: {valid}")
        print(f"   Token: {token[:20]}..." if token else "   Token: None")
        assert valid == True
        assert len(token) > 0
        print("   ✅ 通过\n")

        # 测试3: 无效邀请码
        print("3. 测试无效邀请码 (invalid123):")
        valid, token = service.verify_invite_code("invalid123")
        print(f"   有效: {valid}")
        print(f"   Token: {token}")
        assert valid == False
        assert token == ""
        print("   ✅ 通过\n")

        # 测试4: 过期邀请码
        print("4. 测试过期邀请码 (expired):")
        valid, token = service.verify_invite_code("expired")
        print(f"   有效: {valid}")
        print(f"   Token: {token}")
        assert valid == False
        assert token == ""
        print("   ✅ 通过\n")

        print("=== 所有测试通过！ ===")

    finally:
        db.close()

if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__]))
