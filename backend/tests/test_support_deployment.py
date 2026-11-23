from pathlib import Path


def test_platform_deployment_builds_complete_source_and_keeps_runtime_credentials_external():
    root = Path(__file__).resolve().parents[2]
    content = (root / "deploy/docker-compose.yml").read_text()
    assert "../backend" in content and "../frontend" in content
    assert "env/platform-backend.env" in content
    assert "MYSQL_PASSWORD:?" in content
    assert "DATA_SYNC_TMP_DIR" in content
    ignore = (root / ".gitignore").read_text()
    assert "secrets/" in ignore and ".env" in ignore
    dockerfile = (root / "backend/Dockerfile").read_text()
    assert "COPY app ./app" in dockerfile


def test_initial_schema_contains_every_registered_model():
    import re
    import app.models
    from app.core.database import Base
    root = Path(__file__).resolve().parents[2]
    sql = (root / "backend/init_tables.sql").read_text()
    names = set(re.findall(r"CREATE TABLE IF NOT EXISTS `?([a-z_]+)", sql))
    assert names == set(Base.metadata.tables)
    assert "system_updates" in names
