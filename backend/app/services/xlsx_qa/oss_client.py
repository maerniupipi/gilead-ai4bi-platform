"""
XLSX 表格智能问答 · 对象存储封装

一期实现阿里云 OSS；预留 StorageClient 抽象，后续新增 S3 / MinIO 只需实现同 Protocol。

配置读取自环境变量（或「项目管理」中 OSS 配置；以下为可选兜底变量）：
  XLSX_QA_OSS_ENDPOINT           e.g. oss-cn-shanghai.aliyuncs.com
  XLSX_QA_OSS_BUCKET             e.g. shaox
  XLSX_QA_OSS_ACCESS_KEY_ID
  XLSX_QA_OSS_ACCESS_KEY_SECRET
  XLSX_QA_OSS_PREFIX             默认 xlsx-qa/
  XLSX_QA_OSS_DOWNLOAD_EXPIRES   下载签名 URL 过期秒数，默认 900
"""
from __future__ import annotations

import datetime as _dt
import logging
import os
import uuid
from typing import Protocol

import oss2  # type: ignore[import]

logger = logging.getLogger(__name__)


class StorageClient(Protocol):
    """对象存储抽象，未来要支持 S3 / MinIO 时实现此 Protocol 即可。"""

    def put_bytes(self, object_key: str, data: bytes, content_type: str) -> str: ...

    def delete_object(self, object_key: str) -> None: ...

    def generate_presigned_url(self, object_key: str, expires: int = 900) -> str: ...


class _OssClient:
    """阿里云 OSS 客户端（懒加载；首次使用时才创建 Bucket）。"""

    def __init__(self) -> None:
        self._endpoint = os.getenv("XLSX_QA_OSS_ENDPOINT", "").strip()
        self._bucket_name = os.getenv("XLSX_QA_OSS_BUCKET", "").strip()
        self._ak = os.getenv("XLSX_QA_OSS_ACCESS_KEY_ID", "").strip()
        self._sk = os.getenv("XLSX_QA_OSS_ACCESS_KEY_SECRET", "").strip()
        self._prefix = (os.getenv("XLSX_QA_OSS_PREFIX", "xlsx-qa/") or "").lstrip("/")
        self._default_expires = int(os.getenv("XLSX_QA_OSS_DOWNLOAD_EXPIRES", "900") or 900)
        self._bucket: oss2.Bucket | None = None

    @property
    def prefix(self) -> str:
        return self._prefix

    @property
    def default_expires(self) -> int:
        return self._default_expires

    def _ensure(self) -> oss2.Bucket:
        if self._bucket is not None:
            return self._bucket
        missing = [
            name
            for name, val in (
                ("XLSX_QA_OSS_ENDPOINT", self._endpoint),
                ("XLSX_QA_OSS_BUCKET", self._bucket_name),
                ("XLSX_QA_OSS_ACCESS_KEY_ID", self._ak),
                ("XLSX_QA_OSS_ACCESS_KEY_SECRET", self._sk),
            )
            if not val
        ]
        if missing:
            raise RuntimeError(
                f"XLSX-QA OSS 未配置完整，缺少环境变量: {', '.join(missing)}"
            )
        # endpoint 若只填了 Region（如 oss-cn-shanghai.aliyuncs.com），自动补 https://
        endpoint = self._endpoint
        if not endpoint.startswith(("http://", "https://")):
            endpoint = f"https://{endpoint}"
        auth = oss2.Auth(self._ak, self._sk)
        self._bucket = oss2.Bucket(auth, endpoint, self._bucket_name)
        return self._bucket

    # ------------------------------------------------------------------
    # StorageClient impl
    # ------------------------------------------------------------------

    def put_bytes(self, object_key: str, data: bytes, content_type: str) -> str:
        bucket = self._ensure()
        headers = {"Content-Type": content_type} if content_type else None
        bucket.put_object(object_key, data, headers=headers)
        logger.info("xlsx_qa.oss.put key=%s size=%s", object_key, len(data))
        return object_key

    def delete_object(self, object_key: str) -> None:
        if not object_key:
            return
        try:
            bucket = self._ensure()
            bucket.delete_object(object_key)
            logger.info("xlsx_qa.oss.delete key=%s", object_key)
        except Exception as exc:  # noqa: BLE001 —— 删除失败不阻断主流程
            logger.warning("xlsx_qa.oss.delete failed key=%s err=%s", object_key, exc)

    def generate_presigned_url(self, object_key: str, expires: int | None = None) -> str:
        bucket = self._ensure()
        # 强制指定下载文件名（浏览器 Save As），避免带路径
        return bucket.sign_url(
            "GET",
            object_key,
            expires or self._default_expires,
            slash_safe=True,
        )

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------

    def build_module_file_key(self, module_id: int, file_name: str) -> str:
        """生成带命名空间的 object key。

        结构：{prefix}modules/{module_id}/{yyyymmdd}/{uuid}-{filename}
        """
        ymd = _dt.datetime.utcnow().strftime("%Y%m%d")
        safe_name = _sanitize_filename(file_name)
        short_id = uuid.uuid4().hex[:12]
        return f"{self._prefix}modules/{module_id}/{ymd}/{short_id}-{safe_name}"

    def build_ppt_file_key(self, module_id: int, file_name: str) -> str:
        """生成 PPT 导出文件的 OSS key。

        结构：{prefix}modules/{module_id}/ppt/{yyyymmdd}/{uuid}-{filename}
        """
        ymd = _dt.datetime.utcnow().strftime("%Y%m%d")
        safe_name = _sanitize_filename(file_name)
        short_id = uuid.uuid4().hex[:12]
        return f"{self._prefix}modules/{module_id}/ppt/{ymd}/{short_id}-{safe_name}"

    def build_module_logo_key(self, module_id: int, file_name: str) -> str:
        """生成模块 Logo 的 OSS key。

        结构：{prefix}modules/{module_id}/logo/{uuid}-{filename}
        """
        safe_name = _sanitize_filename(file_name)
        short_id = uuid.uuid4().hex[:12]
        return f"{self._prefix}modules/{module_id}/logo/{short_id}-{safe_name}"


def _sanitize_filename(name: str) -> str:
    """OSS key 不允许裸 /，顺便压缩空格；保留中文便于下载时可见。"""
    s = (name or "file.xlsx").strip().replace("/", "_").replace("\\", "_")
    s = " ".join(s.split())
    return s or "file.xlsx"


# 模块级单例；便于在 service 层直接 `from .oss_client import storage`
storage: _OssClient = _OssClient()

__all__ = ["StorageClient", "storage"]
