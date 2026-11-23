"""
知识库数据访问层 - 负责所有知识库相关的数据库操作
"""
from sqlalchemy.orm import Session, joinedload, selectinload

from .... import models


def list_kb_recall_field_descriptions(
    db: Session, knowledge_base_id: int, table_names: list[str]
) -> list[dict]:
    """批量读取本次召回表的中文说明，只使用当前知识库的启用字段。"""
    if not table_names:
        return []
    rows = (
        db.query(
            models.KbTableStructure.table_name,
            models.KbTableStructure.table_alias,
            models.KbTableField.field_name,
            models.KbTableField.field_alias,
        )
        .join(models.KbTableField, models.KbTableField.kb_table_structure_id == models.KbTableStructure.id)
        .join(models.KnowledgeBase, models.KnowledgeBase.id == models.KbTableStructure.knowledge_base_id)
        .filter(
            models.KnowledgeBase.id == knowledge_base_id,
            models.KnowledgeBase.is_deleted.is_(False),
            models.KbTableStructure.table_name.in_(table_names),
            models.KbTableField.is_enabled.is_(True),
        )
        .order_by(models.KbTableStructure.id, models.KbTableField.id)
        .all()
    )
    return [dict(row._mapping) for row in rows]


def get_knowledge_base_detail(db: Session, knowledge_base_id: int, space_id: int = None):
    """
    查询知识库详情（含关联的表结构、字段、知识词条和样例）

    集合分别批量加载，避免字段 × 知识词条 × 样例的笛卡尔积撑爆查询。
    """
    query = db.query(models.KnowledgeBase).filter(
        models.KnowledgeBase.id == knowledge_base_id,
        models.KnowledgeBase.is_deleted == False,
    )
    if space_id is not None:
        query = query.filter(models.KnowledgeBase.space_id == space_id)
    return query.options(
        joinedload(models.KnowledgeBase.knowledge_access).joinedload(
            models.KnowledgeAccess.data_source
        ),
        selectinload(models.KnowledgeBase.kb_table_structures).selectinload(
            models.KbTableStructure.kb_table_fields
        ),
        selectinload(models.KnowledgeBase.kb_knowledge_terms).joinedload(
            models.KbKnowledgeTerm.knowledge_term
        ),
        selectinload(models.KnowledgeBase.kb_sample_libraries).joinedload(
            models.KbSampleLibrary.sample_library
        )
    ).first()


def get_knowledge_base_active(db: Session, knowledge_base_id: int, space_id: int = None):
    """查询未删除的知识库"""
    query = db.query(models.KnowledgeBase).filter(
        models.KnowledgeBase.id == knowledge_base_id,
        models.KnowledgeBase.is_deleted == False,
    )
    if space_id is not None:
        query = query.filter(models.KnowledgeBase.space_id == space_id)
    return query.first()


def get_knowledge_access_active_by_id(db: Session, knowledge_access_id: int, space_id: int = None):
    """查询未删除的知识接入"""
    query = db.query(models.KnowledgeAccess).filter(
        models.KnowledgeAccess.id == knowledge_access_id,
        models.KnowledgeAccess.is_deleted == False,
    )
    if space_id is not None:
        query = query.filter(models.KnowledgeAccess.space_id == space_id)
    return query.first()


def list_knowledge_bases(db: Session, skip: int, limit: int, space_id: int = None):
    """查询知识库列表"""
    query = db.query(models.KnowledgeBase).filter(
        models.KnowledgeBase.is_deleted == False,
    )
    if space_id is not None:
        query = query.filter(models.KnowledgeBase.space_id == space_id)
    return query.offset(skip).limit(limit).all()


def list_table_structures_by_ids_and_access(db: Session, table_ids, knowledge_access_id: int):
    """根据ID列表和知识接入ID查询表结构"""
    return (
        db.query(models.TableStructure)
        .filter(
            models.TableStructure.id.in_(table_ids),
            models.TableStructure.knowledge_access_id == knowledge_access_id,
        )
        .all()
    )


def list_table_fields_by_ids_and_table_ids(db: Session, field_ids, table_ids):
    """根据字段ID列表和表ID列表查询字段"""
    return (
        db.query(models.TableField)
        .filter(
            models.TableField.id.in_(field_ids),
            models.TableField.table_structure_id.in_(table_ids),
        )
        .all()
    )


def get_kb_table_structure_by_id_with_fields(db: Session, kb_table_structure_id: int, space_id: int = None):
    """查询知识库表结构（含字段）"""
    query = db.query(models.KbTableStructure).filter(
        models.KbTableStructure.id == kb_table_structure_id
    )
    if space_id is not None:
        query = query.join(models.KnowledgeBase).filter(models.KnowledgeBase.space_id == space_id)
    return query.options(joinedload(models.KbTableStructure.kb_table_fields)).first()


def upsert_kb_table_structures_and_fields_old_format(db: Session, knowledge_base_id: int, table_structures):
    """
    批量添加表结构到知识库（老格式）

    注意：选择整张表，自动克隆所有字段
    """
    for table_structure in table_structures:
        existing = (
            db.query(models.KbTableStructure)
            .filter(
                models.KbTableStructure.knowledge_base_id == knowledge_base_id,
                models.KbTableStructure.table_structure_id == table_structure.id,
            )
            .first()
        )

        if existing:
            continue

        kb_table_structure = models.KbTableStructure(
            knowledge_base_id=knowledge_base_id,
            table_structure_id=table_structure.id,
            table_name=table_structure.table_name,
            table_alias=table_structure.table_alias,
        )
        db.add(kb_table_structure)
        db.flush()  # 确保 kb_table_structure.id 可用于写入子表

        for table_field in table_structure.table_fields:
            kb_table_field = models.KbTableField(
                kb_table_structure_id=kb_table_structure.id,
                table_field_id=table_field.id,
                field_name=table_field.field_name,
                field_alias=table_field.field_alias,
                field_type=table_field.field_type,
                is_vectorized=table_field.is_vectorized,
                is_enabled=table_field.is_enabled,
            )
            db.add(kb_table_field)


def upsert_kb_table_structures_and_fields_new_format(
    db: Session,
    knowledge_base_id: int,
    fields_by_table: dict,
    table_map: dict,
    field_map: dict,
):
    """
    批量添加表结构和字段到知识库（新格式）

    注意：只添加指定的字段，支持细粒度选择
    """
    for table_id, field_ids in fields_by_table.items():
        existing_table = (
            db.query(models.KbTableStructure)
            .filter(
                models.KbTableStructure.knowledge_base_id == knowledge_base_id,
                models.KbTableStructure.table_structure_id == table_id,
            )
            .first()
        )

        if existing_table:
            kb_table_structure = existing_table
            table_structure = table_map[table_id]
        else:
            table_structure = table_map[table_id]
            kb_table_structure = models.KbTableStructure(
                knowledge_base_id=knowledge_base_id,
                table_structure_id=table_id,
                table_name=table_structure.table_name,
                table_alias=table_structure.table_alias,
            )
            db.add(kb_table_structure)
            db.flush()  # 获取 kb_table_structure.id

        existing_fields = (
            db.query(models.KbTableField)
            .filter(models.KbTableField.kb_table_structure_id == kb_table_structure.id)
            .all()
        )
        existing_field_ids = [field.table_field_id for field in existing_fields]

        for field_id in field_ids:
            if field_id in existing_field_ids:
                continue

            table_field = field_map[field_id]
            kb_table_field = models.KbTableField(
                kb_table_structure_id=kb_table_structure.id,
                table_field_id=field_id,
                field_name=table_field.field_name,
                field_alias=table_field.field_alias,
                field_type=table_field.field_type,
                is_vectorized=table_field.is_vectorized,
                is_enabled=table_field.is_enabled,
            )
            db.add(kb_table_field)


def count_kb_table_structures(db: Session, knowledge_base_id: int) -> int:
    """统计知识库中的表数量"""
    return (
        db.query(models.KbTableStructure)
        .filter(models.KbTableStructure.knowledge_base_id == knowledge_base_id)
        .count()
    )


def create_knowledge_base(db: Session, knowledge_base_data: dict):
    """创建知识库"""
    db_knowledge_base = models.KnowledgeBase(**knowledge_base_data)
    db.add(db_knowledge_base)
    return db_knowledge_base


def list_knowledge_bases_simple(db: Session, skip: int, limit: int):
    """分页查询知识库列表（无space过滤）"""
    return (
        db.query(models.KnowledgeBase)
        .filter(models.KnowledgeBase.is_deleted == False)
        .offset(skip)
        .limit(limit)
        .all()
    )


def apply_knowledge_base_update(db: Session, db_knowledge_base, update_data: dict):
    """应用知识库更新数据"""
    for key, value in update_data.items():
        setattr(db_knowledge_base, key, value)
    return db_knowledge_base


def soft_delete_knowledge_base(db: Session, db_knowledge_base):
    """软删除知识库"""
    db_knowledge_base.is_deleted = True
    return db_knowledge_base


def get_kb_table_structure_by_id(db: Session, kb_table_structure_id: int):
    """根据ID查询知识库表结构"""
    return db.query(models.KbTableStructure).filter(models.KbTableStructure.id == kb_table_structure_id).first()


def list_knowledge_terms_by_ids_and_access(db: Session, term_ids, knowledge_access_id: int):
    """根据ID列表和知识接入ID查询知识词条"""
    return (
        db.query(models.KnowledgeTerm)
        .filter(
            models.KnowledgeTerm.id.in_(term_ids),
            models.KnowledgeTerm.knowledge_access_id == knowledge_access_id,
            models.KnowledgeTerm.is_deleted == False,
        )
        .all()
    )


def upsert_kb_knowledge_terms(db: Session, knowledge_base_id: int, knowledge_terms):
    """批量引用知识词条到知识库（建立引用关系，不复制值）"""
    for knowledge_term in knowledge_terms:
        existing = (
            db.query(models.KbKnowledgeTerm)
            .filter(
                models.KbKnowledgeTerm.knowledge_base_id == knowledge_base_id,
                models.KbKnowledgeTerm.knowledge_term_id == knowledge_term.id,
            )
            .first()
        )
        if existing:
            continue

        # 建立引用关系，只缓存初始值
        kb_knowledge_term = models.KbKnowledgeTerm(
            knowledge_base_id=knowledge_base_id,
            knowledge_term_id=knowledge_term.id,
            term_name_cache=knowledge_term.term_name,
            term_value_cache=knowledge_term.term_value,
        )
        db.add(kb_knowledge_term)


def list_sample_libraries_by_ids_and_access(db: Session, sample_ids, knowledge_access_id: int):
    """根据ID列表和知识接入ID查询样例库"""
    return (
        db.query(models.SampleLibrary)
        .filter(
            models.SampleLibrary.id.in_(sample_ids),
            models.SampleLibrary.knowledge_access_id == knowledge_access_id,
            models.SampleLibrary.is_deleted == False,
        )
        .all()
    )


def upsert_kb_sample_libraries(db: Session, knowledge_base_id: int, sample_libraries):
    """批量引用样例到知识库（建立引用关系，不复制值）"""
    for sample_library in sample_libraries:
        existing = (
            db.query(models.KbSampleLibrary)
            .filter(
                models.KbSampleLibrary.knowledge_base_id == knowledge_base_id,
                models.KbSampleLibrary.sample_id == sample_library.id,
            )
            .first()
        )
        if existing:
            continue

        # 建立引用关系，只缓存初始值
        kb_sample_library = models.KbSampleLibrary(
            knowledge_base_id=knowledge_base_id,
            sample_id=sample_library.id,
            sample_name_cache=sample_library.sample_name,
            sample_content_cache=sample_library.sql_content,
        )
        db.add(kb_sample_library)


def clone_knowledge_base_relationships(db: Session, original, cloned):
    """
    克隆知识库的所有关联关系

    注意：包括表结构、字段、词条和样例，不负责commit
    """
    # 克隆表结构与字段
    for kb_table_structure in original.kb_table_structures:
        cloned_kb_table_structure = models.KbTableStructure(
            knowledge_base_id=cloned.id,
            table_structure_id=kb_table_structure.table_structure_id,
            table_name=kb_table_structure.table_name,
            table_alias=kb_table_structure.table_alias,
            is_vectorized=kb_table_structure.is_vectorized,
        )
        db.add(cloned_kb_table_structure)
        db.flush()  # 获取 cloned_kb_table_structure.id 以便写子表字段

        for kb_table_field in kb_table_structure.kb_table_fields:
            cloned_kb_table_field = models.KbTableField(
                kb_table_structure_id=cloned_kb_table_structure.id,
                table_field_id=kb_table_field.table_field_id,
                field_name=kb_table_field.field_name,
                field_alias=kb_table_field.field_alias,
                field_type=kb_table_field.field_type,
                is_vectorized=kb_table_field.is_vectorized,
                is_enabled=kb_table_field.is_enabled,
            )
            db.add(cloned_kb_table_field)

    # 克隆知识词条
    for kb_knowledge_term in original.kb_knowledge_terms:
        cloned_kb_knowledge_term = models.KbKnowledgeTerm(
            knowledge_base_id=cloned.id,
            knowledge_term_id=kb_knowledge_term.knowledge_term_id,
            term_name_cache=kb_knowledge_term.term_name,
            term_value_cache=kb_knowledge_term.term_value,
        )
        db.add(cloned_kb_knowledge_term)

    # 克隆样例库
    for kb_sample_library in original.kb_sample_libraries:
        cloned_kb_sample_library = models.KbSampleLibrary(
            knowledge_base_id=cloned.id,
            sample_id=kb_sample_library.sample_id,
            sample_name_cache=kb_sample_library.sample_name,
            sample_content_cache=kb_sample_library.sample_content,
        )
        db.add(cloned_kb_sample_library)

    # 克隆 NER 映射
    ner_rows = (
        db.query(models.KbNerRow)
        .filter(models.KbNerRow.knowledge_base_id == original.id)
        .all()
    )
    for ner in ner_rows:
        db.add(
            models.KbNerRow(
                knowledge_base_id=cloned.id,
                sheet_name=ner.sheet_name,
                table_name=ner.table_name,
                field_name=ner.field_name,
                standard_name=ner.standard_name,
                alias=ner.alias,
                remark=ner.remark,
            )
        )


def get_kb_table_structure_by_id(db: Session, kb_table_structure_id: int, space_id: int = None):
    query = db.query(models.KbTableStructure).filter(models.KbTableStructure.id == kb_table_structure_id)
    if space_id is not None:
        query = query.join(models.KnowledgeBase).filter(models.KnowledgeBase.space_id == space_id)
    return query.first()


def apply_kb_table_structure_update(db: Session, kb_table_structure, update_data: dict):
    """应用知识库表结构更新数据"""
    for key, value in update_data.items():
        setattr(kb_table_structure, key, value)
    return kb_table_structure


def delete_kb_table_structure_by_id(db: Session, kb_table_structure_id: int, space_id: int = None):
    """删除知识库表结构"""
    kb_table_structure = get_kb_table_structure_by_id(db, kb_table_structure_id, space_id)
    if kb_table_structure is None:
        return None

    knowledge_base_id = kb_table_structure.knowledge_base_id
    db.delete(kb_table_structure)
    return knowledge_base_id


def set_knowledge_base_table_count_by_id(db: Session, knowledge_base_id: int):
    """更新知识库的表数量统计"""
    knowledge_base = db.query(models.KnowledgeBase).filter(models.KnowledgeBase.id == knowledge_base_id).first()
    if knowledge_base is None:
        return
    knowledge_base.table_count = count_kb_table_structures(db, knowledge_base_id)


def get_kb_table_field_by_id(db: Session, kb_table_field_id: int):
    """根据ID查询知识库表字段"""
    return db.query(models.KbTableField).filter(models.KbTableField.id == kb_table_field_id).first()


def apply_kb_table_field_update(kb_table_field, update_data: dict):
    """应用知识库表字段更新数据"""
    for key, value in update_data.items():
        setattr(kb_table_field, key, value)
    return kb_table_field


def delete_kb_table_field_by_id(db: Session, kb_table_field_id: int):
    """删除知识库表字段"""
    kb_table_field = get_kb_table_field_by_id(db, kb_table_field_id)
    if kb_table_field is None:
        return False
    db.delete(kb_table_field)
    return True


def delete_kb_knowledge_term_by_id(db: Session, kb_knowledge_term_id: int):
    """删除知识库词条"""
    kb_knowledge_term = db.query(models.KbKnowledgeTerm).filter(models.KbKnowledgeTerm.id == kb_knowledge_term_id).first()
    if kb_knowledge_term is None:
        return False
    db.delete(kb_knowledge_term)
    return True


def get_kb_knowledge_term_by_id(db: Session, kb_knowledge_term_id: int):
    """根据ID获取知识库词条"""
    return db.query(models.KbKnowledgeTerm).filter(models.KbKnowledgeTerm.id == kb_knowledge_term_id).first()


def delete_kb_sample_library_by_id(db: Session, kb_sample_library_id: int):
    """删除知识库样例"""
    kb_sample_library = db.query(models.KbSampleLibrary).filter(models.KbSampleLibrary.id == kb_sample_library_id).first()
    if kb_sample_library is None:
        return False
    db.delete(kb_sample_library)
    return True


def get_kb_sample_library_by_id(db: Session, kb_sample_library_id: int):
    """根据ID获取知识库样例"""
    return db.query(models.KbSampleLibrary).filter(models.KbSampleLibrary.id == kb_sample_library_id).first()


def get_knowledge_bases_by_knowledge_term_id(db: Session, knowledge_term_id: int):
    """根据知识词条ID获取所有引用了该词条的知识库"""
    return (
        db.query(models.KnowledgeBase)
        .join(
            models.KbKnowledgeTerm,
            models.KnowledgeBase.id == models.KbKnowledgeTerm.knowledge_base_id
        )
        .filter(
            models.KbKnowledgeTerm.knowledge_term_id == knowledge_term_id,
            models.KnowledgeBase.is_deleted == False,
        )
        .all()
    )


def delete_kb_knowledge_term_by_term_id(db: Session, knowledge_term_id: int):
    """根据知识词条ID删除所有知识库对该词条的引用"""
    db.query(models.KbKnowledgeTerm).filter(
        models.KbKnowledgeTerm.knowledge_term_id == knowledge_term_id
    ).delete(synchronize_session=False)


def get_knowledge_bases_by_sample_id(db: Session, sample_id: int):
    """根据样例ID获取所有引用了该样例的知识库"""
    return (
        db.query(models.KnowledgeBase)
        .join(
            models.KbSampleLibrary,
            models.KnowledgeBase.id == models.KbSampleLibrary.knowledge_base_id
        )
        .filter(
            models.KbSampleLibrary.sample_id == sample_id,
            models.KnowledgeBase.is_deleted == False,
        )
        .all()
    )


def delete_kb_sample_library_by_sample_id(db: Session, sample_id: int):
    """根据样例ID删除所有知识库对该样例的引用"""
    db.query(models.KbSampleLibrary).filter(
        models.KbSampleLibrary.sample_id == sample_id
    ).delete(synchronize_session=False)
