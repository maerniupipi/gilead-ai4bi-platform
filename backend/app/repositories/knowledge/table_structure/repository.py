from sqlalchemy.orm import Session

from .... import models


def get_knowledge_access_active_by_id(db: Session, knowledge_access_id: int, space_id: int = None):
    query = db.query(models.KnowledgeAccess).filter(
        models.KnowledgeAccess.id == knowledge_access_id,
        models.KnowledgeAccess.is_deleted == False,
    )
    if space_id is not None:
        query = query.filter(models.KnowledgeAccess.space_id == space_id)
    return query.first()


def list_table_structures_by_knowledge_access_id(db: Session, knowledge_access_id: int, space_id: int = None):
    query = db.query(models.TableStructure).filter(
        models.TableStructure.knowledge_access_id == knowledge_access_id
    )
    if space_id is not None:
        query = query.filter(models.TableStructure.space_id == space_id)
    return query.all()


def get_table_structure_by_id(db: Session, table_structure_id: int, space_id: int = None):
    query = db.query(models.TableStructure).filter(models.TableStructure.id == table_structure_id)
    if space_id is not None:
        query = query.filter(models.TableStructure.space_id == space_id)
    return query.first()


def create_table_structure(db: Session, table_structure_data: dict, knowledge_access_id: int, space_id: int = None):
    if space_id is not None:
        table_structure_data['space_id'] = space_id
    db_table_structure = models.TableStructure(**table_structure_data, knowledge_access_id=knowledge_access_id)
    db.add(db_table_structure)
    return db_table_structure


def apply_table_structure_update(db: Session, db_table_structure, update_data: dict):
    for key, value in update_data.items():
        setattr(db_table_structure, key, value)
    return db_table_structure


def list_table_fields_by_table_structure_id(db: Session, table_structure_id: int):
    return (
        db.query(models.TableField)
        .filter(models.TableField.table_structure_id == table_structure_id)
        .all()
    )


def list_enabled_table_fields_by_table_structure_id(db: Session, table_structure_id: int):
    """Get only enabled fields for a table structure"""
    return (
        db.query(models.TableField)
        .filter(
            models.TableField.table_structure_id == table_structure_id,
            models.TableField.is_enabled == True
        )
        .all()
    )


def create_table_field(db: Session, table_field_data: dict, table_structure_id: int):
    db_table_field = models.TableField(**table_field_data, table_structure_id=table_structure_id)
    db.add(db_table_field)
    return db_table_field


def get_table_field_by_id(db: Session, table_field_id: int):
    return db.query(models.TableField).filter(models.TableField.id == table_field_id).first()


def apply_table_field_update(db: Session, db_table_field, update_data: dict):
    for key, value in update_data.items():
        setattr(db_table_field, key, value)
    return db_table_field


def get_existing_table_names(db: Session, knowledge_access_id: int, space_id: int = None):
    """Get list of existing table names for a knowledge access"""
    query = db.query(models.TableStructure.table_name).filter(
        models.TableStructure.knowledge_access_id == knowledge_access_id
    )
    if space_id is not None:
        query = query.filter(models.TableStructure.space_id == space_id)
    results = query.all()
    return [r[0] for r in results]


def batch_create_table_fields(db: Session, table_structure_id: int, fields_data: list):
    """Batch create table fields"""
    db_fields = []
    for field_data in fields_data:
        db_field = models.TableField(
            table_structure_id=table_structure_id,
            **field_data
        )
        db.add(db_field)
        db_fields.append(db_field)
    return db_fields


def delete_table_structure(db: Session, table_structure_id: int, space_id: int = None):
    """Delete a table structure by ID"""
    db_table_structure = get_table_structure_by_id(db, table_structure_id, space_id)
    if db_table_structure:
        db.delete(db_table_structure)
        return True
    return False

