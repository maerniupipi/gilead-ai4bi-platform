"""
Embedding 服务 - 调用向量模型生成向量
"""
import logging
import os
import time
from urllib.parse import urlencode
import requests
from typing import List
from ...core.model_stream import ModelCall
from ...core.resources import embedding_session

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Embedding 服务，所有配置从数据库读取"""

    def __init__(self, config: dict):
        self.last_usage = {}
        self.api_key = (config.get("api_key") or "").strip()
        self.model = config.get("model", "text-embedding-v4")
        self.dimension = int(config.get("dimension", 1024))
        self.base_url = config.get("base_url")
        self.provider = (config.get("provider") or "").lower()
        self.max_request_batch_size = int(config.get("max_batch_size") or self._default_max_batch_size())
        self.request_timeout = float(
            config.get("timeout_seconds")
            or config.get("request_timeout")
            or os.getenv("EMBEDDING_REQUEST_TIMEOUT", "60")
        )
        if not self.base_url or not self.base_url.startswith(("http://", "https://")):
            raise ValueError(f"向量模型 base_url 未配置或无效（当前值: {self.base_url!r}），请在管理中心配置向量模型")
        self.endpoint = self.base_url

    def _default_max_batch_size(self) -> int:
        if self.provider in {"dashscope", "aliyun", "ali"}:
            return 10
        return 10
    
    def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        获取文本的向量表示
        
        Args:
            texts: 文本列表
        
        Returns:
            向量列表，每个向量是一个浮点数数组
        """
        if not texts:
            return []
        
        if not self.api_key:
            raise ValueError("向量模型 API Key 未配置，请在管理中心配置向量模型")
        try:
            self.api_key.encode("latin-1")
        except UnicodeEncodeError as exc:
            raise ValueError("向量模型 API Key 配置错误：API Key 不能包含中文或其他非 ASCII 字符，请重新填写真实密钥") from exc
        
        headers = {"Content-Type": "application/json"}
        if self.provider in {"azure", "azure_openai"} or "openai.azure.com" in self.endpoint:
            headers["api-key"] = self.api_key
            if "api-version=" not in self.endpoint:
                sep = "&" if "?" in self.endpoint else "?"
                self.endpoint = f"{self.endpoint}{sep}{urlencode({'api-version': '2024-02-01'})}"
        else:
            headers["Authorization"] = f"Bearer {self.api_key}"
        
        if len(texts) > self.max_request_batch_size:
            vectors = []
            for i in range(0, len(texts), self.max_request_batch_size):
                batch = texts[i:i + self.max_request_batch_size]
                vectors.extend(self._request_embeddings(batch, headers))
                if i + self.max_request_batch_size < len(texts):
                    time.sleep(0.5)
            logger.info(
                "Generated %s embeddings with dimension %s via %s-request batches",
                len(vectors),
                self.dimension,
                self.max_request_batch_size,
            )
            return vectors

        return self._request_embeddings(texts, headers)

    def _request_embeddings(self, texts: List[str], headers: dict) -> List[List[float]]:
        payload = {
            'model': self.model, 'input': texts, 'dimensions': self.dimension,
            'encoding_format': 'float',
        }
        call = ModelCall(payload, operation='embedding', provider=self.provider)
        call.data['input_count'] = len(texts)
        error = None
        try:
            response = embedding_session().post(self.endpoint, headers=headers, json=payload,
                                     timeout=self.request_timeout)
            call.data.update(http_status=response.status_code,
                             provider_request_id=getattr(response, 'headers', {}).get('x-request-id'))
            if response.status_code != 200:
                call.data['response_preview'] = getattr(response, 'text', '')[:2000]
                raise RuntimeError(f'Embedding API error: {response.status_code}')
            result = response.json()
            self.last_usage = result.get("usage") or {}
            if 'data' not in result:
                raise RuntimeError('Invalid embedding response')
            embeddings = sorted(result['data'], key=lambda item: item.get('index', 0))
            vectors = [item['embedding'] for item in embeddings]
            call.data.update(status='succeeded', response_received_ms=call.elapsed(),
                             token_usage=result.get('usage'), vector_count=len(vectors),
                             dimension=self.dimension)
            return vectors
        except BaseException as exc:
            error = exc
            raise
        finally:
            call.finish(error)

    def get_embedding(self, text: str) -> List[float]:
        """获取单个文本的向量"""
        vectors = self.get_embeddings([text])
        return vectors[0] if vectors else None
