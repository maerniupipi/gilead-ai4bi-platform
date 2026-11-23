"""
AutoBI 原子能力路由
"""
from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.autobi_atomic import (
    ESValueRetrieverRequest, ESValueRetrieverResponse,
    ESKnowledgeRetrieverRequest, ESKnowledgeRetrieverResponse,
    SQLTemplateRetrieverRequest, SQLTemplateRetrieverResponse,
    TableMetaRetrieverRequest, TableMetaRetrieverResponse,
    TableValueRetrieverRequest, TableValueRetrieverResponse,
    GlobalValueMetaRetrieverRequest, GlobalValueMetaRetrieverResponse,
    MultiGlobalValueMetaRetrieverRequest,
    NerRetrieverRequest,
    GenerateSqlRequest, GenerateSqlResponse,
    ExecuteSqlRequest, ExecuteSqlResponse,
)
from app.services.knowledge.autobi_atomic import AutoBIAtomicService

router = APIRouter(prefix="/autobi-atomic", tags=["AutoBI原子能力"])


@router.post("/{knowledge_base_id}/es-value-retriever")
async def es_value_retrieve(
    request: ESValueRetrieverRequest,
    knowledge_base_id: int = Path(..., description="知识库ID"),
    db: Session = Depends(get_db)
):
    """ES表值召回"""
    try:
        result = await AutoBIAtomicService.es_value_retrieve(db, knowledge_base_id, request)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ES表值召回失败: {str(e)}")


@router.post("/{knowledge_base_id}/es-knowledge-retriever")
async def es_knowledge_retrieve(
    request: ESKnowledgeRetrieverRequest,
    knowledge_base_id: int = Path(..., description="知识库ID"),
    db: Session = Depends(get_db)
):
    """ES知识词召回"""
    try:
        result = await AutoBIAtomicService.es_knowledge_retrieve(db, knowledge_base_id, request)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ES知识词召回失败: {str(e)}")


@router.post("/{knowledge_base_id}/sql-template-retriever")
async def sql_template_retrieve(
    request: SQLTemplateRetrieverRequest,
    knowledge_base_id: int = Path(..., description="知识库ID"),
    db: Session = Depends(get_db)
):
    """SQL样例召回"""
    try:
        result = await AutoBIAtomicService.sql_template_retrieve(db, knowledge_base_id, request)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"SQL样例召回失败: {str(e)}")


@router.post("/generate-sql", response_model=GenerateSqlResponse)
async def generate_sql(
    request: GenerateSqlRequest,
    db: Session = Depends(get_db),
):
    """生成 SQL"""
    try:
        return await AutoBIAtomicService.generate_sql(db, request)
    except HTTPException:
        raise
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"生成 SQL 失败: {str(e)}")


@router.post("/{knowledge_base_id}/execute-sql", response_model=ExecuteSqlResponse)
async def execute_sql(
    request: ExecuteSqlRequest,
    knowledge_base_id: int = Path(..., description="知识库ID"),
    db: Session = Depends(get_db),
):
    """执行 SQL"""
    try:
        return await AutoBIAtomicService.execute_sql(db, knowledge_base_id, request)
    except HTTPException:
        raise
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"执行 SQL 失败: {str(e)}")


@router.post("/{knowledge_base_id}/table-meta-retriever")
async def table_meta_retrieve(
    request: TableMetaRetrieverRequest,
    knowledge_base_id: int = Path(..., description="知识库ID"),
    db: Session = Depends(get_db)
):
    """表字段召回"""
    try:
        result = await AutoBIAtomicService.table_meta_retrieve(db, knowledge_base_id, request)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"表字段召回失败: {str(e)}")


@router.post("/{knowledge_base_id}/table-value-retriever")
async def table_value_retrieve(
    request: TableValueRetrieverRequest,
    knowledge_base_id: int = Path(..., description="知识库ID"),
    db: Session = Depends(get_db)
):
    """表值召回"""
    try:
        result = await AutoBIAtomicService.table_value_retrieve(db, knowledge_base_id, request)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"表值召回失败: {str(e)}")


@router.post("/{knowledge_base_id}/global-value-meta-retriever")
async def global_value_meta_retrieve(
    request: GlobalValueMetaRetrieverRequest,
    knowledge_base_id: int = Path(..., description="知识库ID"),
    db: Session = Depends(get_db)
):
    """表值召回(对应字段)"""
    try:
        result = await AutoBIAtomicService.global_value_meta_retrieve(db, knowledge_base_id, request)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"表值召回(对应字段)失败: {str(e)}")


@router.post("/{knowledge_base_id}/multi-global-value-meta-retriever")
async def multi_global_value_meta_retrieve(
    request: MultiGlobalValueMetaRetrieverRequest,
    knowledge_base_id: int = Path(..., description="知识库ID"),
    db: Session = Depends(get_db),
):
    """多列同值：对多个表&字段分别做表值召回(对应字段)后去重合并"""
    try:
        result = await AutoBIAtomicService.multi_global_value_meta_retrieve(
            db, knowledge_base_id, request
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"多列同值召回失败: {str(e)}")


@router.post("/{knowledge_base_id}/ner-retriever")
async def ner_retrieve(
    request: NerRetrieverRequest,
    knowledge_base_id: int = Path(..., description="知识库ID"),
    db: Session = Depends(get_db),
):
    """NER：按别名匹配知识库实体映射表"""
    try:
        result = await AutoBIAtomicService.ner_retrieve(db, knowledge_base_id, request)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"NER 召回失败: {str(e)}")
