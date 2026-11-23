#!/usr/bin/env python3
"""
简单的数据库连接测试脚本
"""
import os
import sys
import time
import traceback

import mysql.connector
from mysql.connector import Error

from tests.env_setup import ensure_loaded

ensure_loaded()

# 设置超时时间（秒）
TIMEOUT = 10

def parse_db_url(url):
    """解析数据库连接URL"""
    if not url.startswith("mysql+mysqlconnector://"):
        return None
    
    # 移除协议前缀
    url = url[23:]
    
    # 分割用户密码和主机数据库部分
    if "@" not in url:
        return None
    
    auth_part, host_part = url.split("@", 1)
    
    # 分割用户名和密码
    if ":" in auth_part:
        user, password = auth_part.split(":", 1)
    else:
        user = auth_part
        password = ""
    
    # 分割主机端口和数据库部分
    if "/" not in host_part:
        return None
    
    host_port, db_part = host_part.split("/", 1)
    
    # 分割主机和端口
    if ":" in host_port:
        host, port = host_port.split(":", 1)
        port = int(port)
    else:
        host = host_port
        port = 3306
    
    # 处理数据库名称和查询参数
    if "?" in db_part:
        db_name, _ = db_part.split("?", 1)
    else:
        db_name = db_part
    
    return {
        "user": user,
        "password": password,
        "host": host,
        "port": port,
        "database": db_name
    }

def test_connection():
    """测试数据库连接"""
    print("=== 简单数据库连接测试 ===")
    
    try:
        # 获取数据库连接URL
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            print("❌ 错误: 未设置DATABASE_URL环境变量")
            return False

        print(f"\n1. 解析数据库URL: {database_url}")
        
        # 解析URL
        db_config = parse_db_url(database_url)
        if not db_config:
            print("❌ 错误: 无法解析数据库URL格式")
            return False
        
        print(f"   ✅ 用户: {db_config['user']}")
        print(f"   ✅ 主机: {db_config['host']}")
        print(f"   ✅ 端口: {db_config['port']}")
        print(f"   ✅ 数据库: {db_config['database']}")
        
        print(f"\n2. 尝试连接数据库（超时: {TIMEOUT}秒）...")
        start_time = time.time()
        
        # 尝试连接数据库
        connection = mysql.connector.connect(
            user=db_config['user'],
            password=db_config['password'],
            host=db_config['host'],
            port=db_config['port'],
            database=db_config['database'],
            connection_timeout=TIMEOUT
        )
        
        elapsed_time = time.time() - start_time
        print(f"   ✅ 连接成功! 耗时: {elapsed_time:.2f}秒")
        
        # 测试创建app schema（如果不存在）
        print("\n3. 创建或切换到app schema...")
        with connection.cursor() as cursor:
            # 创建app schema（如果不存在）
            cursor.execute("CREATE SCHEMA IF NOT EXISTS app")
            print("   ✅ 创建app schema成功")
            
            # 切换到app schema
            cursor.execute("USE app")
            print("   ✅ 切换到app schema成功")
            
            # 测试执行SQL查询
            cursor.execute("SELECT CURRENT_DATABASE()")
            result = cursor.fetchone()
            print(f"   ✅ 当前数据库: {result[0]}")
        
        # 关闭连接
        connection.close()
        print("\n✅ 所有测试通过! 数据库配置正确")
        return True
        
    except Error as e:
        print(f"\n❌ MySQL错误: {e}")
        print("\n可能的原因:")
        print("1. 数据库服务器地址或端口错误")
        print("2. 用户名或密码不正确")
        print("3. 数据库名称不存在")
        print("4. 网络连接超时")
        print("5. 数据库服务器防火墙阻止连接")
        print("\n请检查 config/environments/<APP_ENV>.env 中的 DATABASE_URL 是否正确")
        return False
    except Exception as e:
        print(f"\n❌ 其他错误: {e}")
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_connection()
    sys.exit(0 if success else 1)
