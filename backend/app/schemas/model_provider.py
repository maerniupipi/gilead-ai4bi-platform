"""
模型供应商相关的Pydantic模型
"""
from typing import Optional, List, Literal
from datetime import datetime
from pydantic import BaseModel, Field


class ModelThinkingConfig(BaseModel):
    enabled: bool = False
    parameter: Literal["enable_thinking", "reasoning_effort", "thinking_budget"] = "enable_thinking"
    effort: Literal["low", "medium", "high", "xhigh"] = "medium"
    budget: int = Field(default=4096, ge=1, le=1048576)


class ModelProviderBase(BaseModel):
    """模型供应商基础模型"""
    name: str = Field(..., description="供应商名称")
    base_url: str = Field(..., description="API Base URL")
    api_key: Optional[str] = Field(None, description="API Key")
    protocol: str = Field(default="openai", description="协议类型")
    models: Optional[str] = Field(None, description="模型列表JSON")
    model_settings: Optional[dict[str, ModelThinkingConfig]] = None
    description: Optional[str] = Field(None, description="备注说明")
    is_active: bool = Field(default=True, description="是否启用")


class ModelProviderCreate(ModelProviderBase):
    """创建模型供应商"""
    pass


class ModelProviderUpdate(BaseModel):
    """更新模型供应商"""
    name: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    protocol: Optional[str] = None
    models: Optional[str] = None
    model_settings: Optional[dict[str, ModelThinkingConfig]] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class ModelProviderResponse(ModelProviderBase):
    """模型供应商响应"""
    id: int
    is_builtin: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ModelTestRequest(BaseModel):
    """模型测试请求"""
    base_url: str
    api_key: Optional[str] = None
    protocol: str = "openai"
    model: str = Field(..., description="要测试的模型名称")
    model_settings: Optional[dict[str, ModelThinkingConfig]] = None


class ModelTestResponse(BaseModel):
    """模型测试响应"""
    success: bool
    message: str
    response_data: Optional[dict] = None
