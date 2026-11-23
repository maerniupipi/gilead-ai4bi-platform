"""Isolated data for legacy auth checks; never read an installed invite-code database."""
from datetime import datetime, timedelta
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models.invite_code import InviteCode


@pytest.fixture
def auth_database(tmp_path):
    engine=create_engine('sqlite:///'+str(tmp_path/'auth.sqlite3'),connect_args={'check_same_thread':False})
    InviteCode.__table__.create(engine)
    factory=sessionmaker(engine)
    with factory() as db:
        db.add_all([InviteCode(code='test2024',expires_at=datetime.now()+timedelta(days=1),is_active=True,is_deleted=False),
                    InviteCode(code='expired',expires_at=datetime.now()-timedelta(days=1),is_active=True,is_deleted=False)])
        db.commit()
    yield factory
    engine.dispose()
