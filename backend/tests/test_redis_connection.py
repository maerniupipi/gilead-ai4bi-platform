"""
Redis 连接测试（从环境变量读取，与 config/environments/{APP_ENV}.env 一致）
"""
import os
import sys

import redis

from tests.env_setup import ensure_loaded

ensure_loaded()

REDIS_HOST = (os.getenv("REDIS_HOST") or "").strip()
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_USERNAME = (os.getenv("REDIS_USERNAME") or "").strip() or None
REDIS_PASSWORD = (os.getenv("REDIS_PASSWORD") or "").strip() or None

_loopback = REDIS_HOST.lower() in ("127.0.0.1", "localhost", "::1")
_use_auth_local = (os.getenv("REDIS_USE_AUTH_ON_LOCAL") or "").strip() in ("1", "true", "yes")
if _loopback and not _use_auth_local:
    REDIS_USERNAME = None
    REDIS_PASSWORD = None


def test_redis_connection():
    """Test Redis connection"""
    if not REDIS_HOST:
        print("✗ 未配置 REDIS_HOST，跳过（可在 config/environments/<APP_ENV>.env 中设置）")
        return False
    try:
        print(f"Connecting to Redis at {REDIS_HOST}:{REDIS_PORT}...")

        client = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            username=REDIS_USERNAME,
            password=REDIS_PASSWORD,
            decode_responses=True,
            socket_connect_timeout=10,
        )

        response = client.ping()
        print(f"✓ Redis connection successful! Ping response: {response}")

        test_key = "test:connection"
        test_value = "Hello from BootCamp 2026!"

        client.set(test_key, test_value, ex=60)
        print(f"✓ Set test key: {test_key}")

        retrieved_value = client.get(test_key)
        print(f"✓ Get test key: {test_key} = {retrieved_value}")

        client.delete(test_key)
        print(f"✓ Deleted test key: {test_key}")

        info = client.info()
        print("\nRedis Server Info:")
        print(f"  - Version: {info.get('redis_version', 'N/A')}")
        print(f"  - Mode: {info.get('redis_mode', 'N/A')}")
        print(f"  - Connected clients: {info.get('connected_clients', 'N/A')}")

        client.close()
        print("\n✓ All Redis tests passed successfully!")
        return True

    except redis.ConnectionError as e:
        print(f"✗ Redis connection error: {e}")
        return False
    except redis.AuthenticationError as e:
        print(f"✗ Redis authentication error: {e}")
        return False
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        return False


if __name__ == "__main__":
    success = test_redis_connection()
    sys.exit(0 if success else 1)
