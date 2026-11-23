"""
Elasticsearch 连接测试脚本
配置从数据库读取，需要先在管理中心配置 ES。
"""
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))


def test_elasticsearch_connection():
    """测试 Elasticsearch 连接（配置从数据库读取）"""
    try:
        from app.services.knowledge.es_service import ElasticsearchService
        from app.services.config_resolver import resolve_es_config
        from app.database import SessionLocal

        print("=" * 50)
        print("Elasticsearch 连接测试")
        print("=" * 50)

        db = SessionLocal()
        try:
            es_config = resolve_es_config(db)
        finally:
            db.close()

        host = es_config.get("host")
        user = es_config.get("username", "")

        print(f"\n连接配置（从数据库读取）:")
        print(f"  Host: {host}")
        print(f"  User: {user}")
        print(f"  Password: {'*' * len(es_config.get('password', '')) if es_config.get('password') else 'Not set'}")

        if not host:
            print("\n错误: 未配置 ES 地址，请在管理中心配置")
            return False

        es_svc = ElasticsearchService(es_config)
        es = es_svc.get_client()

        # 测试连接
        print(f"\n正在连接 Elasticsearch...")

        if es.ping():
            print("连接成功!")
        else:
            print("连接失败!")
            return False

        # 获取集群信息
        info = es.info()
        print(f"\n集群信息:")
        print(f"  集群名称: {info.get('cluster_name', 'N/A')}")
        print(f"  Elasticsearch 版本: {info.get('version', {}).get('number', 'N/A')}")
        print(f"  Lucene 版本: {info.get('version', {}).get('lucene_version', 'N/A')}")

        # 获取集群健康状态
        health = es.cluster.health()
        print(f"\n集群健康状态:")
        print(f"  状态: {health.get('status', 'N/A')}")
        print(f"  节点数: {health.get('number_of_nodes', 'N/A')}")
        print(f"  数据节点数: {health.get('number_of_data_nodes', 'N/A')}")

        # 列出所有索引
        indices = es.cat.indices(format="json")
        if indices:
            print(f"\n索引列表 ({len(indices)} 个):")
            for idx in indices[:10]:
                print(f"  - {idx.get('index')} (docs: {idx.get('docs.count', '0')}, size: {idx.get('store.size', 'N/A')})")
            if len(indices) > 10:
                print(f"  ... 还有 {len(indices) - 10} 个索引")
        else:
            print(f"\n暂无索引")

        # 关闭连接
        es.close()
        print("\n连接已关闭")
        print("\n" + "=" * 50)
        print("Elasticsearch 连接测试通过!")
        print("=" * 50)
        return True

    except ImportError as e:
        print(f"\n错误: 无法导入模块")
        print(f"详细错误: {e}")
        return False
    except Exception as e:
        print(f"\n连接失败!")
        print(f"错误信息: {e}")
        return False


if __name__ == "__main__":
    success = test_elasticsearch_connection()
    sys.exit(0 if success else 1)
