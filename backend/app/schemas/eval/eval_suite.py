from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field


class EvalTagInfo(BaseModel):
    """评测集标签信息"""
    id: int
    name: str
    color: Optional[str] = None


class EvalSuiteBase(BaseModel):
    """评估套件基础模型"""
    name: str = Field(..., description="套件名称")
    description: Optional[str] = Field(None, description="描述")
    version: str = Field("v1.0", description="版本号")
    default_task_source_type: str = Field("agent", description="默认任务源类型")
    default_task_source_id: Optional[int] = Field(None, description="默认任务源ID")
    default_task_source_config: Optional[dict] = Field(None, description="默认任务源配置")
    default_comparison_method: str = Field("exact", description="默认比较方法")
    default_comparison_config: Optional[dict] = Field(None, description="默认比较配置")
    folder_id: Optional[int] = Field(None, description="所属文件夹ID")


class EvalSuiteCreate(EvalSuiteBase):
    """创建评估套件请求"""
    tag_ids: Optional[List[int]] = Field(None, description="标签ID列表")


class EvalSuiteUpdate(BaseModel):
    """更新评估套件请求"""
    name: Optional[str] = Field(None, description="套件名称")
    description: Optional[str] = Field(None, description="描述")
    version: Optional[str] = Field(None, description="版本号")
    default_task_source_type: Optional[str] = Field(None, description="默认任务源类型")
    default_task_source_id: Optional[int] = Field(None, description="默认任务源ID")
    default_task_source_config: Optional[dict] = Field(None, description="默认任务源配置")
    default_comparison_method: Optional[str] = Field(None, description="默认比较方法")
    default_comparison_config: Optional[dict] = Field(None, description="默认比较配置")
    folder_id: Optional[int] = Field(None, description="所属文件夹ID")
    tag_ids: Optional[List[int]] = Field(None, description="标签ID列表")


class EvalSuiteResponse(EvalSuiteBase):
    """评估套件响应模型"""
    id: int
    space_id: int
    status: str = Field("draft", description="状态")
    created_by: Optional[int] = Field(None, description="创建人ID")
    created_at: datetime
    updated_at: datetime
    case_count: Optional[int] = Field(None, description="用例数量")
    last_pass_rate: Optional[float] = Field(None, description="最近通过率")
    tags: Optional[List[EvalTagInfo]] = Field(None, description="标签列表")
    suite_count: Optional[int] = Field(None, description="评测集数量（文件夹用）")

    class Config:
        from_attributes = True


class EvalShareIssueRequest(BaseModel):
    """生成或复用分享 token；rotate=true 时作废旧链接。"""
    rotate: bool = False


class EvalShareIssueOut(BaseModel):
    """分享 token 输出。"""
    token: str
    share_public_base_url: Optional[str] = Field(
        None,
        description="服务端 EVAL_SHARE_PUBLIC_BASE_URL，供前端拼完整分享 URL",
    )
