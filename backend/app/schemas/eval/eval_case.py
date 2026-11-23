from typing import Optional, List, Any
from datetime import datetime
from pydantic import BaseModel, Field


class EvalCaseBase(BaseModel):
    """评估用例基础模型"""
    input_prompt: str = Field(..., description="输入提示")
    input_variables: Optional[dict] = Field(None, description="输入变量")
    expected_output_type: str = Field("text", description="期望输出类型")
    difficulty: str = Field("medium", description="难度等级")
    category: Optional[str] = Field(None, description="分类")
    remark: Optional[str] = Field(None, description="备注")
    sort_order: int = Field(0, description="排序顺序")
    is_active: bool = Field(True, description="是否启用")


class EvalCaseCreate(EvalCaseBase):
    """创建评估用例请求"""
    expected_output: Optional[str] = Field(None, description="期望输出（映射到参考答案）")
    expected_answer: Optional[str] = Field(None, description="期望答案（兼容字段）")


class EvalCaseUpdate(BaseModel):
    """更新评估用例请求"""
    input_prompt: Optional[str] = Field(None, description="输入提示")
    input_variables: Optional[dict] = Field(None, description="输入变量")
    expected_output: Optional[str] = Field(None, description="期望输出（映射到参考答案）")
    expected_output_type: Optional[str] = Field(None, description="期望输出类型")
    difficulty: Optional[str] = Field(None, description="难度等级")
    category: Optional[str] = Field(None, description="分类")
    remark: Optional[str] = Field(None, description="备注")
    sort_order: Optional[int] = Field(None, description="排序顺序")
    is_active: Optional[bool] = Field(None, description="是否启用")


class EvalCaseResponse(EvalCaseBase):
    """评估用例响应模型"""
    id: int
    suite_id: int
    created_at: datetime
    updated_at: datetime
    ground_truths: Optional[List[Any]] = Field(None, description="标准答案列表")

    class Config:
        from_attributes = True
