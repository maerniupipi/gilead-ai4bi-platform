import json
import pytest
from app.services.data_sync.settings import SyncConfig, task_definitions


def env(config):
    return {"DATA_SYNC_TASKS":json.dumps({"catalog":config}),
            "DATA_SYNC_DATABASE_URL":"postgresql+psycopg2://user:fake-password@db.example.test/data"}


@pytest.mark.parametrize("override", [
    {"target_table":""}, {"base_url":"https://user:secret@example.test/data"},
    {"base_url":"https://example.test:70000/data"}, {"method":"DELETE"},
    {"page_param":""}, {"column_case":"unrecognized"}, {"page_size":0}, {"unknown":True},
])
def test_bad_source_configuration_never_becomes_runnable(override):
    config = {"base_url":"https://source.example.test/data", "target_table":"public.catalog", **override}
    with pytest.raises(ValueError):
        SyncConfig.from_env("catalog", env(config))


def test_default_registry_is_empty_and_source_credentials_are_optional():
    assert task_definitions({}) == {}
    config = SyncConfig.from_env("catalog", env({"base_url":"https://source.example.test/data", "target_table":"public.catalog"}))
    assert config.headers == {} and config.method == "GET" and config.page_size == 5000
    assert "fake-password" not in repr(config)
