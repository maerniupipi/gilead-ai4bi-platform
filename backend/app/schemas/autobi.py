"""
AutoBI 项目 DTO
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field


class AutobiFolderCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)


class AutobiFolderUpdate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)


class AutobiFolderMoveBody(BaseModel):
    direction: Literal["up", "down"]


class AutobiFolderItem(BaseModel):
    id: int
    name: str
    sort_order: int = 0
    is_system: bool = False
    created_at: datetime

    class Config:
        from_attributes = True


class AutobiProjectCreate(BaseModel):
    name: str = Field(..., max_length=255)
    description: Optional[str] = None
    folder_id: Optional[int] = None


class AutobiProjectImport(BaseModel):
    payload: Dict[str, Any]
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    folder_id: Optional[int] = Field(None, gt=0)


class AutobiProjectUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    folder_id: Optional[int] = None
    # 整包替换：含 knowledge_base_id、model_bindings、request（messages/stream/advanced_config）
    config_json: Optional[Dict[str, Any]] = None


class AutobiProjectListItem(BaseModel):
    id: int
    api_access_id: Optional[str] = None
    name: str
    description: Optional[str] = None
    knowledge_base_id: Optional[int] = None
    folder_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AutobiProjectDetail(AutobiProjectListItem):
    """含完整 config_json（解析为对象）"""

    config_json: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        from_attributes = True


class AutobiShareIssueOut(BaseModel):
    token: str
    share_public_base_url: Optional[str] = None
