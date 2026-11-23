"""Server configuration. Credentials are supplied through the environment."""
from dataclasses import dataclass, field
import os


@dataclass
class Settings:
    database_url: str = field(default_factory=lambda: os.getenv("BATCH_DATABASE_URL", ""))
    admin_password: str = field(default_factory=lambda: os.getenv("BATCH_ADMIN_PASSWORD", ""), repr=False)
    cookie_secure: bool = field(default_factory=lambda: os.getenv("BATCH_COOKIE_SECURE", "false").lower() == "true")
    allowed_hosts: list[str] = field(default_factory=lambda: os.getenv(
        "BATCH_ALLOWED_HOSTS", "127.0.0.1,localhost").split(","))
    allow_local_paths: bool = field(default_factory=lambda: os.getenv("BATCH_ALLOW_LOCAL_PATHS", "false").lower() == "true")
    session_seconds: int = 12 * 60 * 60
