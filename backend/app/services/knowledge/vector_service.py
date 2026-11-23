"""
Milvus 向量服务 - 仅保留底层实现
上层统一通过 vector_store service/provider 调用。
配置从数据库读取，不从环境变量读取。
"""
import hashlib
import inspect
import json
import logging
import uuid
from collections import OrderedDict
from typing import List, Dict, Any, Optional, Callable, TypeVar
from pymilvus import connections, Collection, FieldSchema, CollectionSchema, DataType

logger = logging.getLogger(__name__)
MILVUS_OPERATION_TIMEOUT_SECONDS = 30
MILVUS_DELETE_EXPR_BATCH_SIZE = 100

T = TypeVar("T")


class MilvusService:
    """Milvus 向量数据库服务，配置从数据库读取"""

    def __init__(self, config: dict):
        self.host = config.get("host") or None
        self.port = config.get("port") or None
        self.user = config.get("username") or ""
        self.password = config.get("password") or ""
        self.db_name = config.get("database") or "app"
        if not self.host:
            raise ValueError("向量库地址未配置，请在管理中心配置向量库")
        if not self.port:
            raise ValueError("向量库端口未配置，请在管理中心配置向量库")
        self._connected = False
        self._search_collections = OrderedDict()
        identity = json.dumps([self.host, str(self.port), self.user, self.password, self.db_name])
        self._alias = "kb_milvus_" + hashlib.sha256(identity.encode()).hexdigest()[:16] + "_" + uuid.uuid4().hex

    def _call_with_timeout(self, description: str, func: Callable[..., T], *args, **kwargs) -> T:
        # PyMilvus 2.5 uses an integer timeout as a retry budget, overriding
        # retry_times. A float retains the RPC deadline and honors zero retries.
        options = {'timeout': float(MILVUS_OPERATION_TIMEOUT_SECONDS),
                   'retry_times': 0, 'retry_on_rate_limit': False}
        parameters = inspect.signature(func).parameters
        if not any(p.kind == inspect.Parameter.VAR_KEYWORD for p in parameters.values()):
            options = {key: value for key, value in options.items() if key in parameters}
        # Determine argument support before invocation; never replay a TypeError.
        return func(*args, **{**kwargs, **options})

    def _collection(self, collection_name: str, **kwargs):
        return self._call_with_timeout(f'open collection {collection_name}', Collection,
                                       collection_name, using=self._alias, **kwargs)

    def _has_collection(self, collection_name: str) -> bool:
        # The pinned ORM utility drops retry kwargs; use its same handler so
        # metadata lookups follow the single-attempt policy as searches do.
        handler = connections._fetch_handler(self._alias)
        return bool(self._call_with_timeout(f"check collection {collection_name}", handler.has_collection, collection_name))

    def connect(self):
        if self._connected:
            return
        connections.connect(
            alias=self._alias,
            db_name=self.db_name,
            host=self.host,
            port=int(self.port),
            user=self.user or None,
            password=self.password or None,
            timeout=float(MILVUS_OPERATION_TIMEOUT_SECONDS),
        )
        self._connected = True

    def test_connection(self) -> bool:
        try:
            self.connect()
            return True
        except Exception as e:
            logger.error("Failed to connect to Milvus: %s", e)
            return False

    def disconnect(self):
        if self._connected:
            connections.remove_connection(self._alias)
            self._connected = False
        self._search_collections.clear()

    close = disconnect

    def collection_exists(self, collection_name: str) -> bool:
        self.connect()
        return self._has_collection(collection_name)

    def create_collection(self, collection_name: str, dimension: int = 1024) -> bool:
        self.connect()
        try:
            dimension = int(dimension or 1024)
            if self._has_collection(collection_name):
                collection = self._collection(collection_name)
                embedding_field = next((field for field in collection.schema.fields if field.name == "embedding"), None)
                actual_dimension = embedding_field.params.get("dim") if embedding_field is not None else None
                if actual_dimension is None or int(actual_dimension) != dimension:
                    raise ValueError(
                        f"Collection {collection_name} embedding dimension is {actual_dimension}, "
                        f"but the configured embedding model requires {dimension}; use a compatible collection"
                    )
                return True
            fields = [
                FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
                FieldSchema(name="kb_id", dtype=DataType.INT64),
                FieldSchema(name="field_type", dtype=DataType.VARCHAR, max_length=50),
                FieldSchema(name="field_table", dtype=DataType.VARCHAR, max_length=255),
                FieldSchema(name="field_code", dtype=DataType.VARCHAR, max_length=500),
                FieldSchema(name="field_value", dtype=DataType.VARCHAR, max_length=1000),
                FieldSchema(name="sql_content", dtype=DataType.VARCHAR, max_length=2000),
                FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=dimension),
            ]
            schema = CollectionSchema(fields, description=f"Knowledge base vector collection: {collection_name}")
            collection = self._collection(collection_name, schema=schema)
            self._call_with_timeout(
                f"create index for {collection_name}",
                collection.create_index,
                field_name="embedding",
                index_params={"metric_type": "COSINE", "index_type": "IVF_FLAT", "params": {"nlist": 128}},
            )
            return True
        except Exception as e:
            logger.error("Failed to create collection %s: %s", collection_name, e)
            return False

    def delete_by_table(self, collection_name: str, table_name: str) -> bool:
        self.connect()
        try:
            if not self._has_collection(collection_name):
                return True
            collection = self._collection(collection_name)
            self._call_with_timeout(f"load collection {collection_name}", collection.load)
            self._call_with_timeout(
                f"delete table vectors from {collection_name}",
                collection.delete,
                f'field_table == "{self._expr_quote(table_name)}"',
            )
            self._call_with_timeout(f"flush collection {collection_name}", collection.flush)
            return True
        except Exception as e:
            logger.error("Failed to delete vectors for table %s from %s: %s", table_name, collection_name, e)
            return False

    def delete_by_field_type(self, collection_name: str, field_type: str) -> bool:
        self.connect()
        try:
            if not self._has_collection(collection_name):
                return True
            collection = self._collection(collection_name)
            self._call_with_timeout(f"load collection {collection_name}", collection.load)
            self._call_with_timeout(
                f"delete field_type vectors from {collection_name}",
                collection.delete,
                f'field_type == "{self._expr_quote(field_type)}"',
            )
            self._call_with_timeout(f"flush collection {collection_name}", collection.flush)
            return True
        except Exception as e:
            logger.error("Failed to delete vectors with field_type=%s from %s: %s", field_type, collection_name, e)
            return False

    @staticmethod
    def _expr_quote(value: str) -> str:
        return str(value or "").replace("\\", "\\\\").replace('"', '\\"')

    def delete_by_table_field(self, collection_name: str, field_type: str, table_name: str = None, field_code: str = None) -> bool:
        self.connect()
        try:
            if not self._has_collection(collection_name):
                return True
            expr_parts = [f'field_type == "{self._expr_quote(field_type)}"']
            if table_name is not None:
                expr_parts.append(f'field_table == "{self._expr_quote(table_name)}"')
            if field_code is not None:
                expr_parts.append(f'field_code == "{self._expr_quote(field_code)}"')
            collection = self._collection(collection_name)
            self._call_with_timeout(f"load collection {collection_name}", collection.load)
            self._call_with_timeout(
                f"delete field vectors from {collection_name}",
                collection.delete,
                " && ".join(expr_parts),
            )
            self._call_with_timeout(f"flush collection {collection_name}", collection.flush)
            return True
        except Exception as e:
            logger.error("Failed to delete vectors by field from %s: %s", collection_name, e)
            return False

    def delete_by_table_field_value(self, collection_name: str, field_type: str, table_name: str, field_code: str, field_value: str) -> bool:
        return self.delete_items(
            collection_name,
            field_type,
            [{
                "field_table": table_name,
                "field_code": field_code,
                "field_value": field_value,
            }],
        )

    def delete_items(self, collection_name: str, field_type: str, items: List[Dict[str, Any]]) -> bool:
        self.connect()
        try:
            if not items or not self._has_collection(collection_name):
                return True

            unique_conditions = []
            seen = set()
            for item in items:
                parts = [f'field_type == "{self._expr_quote(field_type)}"']
                for source_key, milvus_key in (
                    ("field_table", "field_table"),
                    ("field_code", "field_code"),
                    ("field_value", "field_value"),
                ):
                    if source_key in item and item[source_key] is not None:
                        parts.append(
                            f'{milvus_key} == "{self._expr_quote(item[source_key])}"'
                        )
                condition = " && ".join(parts)
                if condition not in seen:
                    seen.add(condition)
                    unique_conditions.append(condition)

            collection = self._collection(collection_name)
            self._call_with_timeout(f"load collection {collection_name}", collection.load)
            logger.info(
                "Deleting %s vector item conditions from %s in %s batches",
                len(unique_conditions),
                collection_name,
                (len(unique_conditions) + MILVUS_DELETE_EXPR_BATCH_SIZE - 1)
                // MILVUS_DELETE_EXPR_BATCH_SIZE,
            )
            for start in range(0, len(unique_conditions), MILVUS_DELETE_EXPR_BATCH_SIZE):
                batch = unique_conditions[start:start + MILVUS_DELETE_EXPR_BATCH_SIZE]
                expr = " || ".join(f"({condition})" for condition in batch)
                self._call_with_timeout(
                    f"delete vector item batch from {collection_name}",
                    collection.delete,
                    expr,
                )
            self._call_with_timeout(f"flush collection {collection_name}", collection.flush)
            return True
        except Exception as e:
            logger.error("Failed to batch delete vector items from %s: %s", collection_name, e)
            return False

    def insert_vectors(self, collection_name: str, data: List[Dict[str, Any]]) -> bool:
        self.connect()
        try:
            if not data:
                return True
            collection = self._collection(collection_name)
            self._call_with_timeout(
                f"insert {len(data)} vectors into {collection_name}",
                collection.insert,
                [
                    [int(i["kb_id"]) for i in data],
                    [str(i["field_type"]) for i in data],
                    [str(i["field_table"]) for i in data],
                    [str(i["field_code"]) for i in data],
                    [str(i["field_value"]) for i in data],
                    [str(i.get("sql_content", "")) for i in data],
                    [list(i["embedding"]) for i in data],
                ],
            )
            self._call_with_timeout(f"flush collection {collection_name}", collection.flush)
            return True
        except Exception as e:
            logger.error("Failed to insert vectors into %s: %s", collection_name, e)
            return False

    def upsert_vectors_by_table(self, collection_name: str, table_name: str, data: List[Dict[str, Any]]) -> bool:
        self.connect()
        try:
            if not self.delete_by_table(collection_name, table_name):
                raise Exception("delete failed")
            if not data:
                return True
            return self.insert_vectors(collection_name, data)
        except Exception as e:
            logger.error("Failed to upsert vectors for table %s into %s: %s", table_name, collection_name, e)
            return False

    def upsert_vectors_by_field(self, collection_name: str, table_name: str, field_name: str, data: List[Dict[str, Any]]) -> bool:
        return self.upsert_vectors_by_table(collection_name, table_name, data)

    def search_vectors(self, collection_name: str, query_vector: List[float], top_k: int = 10, expr: Optional[str] = None, output_fields: Optional[List[str]] = None) -> List[Dict]:
        self.connect()
        try:
            collection = self._search_collections.get(collection_name)
            if collection is None:
                collection = self._collection(collection_name)
                self._call_with_timeout(f"load collection {collection_name}", collection.load)
                self._search_collections[collection_name] = collection
                while len(self._search_collections) > 32:
                    self._search_collections.popitem(last=False)
            self._search_collections.move_to_end(collection_name)
            results = self._call_with_timeout(
                f"search vectors in {collection_name}",
                collection.search,
                data=[query_vector],
                anns_field="embedding",
                param={"metric_type": "COSINE", "params": {"nprobe": 10}},
                limit=top_k,
                output_fields=output_fields or ["field_type", "field_table", "field_code", "field_value", "sql_content", "kb_id"],
                expr=expr,
            )
            formatted = []
            for hits in results:
                for hit in hits:
                    ent = hit.entity or {}
                    formatted.append({"id": hit.id, "distance": hit.distance, "field_type": ent.get("field_type"), "field_table": ent.get("field_table"), "field_code": ent.get("field_code"), "field_value": ent.get("field_value"), "sql_content": ent.get("sql_content"), "kb_id": ent.get("kb_id")})
            return formatted
        except Exception as e:
            self._search_collections.pop(collection_name, None)
            logger.error("Failed to search vectors in %s: %s", collection_name, e)
            return []

    def get_collection_stats(self, collection_name: str) -> Dict[str, Any]:
        self.connect()
        try:
            if not self._has_collection(collection_name):
                return {"exists": False, "count": 0}
            collection = self._collection(collection_name)
            return {"exists": True, "count": collection.num_entities, "name": collection_name}
        except Exception as e:
            logger.error("Failed to get stats for %s: %s", collection_name, e)
            return {"exists": False, "count": 0, "error": str(e)}
