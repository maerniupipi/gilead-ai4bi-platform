from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..services.data_sync.cron import next_run


class SyncTaskUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100)
    schedule_enabled: bool
    cron_expression: str = Field(min_length=1, max_length=100)
    timezone: str = Field(default="Asia/Shanghai", min_length=1, max_length=64)

    @field_validator("name", "cron_expression", "timezone")
    @classmethod
    def trim(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("配置不能为空")
        return value

    def next_after(self, after=None):
        return next_run(self.cron_expression, self.timezone, after)
