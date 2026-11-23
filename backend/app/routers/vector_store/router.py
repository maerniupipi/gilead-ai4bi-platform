"""
向量库配置路由
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ...core.database import get_db
from ...core.permissions import RequireSystemPermission
from ...schemas.vector_store import (
    VectorStoreCreate,
    VectorStoreResponse,
    VectorStoreTestRequest,
    VectorStoreTestResponse,
    VectorStoreUpdate,
)
from ...services.vector_store.service import VectorStoreService

router = APIRouter(prefix="/api/vector-stores", tags=["向量库配置"])


@router.get("", response_model=List[VectorStoreResponse])
def list_vector_stores(
    skip: int = 0,
    limit: int = 100,
    space_id: Optional[int] = Query(None, description="空间ID"),
    db: Session = Depends(get_db)
):
    return VectorStoreService.get_all(db, skip, limit, space_id)


@router.post("", response_model=VectorStoreResponse)
def create_vector_store(
    store: VectorStoreCreate,
    space_id: Optional[int] = Query(1, description="空间ID"),
    db: Session = Depends(get_db),
    operator_id: int = Depends(RequireSystemPermission("*")),
):
    return VectorStoreService.create(db, store, space_id)


@router.put("/{store_id}", response_model=VectorStoreResponse)
def update_vector_store(
    store_id: int,
    store: VectorStoreUpdate,
    space_id: Optional[int] = Query(None, description="空间ID"),
    db: Session = Depends(get_db),
    operator_id: int = Depends(RequireSystemPermission("*")),
):
    return VectorStoreService.update(db, store_id, store, space_id)


@router.delete("/{store_id}")
def delete_vector_store(
    store_id: int,
    space_id: Optional[int] = Query(None, description="空间ID"),
    db: Session = Depends(get_db),
    operator_id: int = Depends(RequireSystemPermission("*")),
):
    VectorStoreService.delete(db, store_id, space_id)
    return {"message": "删除成功"}


@router.post("/test", response_model=VectorStoreTestResponse)
async def test_vector_store(
    store: VectorStoreTestRequest,
    operator_id: int = Depends(RequireSystemPermission("*")),
):
    return await VectorStoreService.test_store(store)
