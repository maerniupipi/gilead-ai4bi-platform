#!/usr/bin/env python3
"""
最简单的数据库连接测试脚本
"""
import os

import mysql.connector
from mysql.connector import Error

from tests.env_setup import ensure_loaded

ensure_loaded()


def test_connection():
    print("=== 最简化数据库连接测试 ===")
    user = os.getenv("DB_TEST_USER")
    password = os.getenv("DB_TEST_PASSWORD")
    host = os.getenv("DB_TEST_HOST")
    port = int(os.getenv("DB_TEST_PORT", "3306"))

    if not all([user, password, host]):
        print("❌ 请先设置 DB_TEST_USER / DB_TEST_PASSWORD / DB_TEST_HOST")
        return False
    
    try:
        connection = mysql.connector.connect(
            user=user,
            password=password,
            host=host,
            port=port,
            connect_timeout=10
        )
        
        print("✅ 成功连接到MySQL服务器!")
        print(f"服务器版本: {connection.get_server_info()}")
        
        # 查看所有可用数据库
        with connection.cursor() as cursor:
            cursor.execute("SHOW DATABASES;")
            databases = cursor.fetchall()
            print("\n可用数据库列表:")
            for db in databases:
                print(f"- {db[0]}")
        
        connection.close()
        return True
        
    except Error as e:
        print(f"❌ 连接失败: {e}")
        return False
    except Exception as e:
        print(f"❌ 其他错误: {e}")
        return False

if __name__ == "__main__":
    success = test_connection()
    exit(0 if success else 1)
