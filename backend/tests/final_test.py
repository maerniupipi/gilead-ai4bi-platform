#!/usr/bin/env python3
"""
最终数据库连接测试脚本
"""
import os
from urllib.parse import unquote_plus, urlparse

import mysql.connector
from mysql.connector import Error

from tests.env_setup import ensure_loaded

ensure_loaded()


def parse_mysql_url(url: str) -> dict | None:
    parsed = urlparse(url)
    if parsed.scheme != "mysql+mysqlconnector":
        return None
    return {
        "user": unquote_plus(parsed.username or ""),
        "password": unquote_plus(parsed.password or ""),
        "host": parsed.hostname or "",
        "port": parsed.port or 3306,
        "database": (parsed.path or "/").lstrip("/"),
    }


def test_connection():
    print("=== 最终数据库连接测试 ===")
    
    try:
        # 直接使用环境变量中的数据库URL
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            print("❌ 错误: 未设置DATABASE_URL环境变量")
            return False

        print("数据库URL: <已从环境变量读取，隐藏敏感信息>")
        
        db_config = parse_mysql_url(database_url)
        if not db_config:
            print("❌ 错误: DATABASE_URL 不是 mysql+mysqlconnector:// 格式")
            return False
        
        print(f"\n连接参数:")
        print(f"  用户: {db_config['user']}")
        print(f"  密码: {'*' * len(db_config['password']) if db_config['password'] else '未设置'}")
        print(f"  主机: {db_config['host']}:{db_config['port']}")
        print(f"  数据库: {db_config['database']}")
        
        connection = mysql.connector.connect(
            user=db_config["user"],
            password=db_config["password"],
            host=db_config["host"],
            port=db_config["port"],
            database=db_config["database"],
            connect_timeout=10
        )
        
        print("✅ 成功连接到MySQL数据库!")
        print(f"服务器版本: {connection.get_server_info()}")
        
        # 测试执行SQL
        with connection.cursor() as cursor:
            # 创建表（如果不存在）
            print("\n创建表结构...")
            
            # 创建知识接入表
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS knowledge_access (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(255) NOT NULL COMMENT '知识接入名称',
                description TEXT COMMENT '描述',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                is_deleted BOOLEAN DEFAULT FALSE COMMENT '是否删除'
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='知识接入表';
            """)
            print("  ✅ 创建knowledge_access表成功")
            
            # 创建表结构表
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS table_structure (
                id INT AUTO_INCREMENT PRIMARY KEY,
                knowledge_access_id INT NOT NULL COMMENT '知识接入ID',
                table_name VARCHAR(255) NOT NULL COMMENT '表名',
                table_alias VARCHAR(255) COMMENT '表中文名',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                FOREIGN KEY (knowledge_access_id) REFERENCES knowledge_access(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='表结构表';
            """)
            print("  ✅ 创建table_structure表成功")
            
            # 创建表字段表
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS table_field (
                id INT AUTO_INCREMENT PRIMARY KEY,
                table_structure_id INT NOT NULL COMMENT '表结构ID',
                field_name VARCHAR(255) NOT NULL COMMENT '字段名',
                field_alias VARCHAR(255) COMMENT '字段中文名',
                field_type VARCHAR(50) NOT NULL COMMENT '字段类型',
                is_enabled BOOLEAN DEFAULT TRUE COMMENT '是否生效',
                is_vectorized BOOLEAN DEFAULT FALSE COMMENT '是否向量化',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                FOREIGN KEY (table_structure_id) REFERENCES table_structure(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='表字段表';
            """)
            print("  ✅ 创建table_field表成功")
            
            # 创建知识词条表
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS knowledge_term (
                id INT AUTO_INCREMENT PRIMARY KEY,
                knowledge_access_id INT NOT NULL COMMENT '知识接入ID',
                term_name VARCHAR(255) NOT NULL COMMENT '词条名称',
                term_value TEXT NOT NULL COMMENT '词条值',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                is_deleted BOOLEAN DEFAULT FALSE COMMENT '是否删除',
                FOREIGN KEY (knowledge_access_id) REFERENCES knowledge_access(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='知识词条表';
            """)
            print("  ✅ 创建knowledge_term表成功")
            
            # 创建样例库表
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS sample_library (
                id INT AUTO_INCREMENT PRIMARY KEY,
                knowledge_access_id INT NOT NULL COMMENT '知识接入ID',
                sample_name VARCHAR(255) NOT NULL COMMENT '样例名称',
                sql_content TEXT NOT NULL COMMENT 'SQL内容',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                is_deleted BOOLEAN DEFAULT FALSE COMMENT '是否删除',
                FOREIGN KEY (knowledge_access_id) REFERENCES knowledge_access(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='样例库表';
            """)
            print("  ✅ 创建sample_library表成功")
            
            # 查看创建的表
            cursor.execute("SHOW TABLES;")
            tables = cursor.fetchall()
            print("\n所有创建的表:")
            for table in tables:
                print(f"  - {table[0]}")
            
        connection.commit()
        connection.close()
        
        print("\n✅ 所有表结构创建成功! 数据库配置完成!")
        return True
        
    except Error as e:
        print(f"\n❌ MySQL错误: {e}")
        print("\n解决建议:")
        print("1. 检查用户名和密码是否正确")
        print("2. 确保 DATABASE_URL 中指定的数据库存在")
        print("3. 检查IP是否已添加到数据库白名单")
        print("4. 验证网络连接是否正常")
        return False
    except Exception as e:
        print(f"\n❌ 其他错误: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_connection()
    exit(0 if success else 1)
