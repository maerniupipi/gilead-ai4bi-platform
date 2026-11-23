from sqlalchemy import Column, Integer, String, Boolean, Text, TIMESTAMP, JSON, func
from ...core.database import Base


class EvalSuite(Base):
    __tablename__ = "eval_suites"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    space_id = Column(Integer, nullable=False, index=True, comment="所属空间ID")
    folder_id = Column(Integer, nullable=False, index=True, comment="所属文件夹ID")
    name = Column(String(200), nullable=False, comment="评测集名称")
    description = Column(Text, nullable=True, comment="评测集描述")
    version = Column(String(50), default="v1.0", comment="版本号")
    default_task_source_type = Column(String(30), default="agent", comment="默认任务源类型")
    default_task_source_id = Column(Integer, nullable=True, comment="默认任务源ID")
    default_task_source_config = Column(JSON, nullable=True, comment="默认任务源配置")
    default_comparison_method = Column(String(30), default="exact", comment="默认对比方式")
    default_comparison_config = Column(JSON, nullable=True, comment="默认对比配置")
    status = Column(String(20), default="draft", comment="状态：draft/active/archived")
    share_token = Column(String(64), nullable=True, unique=True, index=True, comment="外链分享token")
    created_by = Column(Integer, nullable=False, comment="创建者ID")
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    updated_at = Column(TIMESTAMP, server_default=func.current_timestamp(), onupdate=func.current_timestamp())
