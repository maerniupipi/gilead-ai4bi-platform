"""OpenSearch k-NN storage for knowledge-base vectors."""

import hashlib
import json
import re
from urllib.parse import urlsplit

from opensearchpy import OpenSearch, helpers
from ...core.resources import thread_resource

FIELDS = (
    "kb_id",
    "field_type",
    "field_table",
    "field_code",
    "field_value",
    "sql_content",
)
FILTER = re.compile(r"\s*(kb_id|field_type|field_table|field_code|field_value)\s*==\s*")


def vector_filters(expression):
    terms = []
    rest = (expression or "").strip()
    while rest:
        match = FILTER.match(rest)
        if not match:
            raise ValueError("不支持的向量检索条件")
        value, end = json.JSONDecoder().raw_decode(rest[match.end() :])
        if not isinstance(value, (str, int)):
            raise ValueError("向量检索条件应为文本或整数")
        terms.append({"term": {match[1]: value}})
        rest = rest[match.end() + end :].strip()
        if rest:
            if not rest.startswith("&&") or not rest[2:].strip():
                raise ValueError("无效的向量检索条件")
            rest = rest[2:].strip()
    return terms


class SearchConnection:
    def __init__(self, config):
        raw = config.get("host") or "127.0.0.1"
        url = urlsplit(raw if "://" in raw else "http://" + raw)
        self.client = OpenSearch(
            hosts=[
                {
                    "host": url.hostname,
                    "port": int(config.get("port") or url.port or 9200),
                    "scheme": url.scheme,
                }
            ],
            http_auth=(config["username"], config.get("password", ""))
            if config.get("username")
            else None,
            timeout=30,
        )

    def close(self):
        self.client.close()


class OpenSearchVectorProvider:
    def client(self, config):
        return thread_resource(SearchConnection, config).client

    def test_connection(self, config):
        return self.client(config).ping()

    def collection_exists(self, config, collection_name):
        return self.client(config).indices.exists(index=collection_name)

    def create_collection(self, config, collection_name, dimension=None):
        client = self.client(config)
        size = int(dimension or config.get("dimension") or 1024)
        if client.indices.exists(index=collection_name):
            mapping = client.indices.get_mapping(index=collection_name)[
                collection_name
            ]["mappings"]
            if mapping["properties"]["embedding"]["dimension"] != size:
                raise ValueError("索引维度与向量模型不一致")
            return True
        fields = {name: {"type": "keyword", "ignore_above": 16000} for name in FIELDS}
        fields.update(
            kb_id={"type": "integer"},
            sql_content={"type": "text", "index": False},
            embedding={
                "type": "knn_vector",
                "dimension": size,
                "method": {
                    "name": "hnsw",
                    "engine": "lucene",
                    "space_type": "cosinesimil",
                },
            },
        )
        client.indices.create(
            index=collection_name,
            body={
                "settings": {
                    "index.knn": True,
                    "number_of_shards": 1,
                    "number_of_replicas": 0,
                },
                "mappings": {"properties": fields},
            },
        )
        return True

    def insert_vectors(self, config, collection_name, data):
        actions = []
        for item in data:
            doc = {k: item.get(k, "") for k in FIELDS}
            doc["embedding"] = item["embedding"]
            identity = [doc[k] for k in FIELDS[:-1]]
            key = hashlib.sha256(
                json.dumps(identity, ensure_ascii=False).encode()
            ).hexdigest()
            actions.append({"_index": collection_name, "_id": key, "_source": doc})
        if actions:
            helpers.bulk(self.client(config), actions, refresh="wait_for")
        return True

    def _delete(self, config, name, conditions):
        if self.collection_exists(config, name):
            self.client(config).delete_by_query(
                index=name, body={"query": conditions}, refresh=True
            )
        return True

    def delete_by_table(self, config, collection_name, table_name):
        return self._delete(
            config, collection_name, {"term": {"field_table": table_name}}
        )

    def upsert_vectors_by_table(self, config, collection_name, table_name, data):
        existing = {
            hit["_id"]
            for hit in helpers.scan(
                self.client(config),
                index=collection_name,
                query={
                    "_source": False,
                    "query": {"term": {"field_table": table_name}},
                },
            )
        }
        self.insert_vectors(config, collection_name, data)
        for item in data:
            key = hashlib.sha256(
                json.dumps(
                    [item.get(k, "") for k in FIELDS[:-1]], ensure_ascii=False
                ).encode()
            ).hexdigest()
            existing.discard(key)
        if existing:
            helpers.bulk(
                self.client(config),
                (
                    {"_op_type": "delete", "_index": collection_name, "_id": key}
                    for key in existing
                ),
                refresh="wait_for",
                ignore_status=(404,),
            )
        return True

    def search_vectors(
        self, config, collection_name, query_vector, top_k=10, expr=None
    ):
        k = max(1, min(1000, int(top_k)))
        spec = {"vector": list(query_vector), "k": k}
        terms = vector_filters(expr)
        if terms:
            spec["filter"] = {"bool": {"filter": terms}}
        hits = self.client(config).search(
            index=collection_name,
            body={
                "size": k,
                "_source": list(FIELDS),
                "query": {"knn": {"embedding": spec}},
            },
        )["hits"]["hits"]
        return [
            dict(hit["_source"], id=hit["_id"], distance=hit["_score"]) for hit in hits
        ]

    def delete_by_field_type(self, config, collection_name, field_type):
        return self._delete(
            config, collection_name, {"term": {"field_type": field_type}}
        )

    def delete_by_table_field(
        self, config, collection_name, field_type, table_name=None, field_code=None
    ):
        terms = {
            "field_type": field_type,
            "field_table": table_name,
            "field_code": field_code,
        }
        return self._delete(
            config,
            collection_name,
            {
                "bool": {
                    "filter": [
                        {"term": {k: v}} for k, v in terms.items() if v is not None
                    ]
                }
            },
        )

    def delete_by_table_field_value(
        self, config, collection_name, field_type, table_name, field_code, field_value
    ):
        return self.delete_items(
            config,
            collection_name,
            field_type,
            [
                {
                    "field_table": table_name,
                    "field_code": field_code,
                    "field_value": field_value,
                }
            ],
        )

    def delete_items(self, config, collection_name, field_type, items):
        for item in items:
            terms = {
                "field_type": field_type,
                **{k: item[k] for k in FIELDS[:5] if k in item},
            }
            if len(terms) < 2:
                raise ValueError("删除向量时缺少标识")
            self._delete(
                config,
                collection_name,
                {"bool": {"filter": [{"term": {k: v}} for k, v in terms.items()]}},
            )
        return True
