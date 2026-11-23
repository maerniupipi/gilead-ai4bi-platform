"""
通用 OSS 客户端 — 从数据库读取活跃配置，支持多 Provider

用法：
    from app.services.oss.client import resolve_active_storage
    storage = resolve_active_storage(db, space_id=1)
    storage.put_bytes(key, data, content_type)
    url = storage.generate_presigned_url(key)
    storage.delete_object(key)
    key = storage.build_module_file_key(module_id, filename)
"""
from __future__ import annotations

import datetime as _dt
import logging
import uuid
from typing import Dict, Any

from sqlalchemy.orm import Session

from ...schemas.oss_config import OssConfigResponse
from ...services.oss.providers import (
    AliyunOssProvider,
    S3Provider,
    MinioProvider,
    AzureBlobProvider,
    OssProvider,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------

def _sanitize_filename(name: str) -> str:
    """OSS key 不允许裸 /，顺便压缩空格；保留中文便于下载时可见。"""
    s = (name or "file.xlsx").strip().replace("/", "_").replace("\\", "_")
    s = " ".join(s.split())
    return s or "file.xlsx"


# ---------------------------------------------------------------------------
# Provider 工厂
# ---------------------------------------------------------------------------

_PROVIDER_MAP = {
    "aliyun": AliyunOssProvider,
    "s3": S3Provider,
    "minio": MinioProvider,
    "azure": AzureBlobProvider,
}


def _build_provider(cfg: Dict[str, Any]) -> OssProvider:
    provider = cfg.get("provider", "aliyun")
    cls = _PROVIDER_MAP.get(provider)
    if cls is None:
        raise ValueError(f"不支持的 OSS Provider: {provider}")
    inst = cls()
    # 注入配置（每个 provider 的 _ensure / _get_client 依赖这些）
    inst._config = cfg
    return inst


# ---------------------------------------------------------------------------
# OssStorage — 通用存储客户端
# ---------------------------------------------------------------------------

class OssStorage:
    """
    通用的 OSS 存储客户端。

    支持 aliyun / s3 / minio / azure 四种 Provider。
    提供与旧的 _OssClient 完全兼容的接口（put_bytes / delete_object /
    generate_presigned_url / build_module_file_key / prefix / default_expires）。
    """

    def __init__(
        self,
        provider: OssProvider,
        config: OssConfigResponse,
        *,
        default_expires: int = 900,
    ) -> None:
        self._provider = provider
        self._config = config
        self._default_expires = default_expires

    @property
    def prefix(self) -> str:
        return self._config.prefix or ""

    @property
    def default_expires(self) -> int:
        return self._default_expires

    def put_bytes(self, object_key: str, data: bytes, content_type: str) -> str:
        return self._provider.put_bytes(object_key, data, content_type)

    def delete_object(self, object_key: str) -> None:
        return self._provider.delete_object(object_key)

    def generate_presigned_url(self, object_key: str, expires: int | None = None) -> str:
        return self._provider.generate_presigned_url(
            object_key, expires or self._default_expires
        )

    def build_module_file_key(self, module_id: int, file_name: str) -> str:
        """
        生成带命名空间的 object key。
        结构：{prefix}modules/{module_id}/{yyyymmdd}/{uuid}-{filename}
        """
        ymd = _dt.datetime.utcnow().strftime("%Y%m%d")
        safe_name = _sanitize_filename(file_name)
        short_id = uuid.uuid4().hex[:12]
        prefix = (self.prefix or "").rstrip("/")
        p = f"{prefix}/modules/{module_id}/{ymd}/{short_id}-{safe_name}" if prefix else f"modules/{module_id}/{ymd}/{short_id}-{safe_name}"
        return p

    def build_ppt_file_key(self, module_id: int, file_name: str) -> str:
        """PPT 导出文件 key：{prefix}modules/{module_id}/ppt/{yyyymmdd}/{uuid}-{filename}"""
        ymd = _dt.datetime.utcnow().strftime("%Y%m%d")
        safe_name = _sanitize_filename(file_name)
        short_id = uuid.uuid4().hex[:12]
        prefix = (self.prefix or "").rstrip("/")
        p = f"{prefix}/modules/{module_id}/ppt/{ymd}/{short_id}-{safe_name}" if prefix else f"modules/{module_id}/ppt/{ymd}/{short_id}-{safe_name}"
        return p

    def build_module_logo_key(self, module_id: int, file_name: str) -> str:
        """模块 Logo key：{prefix}modules/{module_id}/logo/{uuid}-{filename}"""
        safe_name = _sanitize_filename(file_name)
        short_id = uuid.uuid4().hex[:12]
        prefix = (self.prefix or "").rstrip("/")
        p = f"{prefix}/modules/{module_id}/logo/{short_id}-{safe_name}" if prefix else f"modules/{module_id}/logo/{short_id}-{safe_name}"
        return p


# ---------------------------------------------------------------------------
# OSS 配置解析为 provider dict
# ---------------------------------------------------------------------------

def _config_to_dict(cfg: OssConfigResponse) -> Dict[str, Any]:
    return {
        "provider": cfg.provider,
        "endpoint": cfg.endpoint,
        "bucket": cfg.bucket,
        "access_key": cfg.access_key,
        "secret_key": cfg.secret_key,
        "region": cfg.region,
    }


# ---------------------------------------------------------------------------
# 核心入口
# ---------------------------------------------------------------------------

def get_active_storage(
    db: Session,
    space_id: int | None = None,
    *,
    default_expires: int = 900,
) -> OssStorage:
    """
    从数据库获取当前激活的 OSS 配置，返回 OssStorage 实例。

    若未配置 OSS，返回 None（调用方应给出明确提示）。
    若配置了但 Provider 不支持，抛出 ValueError。
    """
    from ...repositories.oss_config import OssConfigRepository

    cfg_db = OssConfigRepository.get_default(db, space_id)
    if not cfg_db:
        return None

    cfg = OssConfigResponse.model_validate(cfg_db)
    provider_cfg = _config_to_dict(cfg)
    provider = _build_provider(provider_cfg)

    return OssStorage(provider, cfg, default_expires=default_expires)


def resolve_active_storage(
    db: Session,
    space_id: int | None = None,
    *,
    default_expires: int = 900,
) -> OssStorage:
    """
    从数据库获取当前激活的 OSS 配置。
    若未配置，抛出 HTTPException 提示用户去绑定。
    """
    storage = get_active_storage(db, space_id, default_expires=default_expires)
    if storage is None:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=503,
            detail="OSS 未配置，请前往「管理中心 → 对象存储」进行配置",
        )
    return storage
