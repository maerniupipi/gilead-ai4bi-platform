"""
OSS 存储提供商抽象层

支持：阿里云 OSS / AWS S3 / Azure Blob / MinIO
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Dict, Any

logger = logging.getLogger(__name__)


class OssProvider(ABC):
    """OSS 提供商抽象接口"""

    @abstractmethod
    def test_connection(self, config: Dict[str, Any] | None = None) -> bool:
        """测试连接，返回是否成功"""
        ...

    @abstractmethod
    def put_bytes(self, object_key: str, data: bytes, content_type: str) -> str:
        """上传文件，返回 object key"""
        ...

    @abstractmethod
    def delete_object(self, object_key: str) -> None:
        """删除文件"""
        ...

    @abstractmethod
    def generate_presigned_url(self, object_key: str, expires: int = 900) -> str:
        """生成预签名 URL"""
        ...


class AliyunOssProvider(OssProvider):
    """阿里云 OSS"""

    def __init__(self):
        self._bucket = None
        self._config: Dict[str, Any] = {}

    def _get_bucket(self, config: Dict[str, Any] | None = None):
        import oss2
        cfg = config or self._config
        if self._bucket is not None:
            return self._bucket
        endpoint = cfg.get("endpoint", "")
        if endpoint and not endpoint.startswith(("http://", "https://")):
            endpoint = f"https://{endpoint}"
        bucket_name = cfg.get("bucket", "")
        ak = cfg.get("access_key", "")
        sk = cfg.get("secret_key", "")
        auth = oss2.Auth(ak, sk)
        self._bucket = oss2.Bucket(auth, endpoint, bucket_name)
        return self._bucket

    def test_connection(self, config: Dict[str, Any] | None = None) -> bool:
        try:
            bucket = self._get_bucket(config)
            bucket.get_bucket_info()
            return True
        except Exception as e:
            logger.warning("Aliyun OSS connection test failed: %s", e)
            return False

    def put_bytes(self, object_key: str, data: bytes, content_type: str) -> str:
        bucket = self._get_bucket()
        headers = {"Content-Type": content_type} if content_type else None
        bucket.put_object(object_key, data, headers=headers)
        return object_key

    def delete_object(self, object_key: str) -> None:
        try:
            bucket = self._get_bucket()
            bucket.delete_object(object_key)
        except Exception as e:
            logger.warning("OSS delete failed: %s", e)

    def generate_presigned_url(self, object_key: str, expires: int = 900) -> str:
        bucket = self._get_bucket()
        return bucket.sign_url("GET", object_key, expires, slash_safe=True)


class S3Provider(OssProvider):
    """AWS S3 / 兼容 S3 的存储（MinIO、腾讯云 COS 等）"""

    def __init__(self):
        self._client = None
        self._bucket_name: str = ""
        self._config: Dict[str, Any] = {}

    def _get_client(self, config: Dict[str, Any] | None = None):
        import boto3
        cfg = config or self._config
        if self._client is not None:
            return self._client
        endpoint = cfg.get("endpoint", "")
        region = cfg.get("region", "us-east-1")
        ak = cfg.get("access_key", "")
        sk = cfg.get("secret_key", "")
        self._bucket_name = cfg.get("bucket", "")
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint if endpoint else None,
            region_name=region,
            aws_access_key_id=ak,
            aws_secret_access_key=sk,
        )
        return self._client

    def test_connection(self, config: Dict[str, Any] | None = None) -> bool:
        try:
            cfg = config or self._config
            client = self._get_client(config)
            bucket_name = cfg.get("bucket", "")
            client.head_bucket(Bucket=bucket_name)
            return True
        except Exception as e:
            logger.warning("S3 connection test failed: %s", e)
            return False

    def put_bytes(self, object_key: str, data: bytes, content_type: str) -> str:
        client = self._get_client()
        client.put_object(
            Bucket=self._bucket_name,
            Key=object_key,
            Body=data,
            ContentType=content_type or "application/octet-stream",
        )
        return object_key

    def delete_object(self, object_key: str) -> None:
        try:
            client = self._get_client()
            client.delete_object(Bucket=self._bucket_name, Key=object_key)
        except Exception as e:
            logger.warning("S3 delete failed: %s", e)

    def generate_presigned_url(self, object_key: str, expires: int = 900) -> str:
        client = self._get_client()
        return client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket_name, "Key": object_key},
            ExpiresIn=expires,
        )


class MinioProvider(S3Provider):
    """MinIO（兼容 S3 API）"""
    pass


class AzureBlobProvider(OssProvider):
    """Azure Blob Storage"""

    def __init__(self):
        self._container_client = None
        self._container_name: str = ""
        self._config: Dict[str, Any] = {}

    def _get_container_client(self, config: Dict[str, Any] | None = None):
        from azure.storage.blob import BlobServiceClient
        cfg = config or self._config
        if self._container_client is not None:
            return self._container_client
        conn_str = cfg.get("endpoint", "")  # Azure uses connection string
        account_name = cfg.get("access_key", "")
        account_key = cfg.get("secret_key", "")
        self._container_name = cfg.get("bucket", "")
        if conn_str:
            self._container_client = BlobServiceClient.from_connection_string(conn_str)
        elif account_name and account_key:
            account_url = f"https://{account_name}.blob.core.windows.net"
            self._container_client = BlobServiceClient(account_url, credential=account_key)
        else:
            raise ValueError("Azure Blob 需要配置连接字符串或账户凭据")
        return self._container_client

    def test_connection(self, config: Dict[str, Any] | None = None) -> bool:
        try:
            client = self._get_container_client(config)
            container_client = client.get_container_client(self._container_name)
            container_client.get_container_properties()
            return True
        except Exception as e:
            logger.warning("Azure Blob connection test failed: %s", e)
            return False

    def put_bytes(self, object_key: str, data: bytes, content_type: str) -> str:
        client = self._get_container_client()
        blob_client = client.get_blob_client(container=self._container_name, blob=object_key)
        blob_client.upload_blob(data, overwrite=True, content_type=content_type or "application/octet-stream")
        return object_key

    def delete_object(self, object_key: str) -> None:
        try:
            client = self._get_container_client()
            blob_client = client.get_blob_client(container=self._container_name, blob=object_key)
            blob_client.delete_blob()
        except Exception as e:
            logger.warning("Azure Blob delete failed: %s", e)

    def generate_presigned_url(self, object_key: str, expires: int = 900) -> str:
        client = self._get_container_client()
        blob_client = client.get_blob_client(container=self._container_name, blob=object_key)
        return blob_client.url


class UnsupportedOssProvider(OssProvider):
    """不支持的 Provider"""

    def test_connection(self, config: Dict[str, Any] | None = None) -> bool:
        raise NotImplementedError(f"Provider not supported: {(config or {}).get('provider', 'unknown')}")

    def put_bytes(self, object_key: str, data: bytes, content_type: str) -> str:
        raise NotImplementedError("Provider not supported")

    def delete_object(self, object_key: str) -> None:
        raise NotImplementedError("Provider not supported")

    def generate_presigned_url(self, object_key: str, expires: int = 900) -> str:
        raise NotImplementedError("Provider not supported")


# Provider 类注册表（返回新实例，避免状态污染）
_PROVIDER_CLASS_MAP: Dict[str, type[OssProvider]] = {
    "aliyun": AliyunOssProvider,
    "s3": S3Provider,
    "minio": MinioProvider,
    "azure": AzureBlobProvider,
}


def get_oss_provider(provider: str) -> OssProvider:
    """根据 provider 名称获取对应的实现（每次返回新实例）"""
    cls = _PROVIDER_CLASS_MAP.get(provider)
    if cls is None:
        return UnsupportedOssProvider()
    inst = cls()
    return inst
