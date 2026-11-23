"""Management API models; never reuse these on the external /v1 boundary."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, SecretStr


class KeyBinding(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=100)
    workflow_id: int = Field(gt=0)
    version_id: int = Field(gt=0)
    enabled: bool = True


class KeyCreate(KeyBinding):
    environment: Literal["uat", "prod"]
    api_key: SecretStr | None = None


class KeyEnabled(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool


class KeyView(BaseModel):
    id: str
    name: str
    environment: str
    key_hint: str
    enabled: bool
    workflow_id: int | None
    workflow_name: str | None
    version_id: int | None
    version_name: str | None
    workflow_rev: int | None
    legacy_config: str | None
    created_at: int
    updated_at: int


class KeyCreated(BaseModel):
    key: KeyView
    api_key: str | None
