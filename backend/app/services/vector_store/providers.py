"""
向量库 provider 抽象。
当前先实现 Milvus，后续可继续扩展 Qdrant / pgvector / Elasticsearch。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from ...core.resources import thread_resource

from ..knowledge.azure_search_service import AzureAISearchService
from ..knowledge.vector_service import MilvusService
from .opensearch import OpenSearchVectorProvider


class VectorStoreProvider(ABC):
    @abstractmethod
    def test_connection(self, config: Dict[str, Any]) -> bool:
        raise NotImplementedError

    @abstractmethod
    def collection_exists(self, config: Dict[str, Any], collection_name: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def create_collection(self, config: Dict[str, Any], collection_name: str, dimension: Optional[int] = None) -> bool:
        raise NotImplementedError

    @abstractmethod
    def delete_by_table(self, config: Dict[str, Any], collection_name: str, table_name: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def upsert_vectors_by_table(self, config: Dict[str, Any], collection_name: str, table_name: str, data: List[Dict[str, Any]]) -> bool:
        raise NotImplementedError

    @abstractmethod
    def search_vectors(self, config: Dict[str, Any], collection_name: str, query_vector: List[float], top_k: int = 10, expr: Optional[str] = None):
        raise NotImplementedError

    @abstractmethod
    def delete_by_field_type(self, config: Dict[str, Any], collection_name: str, field_type: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def delete_by_table_field(self, config: Dict[str, Any], collection_name: str, field_type: str, table_name: Optional[str] = None, field_code: Optional[str] = None) -> bool:
        raise NotImplementedError

    @abstractmethod
    def delete_by_table_field_value(self, config: Dict[str, Any], collection_name: str, field_type: str, table_name: str, field_code: str, field_value: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def delete_items(self, config: Dict[str, Any], collection_name: str, field_type: str, items: List[Dict[str, Any]]) -> bool:
        raise NotImplementedError

    @abstractmethod
    def insert_vectors(self, config: Dict[str, Any], collection_name: str, data: List[Dict[str, Any]]) -> bool:
        raise NotImplementedError


class MilvusProvider(VectorStoreProvider):
    def _get_service(self, config: Dict[str, Any]) -> MilvusService:
        return thread_resource(MilvusService, config)

    def test_connection(self, config: Dict[str, Any]) -> bool:
        svc = self._get_service(config)
        return svc.test_connection()

    def collection_exists(self, config: Dict[str, Any], collection_name: str) -> bool:
        return self._get_service(config).collection_exists(collection_name)

    def create_collection(self, config: Dict[str, Any], collection_name: str, dimension: Optional[int] = None) -> bool:
        svc = self._get_service(config)
        return svc.create_collection(collection_name, dimension or config.get("dimension") or 1024)

    def delete_by_table(self, config: Dict[str, Any], collection_name: str, table_name: str) -> bool:
        svc = self._get_service(config)
        return svc.delete_by_table(collection_name, table_name)

    def upsert_vectors_by_table(self, config: Dict[str, Any], collection_name: str, table_name: str, data: List[Dict[str, Any]]) -> bool:
        svc = self._get_service(config)
        return svc.upsert_vectors_by_table(collection_name, table_name, data)

    def search_vectors(self, config: Dict[str, Any], collection_name: str, query_vector: List[float], top_k: int = 10, expr: Optional[str] = None):
        svc = self._get_service(config)
        return svc.search_vectors(collection_name, query_vector, top_k=top_k, expr=expr)

    def delete_by_field_type(self, config: Dict[str, Any], collection_name: str, field_type: str) -> bool:
        svc = self._get_service(config)
        return svc.delete_by_field_type(collection_name, field_type)

    def delete_by_table_field(self, config: Dict[str, Any], collection_name: str, field_type: str, table_name: Optional[str] = None, field_code: Optional[str] = None) -> bool:
        svc = self._get_service(config)
        return svc.delete_by_table_field(collection_name, field_type, table_name, field_code)

    def delete_by_table_field_value(self, config: Dict[str, Any], collection_name: str, field_type: str, table_name: str, field_code: str, field_value: str) -> bool:
        svc = self._get_service(config)
        return svc.delete_by_table_field_value(collection_name, field_type, table_name, field_code, field_value)

    def delete_items(self, config: Dict[str, Any], collection_name: str, field_type: str, items: List[Dict[str, Any]]) -> bool:
        return self._get_service(config).delete_items(collection_name, field_type, items)

    def insert_vectors(self, config: Dict[str, Any], collection_name: str, data: List[Dict[str, Any]]) -> bool:
        svc = self._get_service(config)
        return svc.insert_vectors(collection_name, data)


class AzureAISearchProvider(VectorStoreProvider):
    def _get_service(self, config: Dict[str, Any]) -> AzureAISearchService:
        return thread_resource(AzureAISearchService, config)

    def test_connection(self, config: Dict[str, Any]) -> bool:
        return self._get_service(config).test_connection()

    def collection_exists(self, config: Dict[str, Any], collection_name: str) -> bool:
        return self._get_service(config).index_exists(collection_name)

    def create_collection(self, config: Dict[str, Any], collection_name: str, dimension: Optional[int] = None) -> bool:
        return self._get_service(config).create_vector_index(collection_name, dimension or config.get("dimension") or 1024)

    def delete_by_table(self, config: Dict[str, Any], collection_name: str, table_name: str) -> bool:
        svc = self._get_service(config)
        index_name = svc.normalize_index_name(collection_name)
        return svc.delete_by_filter(index_name, f"field_table eq '{svc._odata_quote(table_name)}'")

    def upsert_vectors_by_table(self, config: Dict[str, Any], collection_name: str, table_name: str, data: List[Dict[str, Any]]) -> bool:
        svc = self._get_service(config)
        svc.create_vector_index(collection_name, config.get("dimension") or (len(data[0]["embedding"]) if data else 1024))
        return svc.upsert_vectors_by_table(collection_name, table_name, data)

    def search_vectors(self, config: Dict[str, Any], collection_name: str, query_vector: List[float], top_k: int = 10, expr: Optional[str] = None):
        return self._get_service(config).search_vectors(collection_name, query_vector, top_k=top_k, expr=expr)

    def delete_by_field_type(self, config: Dict[str, Any], collection_name: str, field_type: str) -> bool:
        svc = self._get_service(config)
        index_name = svc.normalize_index_name(collection_name)
        return svc.delete_by_filter(index_name, f"field_type eq '{svc._odata_quote(field_type)}'")

    def delete_by_table_field(self, config: Dict[str, Any], collection_name: str, field_type: str, table_name: Optional[str] = None, field_code: Optional[str] = None) -> bool:
        svc = self._get_service(config)
        index_name = svc.normalize_index_name(collection_name)
        filters = [f"field_type eq '{svc._odata_quote(field_type)}'"]
        if table_name is not None:
            filters.append(f"field_table eq '{svc._odata_quote(table_name)}'")
        if field_code is not None:
            filters.append(f"field_code eq '{svc._odata_quote(field_code)}'")
        return svc.delete_by_filter(index_name, " and ".join(filters))

    def delete_by_table_field_value(self, config: Dict[str, Any], collection_name: str, field_type: str, table_name: str, field_code: str, field_value: str) -> bool:
        svc = self._get_service(config)
        index_name = svc.normalize_index_name(collection_name)
        return svc.delete_by_filter(
            index_name,
            " and ".join([
                f"field_type eq '{svc._odata_quote(field_type)}'",
                f"field_table eq '{svc._odata_quote(table_name)}'",
                f"field_code eq '{svc._odata_quote(field_code)}'",
                f"field_value eq '{svc._odata_quote(field_value)}'",
            ]),
        )

    def delete_items(self, config: Dict[str, Any], collection_name: str, field_type: str, items: List[Dict[str, Any]]) -> bool:
        if not items:
            return True
        svc = self._get_service(config)
        index_name = svc.normalize_index_name(collection_name)
        batch_size = 100
        for start in range(0, len(items), batch_size):
            conditions = []
            for item in items[start:start + batch_size]:
                filters = [f"field_type eq '{svc._odata_quote(field_type)}'"]
                for source_key, azure_key in (
                    ("field_table", "field_table"),
                    ("field_code", "field_code"),
                    ("field_value", "field_value"),
                ):
                    if source_key in item and item[source_key] is not None:
                        filters.append(
                            f"{azure_key} eq '{svc._odata_quote(item[source_key])}'"
                        )
                conditions.append(f"({' and '.join(filters)})")
            if not svc.delete_by_filter(index_name, " or ".join(conditions)):
                return False
        return True

    def insert_vectors(self, config: Dict[str, Any], collection_name: str, data: List[Dict[str, Any]]) -> bool:
        return self._get_service(config).upsert_vectors(collection_name, data)


class UnsupportedProvider(VectorStoreProvider):
    def __init__(self, name: str):
        self.name = name

    def test_connection(self, config: Dict[str, Any]) -> bool:
        raise HTTPException(status_code=400, detail=f"暂未实现 {self.name} 向量库")

    def collection_exists(self, config: Dict[str, Any], collection_name: str) -> bool:
        raise HTTPException(status_code=400, detail=f"暂未实现 {self.name} 向量库")

    def create_collection(self, config: Dict[str, Any], collection_name: str, dimension: Optional[int] = None) -> bool:
        raise HTTPException(status_code=400, detail=f"暂未实现 {self.name} 向量库")

    def delete_by_table(self, config: Dict[str, Any], collection_name: str, table_name: str) -> bool:
        raise HTTPException(status_code=400, detail=f"暂未实现 {self.name} 向量库")

    def upsert_vectors_by_table(self, config: Dict[str, Any], collection_name: str, table_name: str, data: List[Dict[str, Any]]) -> bool:
        raise HTTPException(status_code=400, detail=f"暂未实现 {self.name} 向量库")

    def search_vectors(self, config: Dict[str, Any], collection_name: str, query_vector: List[float], top_k: int = 10, expr: Optional[str] = None):
        raise HTTPException(status_code=400, detail=f"暂未实现 {self.name} 向量库")

    def delete_by_field_type(self, config: Dict[str, Any], collection_name: str, field_type: str) -> bool:
        raise HTTPException(status_code=400, detail=f"暂未实现 {self.name} 向量库")

    def delete_by_table_field(self, config: Dict[str, Any], collection_name: str, field_type: str, table_name: Optional[str] = None, field_code: Optional[str] = None) -> bool:
        raise HTTPException(status_code=400, detail=f"暂未实现 {self.name} 向量库")

    def delete_by_table_field_value(self, config: Dict[str, Any], collection_name: str, field_type: str, table_name: str, field_code: str, field_value: str) -> bool:
        raise HTTPException(status_code=400, detail=f"暂未实现 {self.name} 向量库")

    def delete_items(self, config: Dict[str, Any], collection_name: str, field_type: str, items: List[Dict[str, Any]]) -> bool:
        raise HTTPException(status_code=400, detail=f"暂未实现 {self.name} 向量库")

    def insert_vectors(self, config: Dict[str, Any], collection_name: str, data: List[Dict[str, Any]]) -> bool:
        raise HTTPException(status_code=400, detail=f"暂未实现 {self.name} 向量库")


PROVIDER_REGISTRY = {
    "opensearch": OpenSearchVectorProvider(),
    "milvus": MilvusProvider(),
    "azure_ai_search": AzureAISearchProvider(),
    "azure-search": AzureAISearchProvider(),
    "qdrant": UnsupportedProvider("Qdrant"),
    "pgvector": UnsupportedProvider("pgvector"),
    "elasticsearch": UnsupportedProvider("Elasticsearch"),
}


def get_vector_store_provider(provider: str) -> VectorStoreProvider:
    if provider not in PROVIDER_REGISTRY:
        raise HTTPException(status_code=400, detail=f"暂不支持的向量库类型: {provider}")
    return PROVIDER_REGISTRY[provider]
