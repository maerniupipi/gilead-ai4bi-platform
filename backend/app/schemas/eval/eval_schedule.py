from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field


class EvalScheduleBase(BaseModel):
    """评估定时任务基础模型"""
    name: str = Field(..., description="定时任务名称")
    task_config: Optional[dict] = Field(None, description="任务配置")
    cron_expression: str = Field(..., description="Cron表达式")
    is_active: bool = Field(True, description="是否启用")
    notify_on_failure: bool = Field(True, description="失败时是否通知")
    notify_channels: Optional[dict] = Field(None, description="通知渠道配置")


class EvalScheduleCreate(EvalScheduleBase):
    """创建评估定时任务请求"""
    suite_id: int = Field(..., description="关联评测集ID")


class EvalScheduleUpdate(BaseModel):
    """更新评估定时任务请求"""
    name: Optional[str] = Field(None, description="定时任务名称")
    task_config: Optional[dict] = Field(None, description="任务配置")
    cron_expression: Optional[str] = Field(None, description="Cron表达式")
    is_active: Optional[bool] = Field(None, description="是否启用")
    notify_on_failure: Optional[bool] = Field(None, description="失败时是否通知")
    notify_channels: Optional[dict] = Field(None, description="通知渠道配置")


class EvalScheduleResponse(EvalScheduleBase):
    """评估定时任务响应模型"""
    id: int
    suite_id: int
    last_run_at: Optional[datetime] = None
    last_task_id: Optional[int] = None
    next_run_at: Optional[datetime] = None
    created_by: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True
