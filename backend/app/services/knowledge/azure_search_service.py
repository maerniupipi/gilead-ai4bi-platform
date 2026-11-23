"""
Azure AI Search adapter for keyword and vector retrieval.
"""
from __future__ import annotations

import logging
import re
import time
import uuid
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def is_azure_search_config(config: Dict[str, Any]) -> bool:
    provider = (config.get("provider") or "").lower()
    host = (config.get("host") or "").lower()
    # search.windows.net 为国际域名，search.azure.cn 为世纪互联中国区域名
    return provider in {"azure_ai_search", "azure-search"} or any(
        domain in host for domain in ("search.windows.net", "search.azure.cn")
    )


class AzureAISearchService:
    """Small wrapper around azure-search-documents."""

    def __init__(self, config: Dict[str, Any]):
        self.endpoint = self._normalize_endpoint(config.get("host"))
        self.api_key = config.get("password") or config.get("api_key")
        self.collection_prefix = config.get("collection_prefix") or "v-kb"
        if not self.endpoint:
            raise ValueError("Azure AI Search endpoint 未配置")
        if not self.api_key:
            raise ValueError("Azure AI Search API Key 未配置，请填写到密码/API Key 字段")
        self._index_client = None
        self._search_clients: Dict[str, Any] = {}

    @staticmethod
    def _normalize_endpoint(host: Optional[str]) -> str:
        endpoint = (host or "").strip().rstrip("/")
        if not endpoint:
            return ""
        if not endpoint.startswith(("http://", "https://")):
            endpoint = f"https://{endpoint}"
        return endpoint

    @staticmethod
    def normalize_index_name(name: str) -> str:
        normalized = re.sub(r"[^a-z0-9-]+", "-", (name or "").lower()).strip("-")
        normalized = re.sub(r"-{2,}", "-", normalized)
        if not normalized:
            normalized = "idx"
        if not normalized[0].isalnum():
            normalized = f"idx-{normalized}"
        if len(normalized) < 2:
            normalized = f"{normalized}-1"
        return normalized[:128].rstrip("-")

    def _imports(self):
        try:
            from azure.core.credentials import AzureKeyCredential
            from azure.search.documents import SearchClient
            from azure.search.documents.indexes import SearchIndexClient
            from azure.search.documents.indexes.models import (
                HnswAlgorithmConfiguration,
                HnswParameters,
                SearchableField,
                SearchField,
                SearchFieldDataType,
                SearchIndex,
                SimpleField,
                VectorSearch,
                VectorSearchProfile,
            )
            from azure.search.documents.models import VectorizedQuery
        except ImportError as exc:
            raise RuntimeError("缺少 Azure AI Search 依赖，请安装 azure-search-documents") from exc
        return {
            "AzureKeyCredential": AzureKeyCredential,
            "SearchClient": SearchClient,
            "SearchIndexClient": SearchIndexClient,
            "HnswAlgorithmConfiguration": HnswAlgorithmConfiguration,
            "HnswParameters": HnswParameters,
            "SearchableField": SearchableField,
            "SearchField": SearchField,
            "SearchFieldDataType": SearchFieldDataType,
            "SearchIndex": SearchIndex,
            "SimpleField": SimpleField,
            "VectorSearch": VectorSearch,
            "VectorSearchProfile": VectorSearchProfile,
            "VectorizedQuery": VectorizedQuery,
        }

    def _credential(self):
        imports = self._imports()
        return imports["AzureKeyCredential"](self.api_key)

    def get_index_client(self):
        if self._index_client is None:
            imports = self._imports()
            self._index_client = imports["SearchIndexClient"](
                endpoint=self.endpoint,
                credential=self._credential(),
                connection_timeout=10,
                read_timeout=30,
                retry_total=0,
                retry_connect=0,
                retry_read=0,
                retry_status=0,
            )
        return self._index_client

    def get_search_client(self, index_name: str):
        index_name = self.normalize_index_name(index_name)
        if index_name not in self._search_clients:
            imports = self._imports()
            self._search_clients[index_name] = imports["SearchClient"](
                endpoint=self.endpoint,
                index_name=index_name,
                credential=self._credential(),
                connection_timeout=10,
                read_timeout=30,
                retry_total=0,
                retry_connect=0,
                retry_read=0,
                retry_status=0,
            )
        return self._search_clients[index_name]

    def close(self):
        for client in self._search_clients.values():
            client.close()
        self._search_clients.clear()
        if self._index_client is not None:
            self._index_client.close()
            self._index_client = None

    def test_connection(self) -> bool:
        try:
            list(self.get_index_client().list_index_names())
            return True
        except Exception as exc:
            logger.error("Azure AI Search connection failed: %s", exc)
            return False

    def index_exists(self, index_name: str) -> bool:
        index_name = self.normalize_index_name(index_name)
        try:
            self.get_index_client().get_index(index_name)
            return True
        except Exception as exc:
            if getattr(exc, "status_code", None) == 404:
                return False
            raise

    def create_vector_index(self, index_name: str, dimension: int = 1024) -> bool:
        index_name = self.normalize_index_name(index_name)
        dimension = int(dimension or 1024)
        if self.index_exists(index_name):
            index = self.get_index_client().get_index(index_name)
            embedding_field = next((field for field in index.fields if field.name == "embedding"), None)
            actual_dimension = getattr(embedding_field, "vector_search_dimensions", None)
            if actual_dimension is None or int(actual_dimension) != dimension:
                raise ValueError(
                    f"Index {index_name} embedding dimension is {actual_dimension}, "
                    f"but the configured embedding model requires {dimension}; use a compatible index"
                )
            return True

        imports = self._imports()
        fields = [
            imports["SimpleField"](name="id", type=imports["SearchFieldDataType"].String, key=True, filterable=True),
            imports["SimpleField"](name="kb_id", type=imports["SearchFieldDataType"].Int64, filterable=True),
            imports["SimpleField"](name="field_type", type=imports["SearchFieldDataType"].String, filterable=True),
            imports["SimpleField"](name="field_table", type=imports["SearchFieldDataType"].String, filterable=True),
            imports["SimpleField"](name="field_code", type=imports["SearchFieldDataType"].String, filterable=True),
            imports["SearchableField"](name="field_value", type=imports["SearchFieldDataType"].String, filterable=True),
            imports["SearchableField"](name="sql_content", type=imports["SearchFieldDataType"].String),
            imports["SearchField"](
                name="embedding",
                type=imports["SearchFieldDataType"].Collection(imports["SearchFieldDataType"].Single),
                searchable=True,
                vector_search_dimensions=dimension,
                vector_search_profile_name="vector-profile",
            ),
        ]
        vector_search = imports["VectorSearch"](
            profiles=[
                imports["VectorSearchProfile"](
                    name="vector-profile",
                    algorithm_configuration_name="hnsw-config",
                )
            ],
            algorithms=[
                imports["HnswAlgorithmConfiguration"](
                    name="hnsw-config",
                    parameters=imports["HnswParameters"](metric="cosine"),
                )
            ],
        )
        index = imports["SearchIndex"](name=index_name, fields=fields, vector_search=vector_search)
        self.get_index_client().create_or_update_index(index)
        return True

    def create_keyword_index(self, index_name: str, fields: List[Dict[str, str]]) -> bool:
        imports = self._imports()
        index_name = self.normalize_index_name(index_name)
        if self.index_exists(index_name):
            return True
        index_fields = [
            imports["SimpleField"](name="id", type=imports["SearchFieldDataType"].String, key=True, filterable=True),
        ]
        for field in fields:
            name = field["name"]
            if field.get("searchable", True):
                index_fields.append(
                    imports["SearchableField"](
                        name=name,
                        type=imports["SearchFieldDataType"].String,
                        filterable=bool(field.get("filterable", False)),
                        analyzer_name=field.get("analyzer") or "zh-Hans.microsoft",
                    )
                )
            else:
                index_fields.append(
                    imports["SimpleField"](
                        name=name,
                        type=imports["SearchFieldDataType"].String,
                        filterable=bool(field.get("filterable", True)),
                    )
                )
        self.get_index_client().create_or_update_index(
            imports["SearchIndex"](name=index_name, fields=index_fields)
        )
        return True

    def delete_all_documents(self, index_name: str) -> bool:
        return self._delete_matching_documents(index_name)

    @staticmethod
    def _delete_document_batch(client, documents: List[Dict[str, str]]) -> bool:
        results = list(client.delete_documents(documents=documents) or [])
        failed = [item for item in results if not getattr(item, "succeeded", False)]
        if failed or len(results) != len(documents):
            logger.error("Azure AI Search delete failed: %s of %s results failed, %s results returned",
                         len(failed), len(documents), len(results))
            return False
        return True

    def delete_documents(self, index_name: str, ids: List[str]) -> bool:
        if not ids:
            return True
        index_name = self.normalize_index_name(index_name)
        if not self.index_exists(index_name):
            return True
        client = self.get_search_client(index_name)
        for start in range(0, len(ids), 1000):
            documents = [{"id": item_id} for item_id in ids[start:start + 1000]]
            if not self._delete_document_batch(client, documents):
                return False
        return True

    def _delete_matching_documents(self, index_name: str, filter_expr: Optional[str] = None) -> bool:
        index_name = self.normalize_index_name(index_name)
        if not self.index_exists(index_name):
            return True
        client = self.get_search_client(index_name)
        # Azure AI Search rejects any query whose $skip+$top exceeds 100000,
        # so neither manual skip-paging nor SDK auto-paging can enumerate a
        # large result set, and the key field cannot be used in $orderby
        # (it is not sortable). Instead, repeatedly delete the *first* page
        # (top=999, $skip always 0). Deleted ids are tracked; if a query only
        # returns already-deleted ids (the index is eventually consistent),
        # retry a few times before concluding the deletion is finished.
        search_args = {"search_text": "*", "select": ["id"], "top": 999}
        if filter_expr is not None:
            search_args["filter"] = filter_expr
        seen = set()
        stale_rounds = 0
        while True:
            page = [row["id"] for row in client.search(**search_args) if row["id"] not in seen]
            if not page:
                stale_rounds += 1
                if stale_rounds >= 3:
                    return True
                time.sleep(2)
                continue
            stale_rounds = 0
            seen.update(page)
            if not self._delete_document_batch(client, [{"id": i} for i in page]):
                return False
            if len(seen) >= 5_000_000:
                logger.error("Azure AI Search delete_by_filter aborted: matched more than 5M documents")
                return False

    def upload_documents(self, index_name: str, documents: List[Dict[str, Any]]) -> bool:
        if not documents:
            return True
        try:
            client = self.get_search_client(index_name)
            for start in range(0, len(documents), 1000):
                batch = documents[start:start + 1000]
                results = list(client.upload_documents(documents=batch) or [])
                failed = [item for item in results if not getattr(item, "succeeded", False)]
                if failed or len(results) != len(batch):
                    logger.error("Azure AI Search upload failed: %s of %s results failed, %s results returned",
                                 len(failed), len(batch), len(results))
                    return False
        except Exception as exc:
            logger.error("Azure AI Search upload failed for %s: %s", index_name, exc)
            return False
        return True

    def delete_by_filter(self, index_name: str, filter_expr: str) -> bool:
        return self._delete_matching_documents(index_name, filter_expr)

    @staticmethod
    def _doc_id(*parts: Any) -> str:
        raw = "|".join(str(p or "") for p in parts)
        return str(uuid.uuid5(uuid.NAMESPACE_URL, raw))

    def upsert_vectors_by_table(self, index_name: str, table_name: str, data: List[Dict[str, Any]]) -> bool:
        if not self.delete_by_filter(index_name, f"field_table eq '{self._odata_quote(table_name)}'"):
            return False
        return self.upsert_vectors(index_name, data)

    def upsert_vectors(self, index_name: str, data: List[Dict[str, Any]]) -> bool:
        docs = []
        for item in data:
            docs.append({
                "id": self._doc_id(index_name, item.get("kb_id"), item.get("field_type"), item.get("field_table"), item.get("field_code"), item.get("field_value")),
                "kb_id": int(item["kb_id"]),
                "field_type": str(item["field_type"]),
                "field_table": str(item["field_table"]),
                "field_code": str(item["field_code"]),
                "field_value": str(item["field_value"]),
                "sql_content": str(item.get("sql_content", "")),
                "embedding": [float(x) for x in item["embedding"]],
            })
        return self.upload_documents(index_name, docs)

    def search_vectors(self, index_name: str, query_vector: List[float], top_k: int = 10, expr: Optional[str] = None) -> List[Dict[str, Any]]:
        if not self.index_exists(index_name):
            return []
        imports = self._imports()
        vector_query = imports["VectorizedQuery"](
            vector=[float(x) for x in query_vector],
            k_nearest_neighbors=top_k,
            fields="embedding",
        )
        response = self.get_search_client(index_name).search(
            search_text=None,
            vector_queries=[vector_query],
            filter=self.milvus_expr_to_odata(expr),
            top=top_k,
            select=["id", "kb_id", "field_type", "field_table", "field_code", "field_value", "sql_content"],
        )
        return [self._format_vector_hit(row) for row in response]

    def keyword_search(self, index_name: str, query: str, fields: List[str], top_k: int = 10, *, filter_expr: Optional[str] = None) -> List[Dict[str, Any]]:
        if not self.index_exists(index_name):
            return []
        kwargs = {"filter": filter_expr} if filter_expr else {}
        response = self.get_search_client(index_name).search(
            search_text=(query or "*"),
            search_fields=fields,
            top=top_k,
            **kwargs,
        )
        return [self._to_plain_dict(row) for row in response]

    @staticmethod
    def _to_plain_dict(row: Any) -> Dict[str, Any]:
        data = dict(row)
        data["score"] = data.get("@search.score")
        return data

    @classmethod
    def _format_vector_hit(cls, row: Any) -> Dict[str, Any]:
        data = cls._to_plain_dict(row)
        return {
            "id": data.get("id"),
            "distance": data.get("@search.score") or data.get("score"),
            "field_type": data.get("field_type"),
            "field_table": data.get("field_table"),
            "field_code": data.get("field_code"),
            "field_value": data.get("field_value"),
            "sql_content": data.get("sql_content"),
            "kb_id": data.get("kb_id"),
        }

    @staticmethod
    def _odata_quote(value: Any) -> str:
        return str(value or "").replace("'", "''")

    @classmethod
    def milvus_expr_to_odata(cls, expr: Optional[str]) -> Optional[str]:
        if not expr:
            return None
        # 仅替换字符串字面量外部的 &&，避免 field_code 值（表&&字段）被转坏
        _lits = []

        def _mask(m):
            _lits.append(m.group(0))
            return "<<S%d>>" % (len(_lits) - 1)

        out = re.sub(r'"(?:[^"\\]|\\.)*"', _mask, expr).replace("&&", " and ")
        for _i, _lit in enumerate(_lits):
            out = out.replace("<<S%d>>" % _i, _lit)
        out = re.sub(
            r'(\b[a-zA-Z_][a-zA-Z0-9_]*\b)\s*==\s*"([^"]*)"',
            lambda m: f"{m.group(1)} eq '{cls._odata_quote(m.group(2))}'",
            out,
        )
        out = re.sub(
            r"(\b[a-zA-Z_][a-zA-Z0-9_]*\b)\s*==\s*([0-9]+)",
            r"\1 eq \2",
            out,
        )
        return out
