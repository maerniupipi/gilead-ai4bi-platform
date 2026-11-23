"""
向量库配置与通用向量操作服务
"""
import logging
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ...models import KnowledgeBase
from ...repositories.vector_store import VectorStoreRepository
from ...schemas.vector_store import (
    VectorStoreCreate,
    VectorStoreResponse,
    VectorStoreTestRequest,
    VectorStoreTestResponse,
    VectorStoreUpdate,
)
from .providers import get_vector_store_provider
from ..knowledge.config_overrides import resolve_knowledge_base_config

logger = logging.getLogger(__name__)


class VectorStoreService:
    @staticmethod
    def get_all(db: Session, skip: int = 0, limit: int = 100, space_id: int = None) -> List[VectorStoreResponse]:
        return [VectorStoreResponse.model_validate(x) for x in VectorStoreRepository.get_all(db, skip, limit, space_id)]

    @staticmethod
    def get_active(db: Session, space_id: int = None):
        store = VectorStoreRepository.get_active(db, space_id)
        return VectorStoreResponse.model_validate(store) if store else None

    @staticmethod
    def create(db: Session, store: VectorStoreCreate, space_id: int) -> VectorStoreResponse:
        return VectorStoreResponse.model_validate(VectorStoreRepository.create(db, store, space_id))

    @staticmethod
    def update(db: Session, store_id: int, store: VectorStoreUpdate, space_id: int = None) -> VectorStoreResponse:
        db_store = VectorStoreRepository.update(db, store_id, store, space_id)
        if not db_store:
            raise HTTPException(status_code=404, detail="向量库不存在")
        return VectorStoreResponse.model_validate(db_store)

    @staticmethod
    def delete(db: Session, store_id: int, space_id: int = None) -> bool:
        # 检查是否有知识库引用此向量库所在空间
        if space_id is not None:
            kb_count = (
                db.query(KnowledgeBase)
                .filter(KnowledgeBase.space_id == space_id)
                .count()
            )
            if kb_count > 0:
                raise HTTPException(
                    status_code=400,
                    detail=f"该向量库关联了 {kb_count} 个知识库，请先删除相关知识库后再删除向量库",
                )
        if not VectorStoreRepository.delete(db, store_id, space_id):
            raise HTTPException(status_code=404, detail="向量库不存在")
        return True

    @staticmethod
    async def test_store(store: VectorStoreTestRequest) -> VectorStoreTestResponse:
        provider = get_vector_store_provider(store.provider)
        try:
            ok = provider.test_connection({
                "host": store.host,
                "port": store.port,
                "username": store.username,
                "password": store.password,
                "database": store.database,
                "collection_prefix": store.collection_prefix,
                "dimension": store.dimension,
            })
            return VectorStoreTestResponse(success=ok, message="连接测试成功" if ok else "连接测试失败")
        except Exception as e:
            return VectorStoreTestResponse(success=False, message=str(e))

    @staticmethod
    def resolve_active_store(db: Optional[Session] = None, space_id: int = None, kb_id: int = None):
        if not db:
            raise ValueError("数据库会话 required")
        store = resolve_knowledge_base_config(db, kb_id, space_id, "vector_store_id")
        if store is None:
            store = VectorStoreRepository.get_active(db, space_id)
        if not store:
            raise ValueError("向量库配置未找到，请在管理中心配置")
        return VectorStoreResponse.model_validate(store).model_dump()

    @staticmethod
    def _collection_name(store: Dict[str, Any], kb_id: int) -> str:
        prefix = store.get("collection_prefix") or "v_kb"
        return f"{prefix}{kb_id}"

    @staticmethod
    def collection_exists_for_kb(db: Optional[Session], kb_id: int, space_id: int = None) -> bool:
        store = VectorStoreService.resolve_active_store(db, space_id, kb_id=kb_id)
        provider = get_vector_store_provider(store.get("provider", "milvus"))
        return provider.collection_exists(store, VectorStoreService._collection_name(store, kb_id))

    @staticmethod
    def create_collection_for_kb(db: Optional[Session], kb_id: int, dimension: Optional[int] = None, space_id: int = None) -> bool:
        store = VectorStoreService.resolve_active_store(db, space_id, kb_id=kb_id)
        provider = get_vector_store_provider(store.get("provider", "milvus"))
        return provider.create_collection(store, VectorStoreService._collection_name(store, kb_id), dimension=dimension)

    @staticmethod
    def delete_vectors_by_table(db: Optional[Session], kb_id: int, table_name: str, space_id: int = None) -> bool:
        store = VectorStoreService.resolve_active_store(db, space_id, kb_id=kb_id)
        provider = get_vector_store_provider(store.get("provider", "milvus"))
        return provider.delete_by_table(store, VectorStoreService._collection_name(store, kb_id), table_name)

    @staticmethod
    def upsert_vectors_by_table(db: Optional[Session], kb_id: int, table_name: str, data: List[Dict[str, Any]], space_id: int = None) -> bool:
        store = VectorStoreService.resolve_active_store(db, space_id, kb_id=kb_id)
        provider = get_vector_store_provider(store.get("provider", "milvus"))
        return provider.upsert_vectors_by_table(store, VectorStoreService._collection_name(store, kb_id), table_name, data)

    @staticmethod
    def delete_vectors_by_field_type(db: Optional[Session], kb_id: int, field_type: str, space_id: int = None) -> bool:
        store = VectorStoreService.resolve_active_store(db, space_id, kb_id=kb_id)
        provider = get_vector_store_provider(store.get("provider", "milvus"))
        return provider.delete_by_field_type(store, VectorStoreService._collection_name(store, kb_id), field_type)

    @staticmethod
    def delete_vectors_by_table_field(db: Optional[Session], kb_id: int, field_type: str, table_name: str = None, field_code: str = None, space_id: int = None) -> bool:
        store = VectorStoreService.resolve_active_store(db, space_id, kb_id=kb_id)
        provider = get_vector_store_provider(store.get("provider", "milvus"))
        return provider.delete_by_table_field(store, VectorStoreService._collection_name(store, kb_id), field_type, table_name, field_code)

    @staticmethod
    def delete_vector_value(db: Optional[Session], kb_id: int, field_type: str, table_name: str, field_code: str, field_value: str, space_id: int = None) -> bool:
        store = VectorStoreService.resolve_active_store(db, space_id, kb_id=kb_id)
        provider = get_vector_store_provider(store.get("provider", "milvus"))
        return provider.delete_by_table_field_value(store, VectorStoreService._collection_name(store, kb_id), field_type, table_name, field_code, field_value)

    @staticmethod
    def delete_vector_items(db: Optional[Session], kb_id: int, field_type: str, items: List[Dict[str, Any]], space_id: int = None) -> bool:
        if not items:
            return True
        store = VectorStoreService.resolve_active_store(db, space_id, kb_id=kb_id)
        provider = get_vector_store_provider(store.get("provider", "milvus"))
        return provider.delete_items(
            store,
            VectorStoreService._collection_name(store, kb_id),
            field_type,
            items,
        )

    @staticmethod
    def insert_vectors(db: Optional[Session], kb_id: int, data: List[Dict[str, Any]], space_id: int = None) -> bool:
        store = VectorStoreService.resolve_active_store(db, space_id, kb_id=kb_id)
        provider = get_vector_store_provider(store.get("provider", "milvus"))
        return provider.insert_vectors(store, VectorStoreService._collection_name(store, kb_id), data)

    @staticmethod
    def search_vectors(db: Optional[Session], kb_id: int, query_vector: List[float], top_k: int = 10, expr: Optional[str] = None, space_id: int = None):
        store = VectorStoreService.resolve_active_store(db, space_id, kb_id=kb_id)
        return VectorStoreService.search_vectors_with_config(store, kb_id, query_vector, top_k=top_k, expr=expr)

    @staticmethod
    def search_vectors_with_config(store: Dict[str, Any], kb_id: int, query_vector: List[float], top_k: int = 10, expr: Optional[str] = None):
        """使用已解析配置执行网络查询，便于工作线程不携带数据库会话。"""
        provider = get_vector_store_provider(store.get("provider", "milvus"))
        return provider.search_vectors(store, VectorStoreService._collection_name(store, kb_id), query_vector, top_k=top_k, expr=expr)
