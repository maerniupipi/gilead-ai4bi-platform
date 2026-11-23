from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field


class EvalSubTaskCreate(BaseModel):
    """创建评估子任务请求"""
    target_type: str = Field(..., description="目标类型")
    target_id: Optional[int] = Field(None, description="目标ID")
    target_config: Optional[dict] = Field(None, description="目标配置")


class EvalExecParams(BaseModel):
    """评估执行参数"""
    timeout_seconds: int = Field(180, ge=30, le=600, description="单条用例执行超时时间（秒）")


class EvalTaskCreate(BaseModel):
    """创建评估任务请求"""
    suite_id: int = Field(..., description="套件ID")
    name: str = Field(..., description="任务名称")
    description: Optional[str] = Field(None, description="描述")
    output_template_id: Optional[int] = Field(None, description="输出模板ID")
    comparison_template_id: Optional[int] = Field(None, description="评判模板ID")
    case_filter: Optional[dict] = Field(None, description="用例筛选条件")
    exec_params: Optional[EvalExecParams] = Field(None, description="执行参数")
    sub_tasks: List[EvalSubTaskCreate] = Field(..., description="子任务列表")
    scheduled_at: Optional[datetime] = Field(None, description="定时执行时间")


class EvalTaskResponse(BaseModel):
    """评估任务响应模型"""
    id: int
    suite_id: int
    name: str
    description: Optional[str] = None
    output_template_id: Optional[int] = None
    case_filter: Optional[dict] = None
    exec_params: Optional[dict] = None
    status: str = "pending"
    total_cases: int = 0
    completed_cases: int = 0
    passed_cases: int = 0
    failed_cases: int = 0
    error_cases: int = 0
    scheduled_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_by: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class EvalSubTaskResponse(BaseModel):
    """评估子任务响应模型"""
    id: int
    task_id: int
    target_type: str
    target_id: Optional[int] = None
    target_config: Optional[dict] = None
    status: str = "pending"
    total_cases: int = 0
    completed_cases: int = 0
    passed_cases: int = 0
    failed_cases: int = 0
    error_cases: int = 0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None

    class Config:
        from_attributes = True
