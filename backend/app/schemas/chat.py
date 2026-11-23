"""
聊天相关的Pydantic模型
"""
from typing import Optional, List
from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    """聊天消息"""
    role: str = Field(..., description="角色: user/assistant")
    content: str = Field(..., description="消息内容")


class ChatRequest(BaseModel):
    """聊天请求"""
    provider_id: int = Field(..., description="供应商ID")
    model: str = Field(..., description="模型名称")
    message: str = Field(..., description="用户消息")
    system: Optional[str] = Field(None, description="系统提示词（OpenAI 协议下作为 system 消息）")
    temperature: Optional[float] = Field(0.7, description="温度参数")
    max_tokens: Optional[int] = Field(2000, description="最大token数")
    top_p: Optional[float] = Field(0.9, description="top_p参数")
    timeout_seconds: Optional[float] = Field(None, description="模型请求超时时间（秒）")
    stop_words: Optional[List[str]] = Field(None, description="模型停止生成的字符串列表")


class ChatResponse(BaseModel):
    """聊天响应"""
    content: str = Field(..., description="助手回复内容")
    model: str = Field(..., description="使用的模型")
    provider: str = Field(..., description="供应商名称")
    usage: dict = Field(default_factory=dict)
