from sqlalchemy import Column, Integer, String, TIMESTAMP, func, ForeignKey
from ...core.database import Base


class EvalTag(Base):
    __tablename__ = "eval_tags"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    space_id = Column(Integer, nullable=False, index=True, comment="所属空间ID")
    name = Column(String(50), nullable=False, comment="标签名称")
    color = Column(String(20), default="#409EFF", comment="标签颜色")
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())


class EvalSuiteTag(Base):
    __tablename__ = "eval_suite_tags"

    suite_id = Column(Integer, ForeignKey("eval_suites.id", ondelete="CASCADE"), primary_key=True)
    tag_id = Column(Integer, ForeignKey("eval_tags.id", ondelete="CASCADE"), primary_key=True)
