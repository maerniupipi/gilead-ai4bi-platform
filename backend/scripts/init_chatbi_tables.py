"""Explicit schema upgrade when DB_CREATE_ALL_ON_STARTUP=false. Adds service tables and indexes without changing conversation data."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.env_loader import load_app_environment
load_app_environment()
from app.core.database import Base, engine, SessionLocal
from app.models.chatbi import TABLES, ChatBIMessage

def initialize_service_tables(bind=None):
    bind = engine if bind is None else bind
    Base.metadata.create_all(bind=bind, tables=TABLES)
    for index in ChatBIMessage.__table__.indexes:
        if index.name == "ix_chatbi_message_conversation_sequence":
            index.create(bind=bind, checkfirst=True)


if __name__ == "__main__":
    initialize_service_tables()
    from app.services.chatbi.credentials import bootstrap_environment_key
    with SessionLocal() as db:
        bootstrap_environment_key(db)
    print("Platform service tables and optional environment Key registration are ready; raw keys were not printed.")
