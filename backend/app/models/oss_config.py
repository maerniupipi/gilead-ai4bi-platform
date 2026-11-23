"""
OSS 对象存储配置数据模型
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, UniqueConstraint
from sqlalchemy.sql import func
from ..core.database import Base


class OssConfig(Base):
    """OSS 配置表：默认仅允许启用一个"""
    __tablename__ = "oss_configs"
    __table_args__ = (
        UniqueConstraint("is_default", "space_id", name="uq_oss_default_flag_per_space"),
    )

    id = Column(Integer, primary_key=True, index=True, comment="主键ID")
    space_id = Column(Integer, nullable=False, default=1, index=True, comment="所属空间ID")
    name = Column(String(100), nullable=False, comment="配置名称")
    provider = Column(String(50), nullable=False, default="aliyun", comment="存储提供商: aliyun/s3/azure/minio")
    endpoint = Column(String(500), nullable=True, comment=" Endpoint / Region")
    bucket = Column(String(200), nullable=True, comment="Bucket 名称")
    access_key = Column(String(200), nullable=True, comment="Access Key / Account Name")
    secret_key = Column(String(500), nullable=True, comment="Secret Key / Account Key")
    prefix = Column(String(200), nullable=True, comment="存储路径前缀")
    region = Column(String(100), nullable=True, comment="区域/Region (S3/Azure)")
    extra_config = Column(Text, nullable=True, comment="扩展配置JSON")
    is_default = Column(Boolean, default=True, nullable=False, comment="是否默认启用")
    is_active = Column(Boolean, default=True, nullable=False, comment="是否启用")
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")
