"""
Elasticsearch 服务 - 管理知识库ES索引和文档操作
"""
import json
import os
import uuid
import logging
from typing import List, Dict, Any, Optional
from elasticsearch import Elasticsearch
from .azure_search_service import AzureAISearchService, is_azure_search_config

logger = logging.getLogger(__name__)

# 调试：打印 ES 原始 JSON 的最大长度（可通过环境变量调大）
_ES_DEBUG_LOG_MAX_CHARS = int(os.getenv("ES_DEBUG_LOG_MAX_CHARS", "20000"))


def _log_es_exception(context: str, e: Exception) -> None:
    """打印 ES 异常详情（BadRequestError 常带 meta.body）。"""
    extra = ""
    for attr in ("body", "message", "info"):
        if hasattr(e, attr):
            extra += f" | {attr}={getattr(e, attr)!r}"
    logger.error("Failed %s: %s%s", context, e, extra, exc_info=True)


def _es_response_to_dict(resp: Any) -> Dict[str, Any]:
    """elasticsearch-py 8 的 ObjectApiResponse / dict 统一成可遍历结构。"""
    if resp is None:
        return {}
    if isinstance(resp, dict):
        return resp
    if hasattr(resp, "body"):
        b = resp.body
        if isinstance(b, dict):
            return b
        if b is not None and hasattr(b, "items"):
            try:
                return dict(b)
            except Exception:
                pass
    if hasattr(resp, "to_dict"):
        try:
            td = resp.to_dict()
            if isinstance(td, dict):
                return td
        except Exception:
            pass
    try:
        return dict(resp)
    except Exception:
        return {"_repr": repr(resp)[:2000]}


def _safe_json_for_log(obj: Any, max_len: Optional[int] = None) -> str:
    max_len = max_len if max_len is not None else _ES_DEBUG_LOG_MAX_CHARS
    try:
        s = json.dumps(obj, ensure_ascii=False, default=str, indent=2)
    except Exception:
        s = repr(obj)
    if len(s) > max_len:
        return s[:max_len] + f"\n... [truncated, total {len(s)} chars; set ES_DEBUG_LOG_MAX_CHARS]"
    return s


def _log_es_search_trace(
    operation: str,
    index_name: str,
    *,
    query_text: str,
    query_dsl: Dict[str, Any],
    size: int,
    response: Any,
    parsed_results: List[Dict[str, Any]],
) -> None:
    """打印一次 search 的完整排查信息：请求 DSL、索引、ES 原始 hits、解析后条数。"""
    body = _es_response_to_dict(response)
    hits_meta = body.get("hits") or {}
    if not isinstance(hits_meta, dict):
        hits_meta = {}
    total_hits = hits_meta.get("total")
    if isinstance(total_hits, dict):
        total_hits = total_hits.get("value", total_hits)
    raw_hits = hits_meta.get("hits") or []
    hits_len = len(raw_hits) if isinstance(raw_hits, list) else 0

    logger.info(
        "ES trace [%s] index=%s | query_text=%r | size=%s | dsl=%s | "
        "hits.total=%s | hits.hits_len=%s | parsed=%s",
        operation,
        index_name,
        query_text,
        size,
        json.dumps(query_dsl, ensure_ascii=False),
        total_hits,
        hits_len,
        len(parsed_results),
    )
    logger.info(
        "ES trace [%s] index=%s | raw response JSON:\n%s",
        operation,
        index_name,
        _safe_json_for_log(body),
    )


def _log_index_doc_count(client: Elasticsearch, index_name: str) -> None:
    """索引文档总数（调用方已确认索引存在；用于排查「match 无命中」）。"""
    try:
        cres = client.count(index=index_name)
        cbody = _es_response_to_dict(cres)
        logger.info("ES index=%s doc_count=%s", index_name, cbody.get("count"))
    except Exception as e:
        logger.warning("ES index=%s count failed: %s", index_name, e)




class ElasticsearchService:
    """Elasticsearch 服务"""

    def __init__(self, config: dict):
        self.host = config.get("host")
        self.port = config.get("port")
        self.user = config.get("username", "")
        self.password = config.get("password", "")
        endpoint = self.host + (f":{self.port}" if self.port else "") if self.host else ""
        self.is_opensearch = bool(endpoint) and (
            endpoint.startswith(("opensearch+http://", "opensearch+https://"))
            or endpoint.rstrip("/") == os.getenv("OPENSEARCH_URL", "").rstrip("/")
        )
        self.is_azure_search = is_azure_search_config(config)
        self._azure_client = AzureAISearchService(config) if self.is_azure_search else None
        if not self.host:
            raise ValueError("ES 地址未配置，请在管理中心配置 ES")
        self._client = None

    def get_client(self) -> Elasticsearch:
        """获取 ES 客户端"""
        if self.is_azure_search:
            raise RuntimeError("Azure AI Search 配置不使用 Elasticsearch 客户端")
        if self._client is None:
            host = self.host
            if self.port:
                host = f"{host}:{self.port}"
            if self.is_opensearch:
                from opensearchpy import OpenSearch
                self._client = OpenSearch(
                    hosts=[host.removeprefix("opensearch+")],
                    http_auth=(self.user, self.password) if self.user else None,
                    timeout=30, max_retries=0, retry_on_timeout=False,
                )
                return self._client
            self._client = Elasticsearch(
                host,
                basic_auth=(self.user, self.password) if self.user else None,
                request_timeout=30,
                max_retries=0,
                retry_on_timeout=False,
            )
        return self._client
    
    def close(self):
        """关闭 ES 连接"""
        if self._azure_client:
            self._azure_client.close()
        if self._client:
            self._client.close()
            self._client = None

    def index_exists(self, index_name: str) -> bool:
        """Only a confirmed missing index is False; lookup errors propagate."""
        if self.is_azure_search:
            return self._azure_client.index_exists(index_name)
        return bool(self.get_client().indices.exists(index=index_name))
    
    def _get_index_name(self, knowledge_base_id: int) -> str:
        """获取知识库对应的索引名称"""
        return f"es_kb{knowledge_base_id}_knowledge"
    
    def _get_table_value_index_name(self, knowledge_base_id: int) -> str:
        """获取表字段值索引名称"""
        return f"es_kb{knowledge_base_id}_table_value"

    @staticmethod
    def _doc_id(*parts: Any) -> str:
        raw = "|".join(str(p or "") for p in parts)
        return str(uuid.uuid5(uuid.NAMESPACE_URL, raw))
    
    def create_knowledge_index(self, knowledge_base_id: int) -> bool:
        """
        创建知识库索引
        
        Args:
            knowledge_base_id: 知识库ID
        
        Returns:
            bool: 是否创建成功
        """
        index_name = self._get_index_name(knowledge_base_id)
        if self.is_azure_search:
            return self._azure_client.create_keyword_index(index_name, [
                {"name": "data_detail", "searchable": True, "filterable": False},
                {"name": "quote_extend", "searchable": False, "filterable": True},
            ])
        client = self.get_client()
        
        try:
            # 检查索引是否存在
            if client.indices.exists(index=index_name):
                logger.info(f"Index {index_name} already exists")
                return True
            
            # 创建索引映射
            mapping = {
                "mappings": {
                    "properties": {
                        "id": {"type": "keyword"},
                        "data_detail": {
                            "type": "text",
                            "analyzer": "cjk" if self.is_opensearch else "ik_max_word",
                            "search_analyzer": "cjk" if self.is_opensearch else "ik_smart"
                        },
                        "quote_extend": {"type": "keyword"}
                    }
                }
            }
            
            # elasticsearch-py 8.x：使用 mappings 顶层参数，避免 body= 与 Serverless 不兼容导致 400
            if self.is_opensearch:
                client.indices.create(index=index_name, body=mapping)
            else:
                client.indices.create(index=index_name, mappings=mapping["mappings"])
            logger.info(f"Index {index_name} created successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create index {index_name}: {e}")
            return False
    
    def delete_knowledge_index(self, knowledge_base_id: int) -> bool:
        """删除知识库索引"""
        index_name = self._get_index_name(knowledge_base_id)
        if self.is_azure_search:
            return self._azure_client.delete_all_documents(index_name)
        client = self.get_client()
        
        try:
            if client.indices.exists(index=index_name):
                client.indices.delete(index=index_name)
                logger.info(f"Index {index_name} deleted")
            return True
        except Exception as e:
            logger.error(f"Failed to delete index {index_name}: {e}")
            return False
    
    def index_knowledge_terms(
        self, 
        knowledge_base_id: int, 
        terms: List[Dict[str, str]]
    ) -> bool:
        """
        批量索引知识词条
        
        Args:
            knowledge_base_id: 知识库ID
            terms: 词条列表，每个词条包含 {"term_name": "...", "term_value": "..."}
        
        Returns:
            bool: 是否索引成功
        """
        index_name = self._get_index_name(knowledge_base_id)
        if self.is_azure_search:
            try:
                if not self.create_knowledge_index(knowledge_base_id):
                    raise Exception(f"Failed to create index {index_name}")
                if not self._azure_client.delete_all_documents(index_name):
                    return False
                docs = [
                    {
                        "id": str(uuid.uuid4()),
                        "data_detail": term["term_name"],
                        "quote_extend": term["term_value"],
                    }
                    for term in terms
                ]
                return self._azure_client.upload_documents(index_name, docs)
            except Exception as e:
                logger.error("Failed to index knowledge terms to Azure AI Search %s: %s", index_name, e)
                return False
        client = self.get_client()
        
        try:
            # 确保索引存在
            if not client.indices.exists(index=index_name):
                if not self.create_knowledge_index(knowledge_base_id):
                    raise Exception(f"Failed to create index {index_name}")
            
            # 删除旧数据（清空索引）
            if self.is_opensearch:
                client.delete_by_query(index=index_name, body={"query": {"match_all": {}}})
            else:
                client.delete_by_query(index=index_name, query={"match_all": {}})
            logger.info(f"Deleted old documents from {index_name}")
            
            # 批量插入新数据
            if not terms:
                logger.info(f"No terms to index for knowledge base {knowledge_base_id}")
                return True
            
            bulk_body = []
            for term in terms:
                doc = {
                    "id": str(uuid.uuid4()),
                    "data_detail": term["term_name"],
                    "quote_extend": term["term_value"]
                }
                bulk_body.append({"index": {"_index": index_name}})
                bulk_body.append(doc)
            
            # 批量写入
            response = client.bulk(body=bulk_body, refresh=True)
            
            if response.get("errors"):
                logger.error(f"Bulk indexing had errors: {response}")
                return False
            
            logger.info(f"Indexed {len(terms)} knowledge terms to {index_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to index knowledge terms to {index_name}: {e}")
            return False

    def upsert_knowledge_terms(
        self,
        knowledge_base_id: int,
        terms: List[Dict[str, str]],
    ) -> bool:
        index_name = self._get_index_name(knowledge_base_id)
        if self.is_azure_search:
            if not self.create_knowledge_index(knowledge_base_id):
                return False
            docs = [
                {
                    "id": term.get("id") or self._doc_id(index_name, term.get("term_key") or term.get("term_name")),
                    "data_detail": term["term_name"],
                    "quote_extend": term["term_value"],
                }
                for term in terms
            ]
            return self._azure_client.upload_documents(index_name, docs)
        client = self.get_client()
        try:
            if not client.indices.exists(index=index_name):
                if not self.create_knowledge_index(knowledge_base_id):
                    raise Exception(f"Failed to create index {index_name}")
            if not terms:
                return True
            bulk_body = []
            for term in terms:
                doc_id = term.get("id") or self._doc_id(index_name, term.get("term_key") or term.get("term_name"))
                bulk_body.append({"index": {"_index": index_name, "_id": doc_id}})
                bulk_body.append({
                    "id": doc_id,
                    "data_detail": term["term_name"],
                    "quote_extend": term["term_value"],
                })
            response = client.bulk(body=bulk_body, refresh=True)
            if response.get("errors"):
                logger.error("Bulk upsert knowledge terms had errors: %s", response)
                return False
            return True
        except Exception as e:
            logger.error("Failed to upsert knowledge terms to %s: %s", index_name, e)
            return False

    def delete_knowledge_terms_by_ids(self, knowledge_base_id: int, ids: List[str]) -> bool:
        index_name = self._get_index_name(knowledge_base_id)
        if not ids:
            return True
        if self.is_azure_search:
            try:
                return self._azure_client.delete_documents(index_name, ids)
            except Exception as e:
                logger.error("Failed to delete knowledge terms from Azure AI Search %s: %s", index_name, e)
                return False
        client = self.get_client()
        try:
            if not client.indices.exists(index=index_name):
                return True
            bulk_body = [{"delete": {"_index": index_name, "_id": i}} for i in ids]
            response = client.bulk(body=bulk_body, refresh=True)
            return not response.get("errors")
        except Exception as e:
            logger.error("Failed to delete knowledge terms from %s: %s", index_name, e)
            return False
    
    def search_knowledge_terms(
        self, 
        knowledge_base_id: int, 
        query: str, 
        top_k: int = 10
    ) -> List[Dict[str, Any]]:
        """
        搜索知识词条
        
        Args:
            knowledge_base_id: 知识库ID
            query: 查询文本
            top_k: 返回结果数量
        
        Returns:
            List[Dict]: 搜索结果列表
        """
        index_name = self._get_index_name(knowledge_base_id)
        if self.is_azure_search:
            try:
                return [
                    {
                        "id": row.get("id"),
                        "data_detail": row.get("data_detail"),
                        "quote_extend": row.get("quote_extend"),
                        "score": row.get("score"),
                    }
                    for row in self._azure_client.keyword_search(index_name, query, ["data_detail"], top_k)
                ]
            except Exception as e:
                logger.error("Failed to search knowledge terms in Azure AI Search %s: %s", index_name, e)
                return []
        client = self.get_client()
        
        try:
            if not client.indices.exists(index=index_name):
                logger.warning("Index %s does not exist", index_name)
                return []


            q = (query or "").strip()
            if not q:
                logger.info("ES search_knowledge_terms: empty query, skip")
                return []

            query_dsl = {"match": {"data_detail": q}}
            # elasticsearch-py 8.x：使用 query= / size=，勿用 body=（阿里云 ES Serverless 易返回 400）
            if self.is_opensearch:
                response = client.search(index=index_name, body={"query": query_dsl, "size": top_k})
            else:
                response = client.search(index=index_name, query=query_dsl, size=top_k)

            body = _es_response_to_dict(response)
            hits_list = (body.get("hits") or {}).get("hits") or []

            results = []
            for hit in hits_list:
                if not isinstance(hit, dict):
                    continue
                source = hit.get("_source", {})
                results.append({
                    "id": source.get("id"),
                    "data_detail": source.get("data_detail"),
                    "quote_extend": source.get("quote_extend"),
                    "score": hit.get("_score")
                })

            _log_es_search_trace(
                "search_knowledge_terms",
                index_name,
                query_text=q,
                query_dsl=query_dsl,
                size=top_k,
                response=response,
                parsed_results=results,
            )

            return results
            
        except Exception as e:
            _log_es_exception(f"search knowledge terms in {index_name}", e)
            return []
    
    def create_table_value_index(self, knowledge_base_id: int) -> bool:
        """
        创建表字段值索引
        
        Args:
            knowledge_base_id: 知识库ID
        
        Returns:
            bool: 是否创建成功
        """
        index_name = self._get_table_value_index_name(knowledge_base_id)
        if self.is_azure_search:
            return self._azure_client.create_keyword_index(index_name, [
                {"name": "field_table", "searchable": False, "filterable": True},
                {"name": "field_code", "searchable": False, "filterable": True},
                {"name": "field_value", "searchable": True, "filterable": False},
            ])
        client = self.get_client()
        
        try:
            # 检查索引是否存在
            if client.indices.exists(index=index_name):
                logger.info(f"Index {index_name} already exists")
                return True
            
            # 创建索引映射
            mapping = {
                "mappings": {
                    "properties": {
                        "id": {"type": "keyword"},
                        "field_table": {"type": "keyword"},
                        "field_code": {"type": "keyword"},
                        "field_value": {
                            "type": "text",
                            "analyzer": "cjk" if self.is_opensearch else "ik_max_word",
                            "search_analyzer": "cjk" if self.is_opensearch else "ik_smart"
                        }
                    }
                }
            }
            
            if self.is_opensearch:
                client.indices.create(index=index_name, body=mapping)
            else:
                client.indices.create(index=index_name, mappings=mapping["mappings"])
            logger.info(f"Index {index_name} created successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create index {index_name}: {e}")
            return False

    def delete_table_value_index(self, knowledge_base_id: int) -> bool:
        """删除表字段值索引。"""
        index_name = self._get_table_value_index_name(knowledge_base_id)
        if self.is_azure_search:
            return self._azure_client.delete_all_documents(index_name)
        client = self.get_client()
        try:
            if client.indices.exists(index=index_name):
                client.indices.delete(index=index_name)
                logger.info("Index %s deleted", index_name)
            return True
        except Exception as e:
            logger.error("Failed to delete index %s: %s", index_name, e)
            return False
    
    def index_table_values(
        self, 
        knowledge_base_id: int, 
        values: List[Dict[str, str]]
    ) -> bool:
        """
        批量索引表字段值
        
        Args:
            knowledge_base_id: 知识库ID
            values: 值列表，每个包含 {"field_table": "...", "field_code": "...", "field_value": "..."}
        
        Returns:
            bool: 是否索引成功
        """
        index_name = self._get_table_value_index_name(knowledge_base_id)
        if self.is_azure_search:
            try:
                if not self.create_table_value_index(knowledge_base_id):
                    raise Exception(f"Failed to create index {index_name}")
                if not self._azure_client.delete_all_documents(index_name):
                    return False
                docs = [
                    {
                        "id": str(uuid.uuid4()),
                        "field_table": value["field_table"],
                        "field_code": value["field_code"],
                        "field_value": value["field_value"],
                    }
                    for value in values
                ]
                return self._azure_client.upload_documents(index_name, docs)
            except Exception as e:
                logger.error("Failed to index table values to Azure AI Search %s: %s", index_name, e)
                return False
        client = self.get_client()
        
        try:
            # 确保索引存在
            if not client.indices.exists(index=index_name):
                if not self.create_table_value_index(knowledge_base_id):
                    raise Exception(f"Failed to create index {index_name}")
            
            # 删除旧数据（清空索引）
            if self.is_opensearch:
                client.delete_by_query(index=index_name, body={"query": {"match_all": {}}})
            else:
                client.delete_by_query(index=index_name, query={"match_all": {}})
            logger.info(f"Deleted old documents from {index_name}")
            
            # 批量插入新数据
            if not values:
                logger.info(f"No values to index for knowledge base {knowledge_base_id}")
                return True
            
            bulk_body = []
            for value in values:
                doc = {
                    "id": str(uuid.uuid4()),
                    "field_table": value["field_table"],
                    "field_code": value["field_code"],
                    "field_value": value["field_value"]
                }
                bulk_body.append({"index": {"_index": index_name}})
                bulk_body.append(doc)
            
            # 批量写入
            response = client.bulk(body=bulk_body, refresh=True)
            
            if response.get("errors"):
                logger.error(f"Bulk indexing had errors: {response}")
                return False
            
            logger.info(f"Indexed {len(values)} table values to {index_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to index table values to {index_name}: {e}")
            return False

    def upsert_table_values(
        self,
        knowledge_base_id: int,
        values: List[Dict[str, str]],
    ) -> bool:
        index_name = self._get_table_value_index_name(knowledge_base_id)
        if self.is_azure_search:
            try:
                if not self.create_table_value_index(knowledge_base_id):
                    raise Exception(f"Failed to create index {index_name}")
                docs = [
                    {
                        "id": value.get("id") or self._doc_id(index_name, value.get("field_code"), value.get("field_value")),
                        "field_table": value["field_table"],
                        "field_code": value["field_code"],
                        "field_value": value["field_value"],
                    }
                    for value in values
                ]
                return self._azure_client.upload_documents(index_name, docs)
            except Exception as e:
                logger.error("Failed to upsert table values to Azure AI Search %s: %s", index_name, e)
                return False
        client = self.get_client()
        try:
            if not client.indices.exists(index=index_name):
                if not self.create_table_value_index(knowledge_base_id):
                    raise Exception(f"Failed to create index {index_name}")
            if not values:
                return True
            bulk_body = []
            for value in values:
                doc_id = value.get("id") or self._doc_id(index_name, value.get("field_code"), value.get("field_value"))
                bulk_body.append({"index": {"_index": index_name, "_id": doc_id}})
                bulk_body.append({
                    "id": doc_id,
                    "field_table": value["field_table"],
                    "field_code": value["field_code"],
                    "field_value": value["field_value"],
                })
            response = client.bulk(body=bulk_body, refresh=True)
            if response.get("errors"):
                logger.error("Bulk upsert table values had errors: %s", response)
                return False
            return True
        except Exception as e:
            logger.error("Failed to upsert table values to %s: %s", index_name, e)
            return False

    def delete_table_values_by_ids(self, knowledge_base_id: int, ids: List[str]) -> bool:
        index_name = self._get_table_value_index_name(knowledge_base_id)
        if not ids:
            return True
        if self.is_azure_search:
            try:
                return self._azure_client.delete_documents(index_name, ids)
            except Exception as e:
                logger.error("Failed to delete table values from Azure AI Search %s: %s", index_name, e)
                return False
        client = self.get_client()
        try:
            if not client.indices.exists(index=index_name):
                return True
            bulk_body = [{"delete": {"_index": index_name, "_id": i}} for i in ids]
            response = client.bulk(body=bulk_body, refresh=True)
            return not response.get("errors")
        except Exception as e:
            logger.error("Failed to delete table values from %s: %s", index_name, e)
            return False
    
    def search_table_values(
        self, 
        knowledge_base_id: int, 
        query: str, 
        top_k: int = 10,
        *,
        field_table: Optional[str] = None,
        field_code: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        搜索表字段值
        
        Args:
            knowledge_base_id: 知识库ID
            query: 查询文本
            top_k: 返回结果数量
            field_table: 可选物理表过滤，在 TopK 之前执行
            field_code: 可选完整字段编码过滤，在 TopK 之前执行
        
        Returns:
            List[Dict]: 搜索结果列表
        """
        index_name = self._get_table_value_index_name(knowledge_base_id)
        scope = {k: v for k, v in (("field_table", field_table), ("field_code", field_code)) if v}
        if self.is_azure_search:
            try:
                filter_expr = " and ".join(
                    f"{key} eq '" + str(value).replace("'", "''") + "'"
                    for key, value in scope.items()
                )
                kwargs = {"filter_expr": filter_expr} if filter_expr else {}
                return [
                    {
                        "id": row.get("id"),
                        "field_table": row.get("field_table"),
                        "field_code": row.get("field_code"),
                        "field_value": row.get("field_value"),
                        "score": row.get("score"),
                    }
                    for row in self._azure_client.keyword_search(index_name, query, ["field_value"], top_k, **kwargs)
                ]
            except Exception as e:
                logger.error("Failed to search table values in Azure AI Search %s: %s", index_name, e)
                return []
        client = self.get_client()
        
        try:
            if not client.indices.exists(index=index_name):
                logger.warning("Index %s does not exist", index_name)
                return []


            q = (query or "").strip()
            if not q:
                logger.info("ES search_table_values: empty query, skip")
                return []

            query_dsl = {"match": {"field_value": q}}
            if scope:
                query_dsl = {"bool": {
                    "must": [query_dsl],
                    "filter": [{"term": {key: value}} for key, value in scope.items()],
                }}
            if self.is_opensearch:
                response = client.search(index=index_name, body={"query": query_dsl, "size": top_k})
            else:
                response = client.search(index=index_name, query=query_dsl, size=top_k)

            body = _es_response_to_dict(response)
            hits_list = (body.get("hits") or {}).get("hits") or []

            results = []
            for hit in hits_list:
                if not isinstance(hit, dict):
                    continue
                source = hit.get("_source", {})
                results.append({
                    "id": source.get("id"),
                    "field_table": source.get("field_table"),
                    "field_code": source.get("field_code"),
                    "field_value": source.get("field_value"),
                    "score": hit.get("_score")
                })

            _log_es_search_trace(
                "search_table_values",
                index_name,
                query_text=q,
                query_dsl=query_dsl,
                size=top_k,
                response=response,
                parsed_results=results,
            )

            return results
            
        except Exception as e:
            _log_es_exception(f"search table values in {index_name}", e)
            return []
