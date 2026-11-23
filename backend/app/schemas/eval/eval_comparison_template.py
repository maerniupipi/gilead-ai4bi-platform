from datetime import datetime
from typing import Optional
from pydantic import BaseModel, field_validator


class EvalComparisonTemplateBase(BaseModel):
    name: str
    description: Optional[str] = None
    system_prompt: str
    user_prompt: str
    comparison_method: str = "llm_judge"


class EvalComparisonTemplateCreate(EvalComparisonTemplateBase):
    @field_validator("comparison_method")
    @classmethod
    def validate_comparison_method(cls, v: str) -> str:
        if v != "llm_judge":
            raise ValueError("当前仅支持 llm_judge 对比方式")
        return v


class EvalComparisonTemplateUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    user_prompt: Optional[str] = None
    comparison_method: Optional[str] = None
    is_default: Optional[bool] = None

    @field_validator("comparison_method")
    @classmethod
    def validate_comparison_method(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v != "llm_judge":
            raise ValueError("当前仅支持 llm_judge 对比方式")
        return v


class EvalComparisonTemplateResponse(EvalComparisonTemplateBase):
    id: int
    space_id: int
    is_default: bool
    is_system: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
