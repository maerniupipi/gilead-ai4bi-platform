#!/usr/bin/env python3
"""
测试数据库连接和表创建的脚本
"""
import os
import sys

from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError

from tests.env_setup import ensure_loaded

ensure_loaded()

def test_connection():
    """测试数据库连接"""
    try:
        # 获取数据库连接URL
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            print("错误: 未设置DATABASE_URL环境变量")
            return False

        print(f"正在连接数据库: {database_url}")
        
        # 创建数据库引擎
        engine = create_engine(database_url)
        
        # 测试连接
        with engine.connect() as connection:
            print("✅ 数据库连接成功!")
            
            # 测试创建app schema（如果不存在）
            try:
                connection.execute("CREATE SCHEMA IF NOT EXISTS app;")
                connection.execute("USE app;")
                print("✅ 成功切换到app schema")
                return True
            except Exception as e:
                print(f"❌ 创建或切换app schema失败: {e}")
                return False
                
    except OperationalError as e:
        print(f"❌ 数据库连接失败: {e}")
        print("请检查以下事项:")
        print("1. 数据库服务器是否可访问")
        print("2. 用户名和密码是否正确")
        print("3. 数据库名称是否存在")
        print("4. 网络连接是否正常")
        return False
    except Exception as e:
        print(f"❌ 发生其他错误: {e}")
        return False

if __name__ == "__main__":
    print("=== Chat-BI 数据库连接测试 ===")
    success = test_connection()
    sys.exit(0 if success else 1)
