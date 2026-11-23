from pydantic import BaseModel, ConfigDict, Field


class PPTModelSelection(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    provider_id: int = Field(gt=0, strict=True)
    model: str = Field(min_length=1, max_length=200)


class PPTModelOption(BaseModel):
    id: int
    name: str
    models: list[str]


class PPTModelView(BaseModel):
    provider_id: int | None
    provider_name: str | None
    model: str | None
    configured: bool
    available: bool
    source: str
    reason: str | None
    updated_at: int | None
