"""
测试认证API
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from tests.auth_fixtures import auth_database
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

API_PREFIX = "/api/auth"

@pytest.fixture(autouse=True)
def isolated_auth_storage(auth_database,monkeypatch):
    from app.core.database import get_db
    from app.core import middleware
    monkeypatch.setattr(middleware,'_audit_db_enabled',False)
    def database():
        with auth_database() as db:
            yield db
    previous=app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db]=database
    yield
    if previous is None: app.dependency_overrides.pop(get_db,None)
    else: app.dependency_overrides[get_db]=previous



def test_session_login():
    """测试无邀请码会话登录"""
    response = client.post(f"{API_PREFIX}/login")
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == "SUCCESS"
    assert "token" in data["data"]
    assert len(data["data"]["token"]) > 0


def test_verify_invite_code():
    """测试邀请码验证接口"""
    print("\n=== 测试邀请码验证接口 ===\n")

    # 测试1: 有效的邀请码
    print("1. 测试有效邀请码 (test2024):")
    response = client.post(f"{API_PREFIX}/verify-invite-code", json={"code": "test2024"})
    print(f"   状态码: {response.status_code}")
    data = response.json()
    print(f"   响应: {data}")
    assert response.status_code == 200
    assert data["code"] == "SUCCESS"
    assert data["data"]["valid"] == True
    assert len(data["data"]["token"]) > 0
    print("   ✅ 通过\n")

    # 测试2: 后门邀请码
    print("2. 测试后门邀请码 (shenzhoushuma666):")
    response = client.post(f"{API_PREFIX}/verify-invite-code", json={"code": "shenzhoushuma666"})
    print(f"   状态码: {response.status_code}")
    data = response.json()
    print(f"   响应: {data}")
    assert response.status_code == 200
    assert data["code"] == "SUCCESS"
    assert data["data"]["valid"] == True
    assert len(data["data"]["token"]) > 0
    print("   ✅ 通过\n")

    # 测试3: 无效的邀请码
    print("3. 测试无效邀请码 (invalid123):")
    response = client.post(f"{API_PREFIX}/verify-invite-code", json={"code": "invalid123"})
    print(f"   状态码: {response.status_code}")
    data = response.json()
    print(f"   响应: {data}")
    assert response.status_code == 200
    assert data["code"] == "SUCCESS"
    assert data["data"]["valid"] == False
    print("   ✅ 通过\n")

    # 测试4: 过期的邀请码
    print("4. 测试过期邀请码 (expired):")
    response = client.post(f"{API_PREFIX}/verify-invite-code", json={"code": "expired"})
    print(f"   状态码: {response.status_code}")
    data = response.json()
    print(f"   响应: {data}")
    assert response.status_code == 200
    assert data["code"] == "SUCCESS"
    assert data["data"]["valid"] == False
    print("   ✅ 通过\n")

    # 测试5: 空邀请码
    print("5. 测试空邀请码:")
    response = client.post(f"{API_PREFIX}/verify-invite-code", json={"code": ""})
    print(f"   状态码: {response.status_code}")
    data = response.json()
    print(f"   响应: {data}")
    # 空字符串应该返回验证失败
    assert response.status_code == 200
    print("   ✅ 通过\n")

    print("=== 所有测试通过！ ===")

if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
