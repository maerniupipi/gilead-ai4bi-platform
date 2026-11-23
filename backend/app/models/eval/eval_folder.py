from sqlalchemy import Column, Integer, String, Boolean, Text, TIMESTAMP, func
from ...core.database import Base


class EvalFolder(Base):
    __tablename__ = "eval_folders"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    space_id = Column(Integer, nullable=False, index=True, comment="所属空间ID")
    parent_id = Column(Integer, nullable=True, index=True, comment="父文件夹ID")
    name = Column(String(100), nullable=False, comment="文件夹名称")
    description = Column(Text, nullable=True, comment="文件夹描述")
    sort_order = Column(Integer, default=0, comment="排序序号")
    is_system = Column(Boolean, default=False, comment="系统文件夹")
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
    updated_at = Column(TIMESTAMP, server_default=func.current_timestamp(), onupdate=func.current_timestamp())
