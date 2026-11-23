"""
Embedding 模型测试脚本
配置从数据库读取，需要先在管理中心配置向量模型。
"""
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))


def test_embedding():
    """测试 Embedding 模型（配置从数据库读取）"""
    try:
        from app.services.knowledge.embedding_service import EmbeddingService
        from app.services.config_resolver import resolve_embedding_config
        from app.database import SessionLocal

        print("=" * 60)
        print("Embedding 模型测试")
        print("=" * 60)

        db = SessionLocal()
        try:
            embedding_config = resolve_embedding_config(db)
        finally:
            db.close()

        print(f"\n配置信息（从数据库读取）:")
        print(f"  Provider: {embedding_config.get('provider', 'N/A')}")
        print(f"  Model: {embedding_config.get('model', 'N/A')}")
        print(f"  Base URL: {embedding_config.get('base_url', 'N/A')}")
        api_key = embedding_config.get('api_key', '')
        print(f"  API Key: {'*' * len(api_key) if api_key else 'Not set'}")

        embedding_svc = EmbeddingService(embedding_config)

        # 测试文本
        test_texts = [
            "这是一个测试文本",
            "Milvus 是一个向量数据库"
        ]

        print(f"\n测试文本:")
        for i, text in enumerate(test_texts, 1):
            print(f"  {i}. {text}")

        # 调用 embedding API
        print(f"\n正在调用 Embedding API...")
        print(f"  Endpoint: {embedding_svc.endpoint}")

        embeddings = embedding_svc.get_embeddings(test_texts)

        print("API 调用成功!")
        print(f"\nEmbedding 结果:")
        print(f"  返回数量: {len(embeddings)}")

        for i, vector in enumerate(embeddings):
            vector_dim = len(vector)
            preview = vector[:5] + ["..."] + vector[-5:] if vector_dim > 10 else vector
            print(f"\n  文本 {i+1}:")
            print(f"    向量维度: {vector_dim}")
            print(f"    向量预览: {preview}")

        expected_dim = embedding_svc.dimension
        actual_dim = len(embeddings[0]) if embeddings else 0

        if actual_dim == expected_dim:
            print(f"\n向量维度验证通过: {actual_dim}")
        else:
            print(f"\n向量维度不匹配: 期望 {expected_dim}, 实际 {actual_dim}")

        print("\n" + "=" * 60)
        print("Embedding 模型测试通过!")
        print("=" * 60)
        return True

    except ImportError as e:
        print(f"\n错误: 无法导入模块")
        print(f"详细错误: {e}")
        return False
    except Exception as e:
        print(f"\n测试失败!")
        print(f"错误信息: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_embedding()
    sys.exit(0 if success else 1)
