from sqlalchemy import Column, Integer, String, TIMESTAMP, func
from ...core.database import Base


class EvalConfig(Base):
    __tablename__ = "eval_configs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    key = Column(String(100), unique=True, nullable=False, comment="配置键")
    value = Column(String(500), nullable=False, comment="配置值")
    description = Column(String(500), nullable=True, comment="配置说明")
    updated_at = Column(TIMESTAMP, server_default=func.current_timestamp(), onupdate=func.current_timestamp())
