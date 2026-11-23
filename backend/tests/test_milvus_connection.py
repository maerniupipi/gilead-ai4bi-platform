"""
Milvus 向量数据库连接测试脚本
"""
import os
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from tests.env_setup import ensure_loaded

ensure_loaded()

def test_milvus_connection():
    """测试 Milvus 连接"""
    try:
        from pymilvus import connections, db, utility
        
        # 获取环境变量
        host = os.getenv("MILVUS_HOST")
        port = os.getenv("MILVUS_PORT", "19530")
        user = os.getenv("MILVUS_USER")
        password = os.getenv("MILVUS_PASSWORD")
        db_name = os.getenv("MILVUS_DB_NAME", "default")
        
        print("=" * 50)
        print("Milvus 连接测试")
        print("=" * 50)
        print(f"\n连接配置:")
        print(f"  Host: {host}")
        print(f"  Port: {port}")
        print(f"  User: {user}")
        print(f"  Database: {db_name}")
        print(f"  Password: {'*' * len(password) if password else 'Not set'}")
        
        if not host:
            print("\n错误: MILVUS_HOST 环境变量未设置")
            return False
            
        # 建立连接
        print(f"\n正在连接 Milvus...")
        connections.connect(
            alias="default",
            host=host,
            port=port,
            user=user,
            password=password
        )
        
        print("✓ 连接成功!")
        
        # 获取服务器版本
        server_version = utility.get_server_version()
        print(f"\nMilvus 服务器版本: {server_version}")
        
        # 列出所有数据库
        print(f"\n数据库列表:")
        databases = db.list_database()
        for database in databases:
            marker = " <-- 当前" if database == db_name else ""
            print(f"  - {database}{marker}")
        
        # 切换到指定数据库
        if db_name in databases:
            print(f"\n✓ 数据库 '{db_name}' 存在")
            db.using_database(db_name)
            
            # 列出集合
            collections = utility.list_collections()
            if collections:
                print(f"\n集合列表 (Collections):")
                for collection in collections:
                    print(f"  - {collection}")
            else:
                print(f"\n数据库 '{db_name}' 中暂无集合")
        else:
            print(f"\n✗ 数据库 '{db_name}' 不存在")
        
        # 断开连接
        connections.disconnect("default")
        print("\n✓ 连接已断开")
        print("\n" + "=" * 50)
        print("Milvus 连接测试通过!")
        print("=" * 50)
        return True
        
    except ImportError as e:
        print(f"\n错误: 无法导入 pymilvus 模块")
        print(f"请安装依赖: pip install pymilvus==2.5.0")
        print(f"详细错误: {e}")
        return False
    except Exception as e:
        print(f"\n✗ 连接失败!")
        print(f"错误信息: {e}")
        return False


if __name__ == "__main__":
    success = test_milvus_connection()
    sys.exit(0 if success else 1)
