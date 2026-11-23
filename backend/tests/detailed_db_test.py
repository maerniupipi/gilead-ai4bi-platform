#!/usr/bin/env python3
"""
详细数据库连接测试脚本
"""
import os
import sys
from urllib.parse import unquote_plus

import mysql.connector
from mysql.connector import Error

from tests.env_setup import ensure_loaded

ensure_loaded()

# 解析数据库URL函数
def parse_db_url(url):
    if not url.startswith("mysql+mysqlconnector://"):
        return None
    url = url[23:]
    if "@" not in url:
        return None
    auth_part, host_part = url.split("@", 1)
    if ":" in auth_part:
        user, password = auth_part.split(":", 1)
    else:
        user = auth_part
        password = ""
    if ":" in host_part:
        host_port, rest = host_part.split(":", 1)
        if "/" in rest:
            port, db_part = rest.split("/", 1)
        else:
            port = rest
            db_part = ""
    else:
        host_port = host_part
        if "/" in host_port:
            host_port, db_part = host_port.split("/", 1)
        else:
            db_part = ""
        port = "3306"
    host = host_port
    port = int(port)
    if "?" in db_part:
        db_name, _ = db_part.split("?", 1)
    else:
        db_name = db_part
    return {
        "user": unquote_plus(user),
        "password": unquote_plus(password),
        "host": host,
        "port": port,
        "database": db_name
    }

def test_connection():
    print("=== 详细数据库连接测试 ===")
    
    try:
        # 获取数据库连接URL
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            print("❌ 错误: 未设置DATABASE_URL环境变量")
            return False

        print("1. 数据库URL: <已从环境变量读取，隐藏敏感信息>")
        
        # 解析URL
        db_config = parse_db_url(database_url)
        if not db_config:
            print("❌ 错误: 无法解析数据库URL格式")
            return False
        
        # 1. 先测试连接到MySQL服务器（不指定数据库）
        print(f"\n2. 测试连接到MySQL服务器...")
        print(f"   主机: {db_config['host']}:{db_config['port']}")
        print(f"   用户: {db_config['user']}")
        
        server_config = {
            "user": db_config['user'],
            "password": db_config['password'],
            "host": db_config['host'],
            "port": db_config['port'],
            "connect_timeout": 10
        }
        
        with mysql.connector.connect(**server_config) as connection:
            print("   ✅ 成功连接到MySQL服务器!")
            
            # 2. 查看所有可用数据库
            print("\n3. 查看可用数据库列表:")
            with connection.cursor() as cursor:
                cursor.execute("SHOW DATABASES;")
                databases = cursor.fetchall()
                for db in databases:
                    print(f"   - {db[0]}")
            
            # 3. 测试访问chatbi数据库
            print(f"\n4. 测试访问'{db_config['database']}'数据库...")
            try:
                connection.database = db_config['database']
                print(f"   ✅ 成功访问'{db_config['database']}'数据库!")
                
                # 4. 查看当前数据库
                with connection.cursor() as cursor:
                    cursor.execute("SELECT DATABASE();")
                    current_db = cursor.fetchone()
                    print(f"   当前数据库: {current_db[0]}")
                    
                # 5. 创建或切换到app schema
                print("\n5. 创建或切换到app schema...")
                with connection.cursor() as cursor:
                    cursor.execute("CREATE SCHEMA IF NOT EXISTS app;")
                    print("   ✅ 创建app schema成功")
                    
                    cursor.execute("USE app;")
                    print("   ✅ 切换到app schema成功")
                    
                    # 6. 查看当前schema
                    cursor.execute("SELECT DATABASE();")
                    current_db = cursor.fetchone()
                    print(f"   当前schema: {current_db[0]}")
                    
                print("\n✅ 所有测试通过! 数据库配置正确")
                return True
                
            except Error as e:
                print(f"   ❌ 访问数据库失败: {e}")
                print("\n解决建议:")
                print("1. 确保用户具有访问该数据库的权限")
                print("2. 确保数据库名称正确")
                print("3. 在MySQL中为当前用户授权访问目标数据库")
                print("4. 然后执行: FLUSH PRIVILEGES;")
                return False
                
    except Error as e:
        print(f"\n❌ MySQL服务器连接失败: {e}")
        print("\n可能的原因:")
        print("1. 白名单配置是否包含当前机器出口 IP")
        print("2. 用户名或密码是否正确")
        print("3. 数据库服务器是否正常运行")
        return False
    except Exception as e:
        print(f"\n❌ 其他错误: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_connection()
    sys.exit(0 if success else 1)
