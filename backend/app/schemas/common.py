"""
通用Schema - 定义批量操作的请求模型
"""
from pydantic import BaseModel, Field
from typing import List, Dict


class BatchSelectRequest(BaseModel):
    """批量选择请求 - 通过ID列表选择资源"""
    ids: List[int] = Field(..., description="要选择的ID列表")


class BatchSelectFieldsRequest(BaseModel):
    """批量选择字段请求 - 选择指定表的指定字段"""
    fields: List[Dict[str, int]] = Field(..., description="要选择的表和字段映射，格式为[{table_id: int, field_id: int}]")


class BatchDeleteRequest(BaseModel):
    """批量删除请求 - 通过ID列表删除资源"""
    ids: List[int] = Field(..., description="要删除的ID列表")
