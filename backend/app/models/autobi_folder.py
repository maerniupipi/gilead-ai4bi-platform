"""AutoBI 项目分组文件夹"""
from sqlalchemy import Boolean, Column, Integer, String, TIMESTAMP, func

from ..core.database import Base


class AutobiFolder(Base):
    __tablename__ = "autobi_folders"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    space_id = Column(Integer, nullable=False, default=1, index=True, comment="所属空间ID")
    name = Column(String(128), nullable=False)
    sort_order = Column(Integer, nullable=False, server_default="0")
    is_system = Column(Boolean, nullable=False, server_default="0")
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
