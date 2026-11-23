from typing import Optional, List
from pydantic import BaseModel, Field


class EvalGenerateRequest(BaseModel):
    """评估用例生成请求"""
    count: int = Field(10, description="生成数量")
    output_type: str = Field("mixed", description="输出类型")
    difficulty_distribution: Optional[dict] = Field(None, description="难度分布")
    scenario_description: Optional[str] = Field(None, description="场景描述")
    generate_ground_truth: bool = Field(True, description="是否生成标准答案")
    comparison_method: Optional[str] = Field(None, description="比较方法")


class EvalImportPreview(BaseModel):
    """评估导入预览"""
    total_rows: int = Field(..., description="总行数")
    valid_rows: int = Field(..., description="有效行数")
    invalid_rows: int = Field(..., description="无效行数")
    preview: list = Field(default_factory=list, description="预览数据")
    errors: list = Field(default_factory=list, description="错误列表")


class EvalImportRequest(BaseModel):
    """评估导入请求"""
    cases: list = Field(..., description="导入用例列表")
    import_mode: str = Field("skip", description="导入模式: skip=跳过重复, overwrite=覆盖重复, insert=插入新用例")
