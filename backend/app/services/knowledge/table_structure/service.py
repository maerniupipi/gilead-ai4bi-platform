from fastapi import HTTPException
from sqlalchemy.orm import Session
import os
import pymysql
import psycopg2
from psycopg2.extras import RealDictCursor
from pymysql.cursors import DictCursor
from typing import List

from ....repositories.knowledge.table_structure.repository import (
    apply_table_field_update,
    apply_table_structure_update,
    create_table_field,
    create_table_structure,
    get_table_field_by_id,
    get_table_structure_by_id,
    get_knowledge_access_active_by_id,
    list_table_fields_by_table_structure_id,
    list_enabled_table_fields_by_table_structure_id,
    list_table_structures_by_knowledge_access_id,
    get_existing_table_names,
    batch_create_table_fields,
    delete_table_structure,
)
from ....core.crypto import decrypt_password
from ....repositories.knowledge.data_source.repository import get_data_source_active_by_id
from ....schemas.table_structure import TableInfo, TableFieldInfo, ImportTablesResponse


def _env_int(name: str, default: int, minimum: int = 1) -> int:
    raw = (os.getenv(name) or "").strip()
    try:
        value = int(raw) if raw else default
    except ValueError:
        return default
    return max(minimum, value)


def _connect_external_mysql(data_source):
    return pymysql.connect(
        host=data_source.host,
        port=data_source.port,
        user=data_source.username,
        password=decrypt_password(data_source.password),
        database=data_source.default_database,
        charset='utf8mb4',
        cursorclass=DictCursor,
        connect_timeout=_env_int("EXTERNAL_DB_CONNECT_TIMEOUT_SECONDS", 10),
        read_timeout=_env_int("EXTERNAL_DB_READ_TIMEOUT_SECONDS", 30),
        write_timeout=_env_int("EXTERNAL_DB_WRITE_TIMEOUT_SECONDS", 30),
    )


def _database_type(data_source) -> str:
    return (getattr(data_source, "database_type", "") or "").strip().lower()


def _is_postgresql(data_source) -> bool:
    return _database_type(data_source) in {"postgresql", "postgres", "pgsql"}


def _connect_external_postgresql(data_source):
    schema = "public"
    dbname = (data_source.default_database or "").strip()
    if not dbname or dbname == "public":
        schema = dbname or "public"
        dbname = os.getenv("EXTERNAL_POSTGRES_DEFAULT_DATABASE", "postgres")
    setattr(data_source, "_postgres_schema", schema)
    return psycopg2.connect(
        host=data_source.host,
        port=data_source.port,
        user=data_source.username,
        password=decrypt_password(data_source.password),
        dbname=dbname,
        connect_timeout=_env_int("EXTERNAL_DB_CONNECT_TIMEOUT_SECONDS", 10),
        cursor_factory=RealDictCursor,
    )


def _connect_external_database(data_source):
    if _is_postgresql(data_source):
        return _connect_external_postgresql(data_source)
    if _database_type(data_source) in {"mysql", ""}:
        return _connect_external_mysql(data_source)
    raise HTTPException(status_code=400, detail=f"暂不支持的数据源类型: {data_source.database_type}")


def _db_error_to_http(e: Exception):
    raise HTTPException(status_code=503, detail=f"Database connection error: {str(e)}")


def get_table_structures_service(db: Session, knowledge_access_id: int, space_id: int = None):
    knowledge_access = get_knowledge_access_active_by_id(db, knowledge_access_id, space_id)
    if knowledge_access is None:
        raise HTTPException(status_code=404, detail="Knowledge access not found")
    return list_table_structures_by_knowledge_access_id(db, knowledge_access_id, space_id)


def get_table_fields_service(db: Session, table_structure_id: int):
    table_structure = get_table_structure_by_id(db, table_structure_id)
    if table_structure is None:
        raise HTTPException(status_code=404, detail="Table structure not found")
    return list_table_fields_by_table_structure_id(db, table_structure_id)


def get_enabled_table_fields_service(db: Session, table_structure_id: int):
    """Get only enabled fields for a table structure"""
    table_structure = get_table_structure_by_id(db, table_structure_id)
    if table_structure is None:
        raise HTTPException(status_code=404, detail="Table structure not found")
    return list_enabled_table_fields_by_table_structure_id(db, table_structure_id)


def create_table_structure_service(db: Session, knowledge_access_id: int, table_structure, space_id: int = None):
    knowledge_access = get_knowledge_access_active_by_id(db, knowledge_access_id, space_id)
    if knowledge_access is None:
        raise HTTPException(status_code=404, detail="Knowledge access not found")

    db_table_structure = create_table_structure(db, table_structure.dict(), knowledge_access_id, space_id)
    db.commit()
    db.refresh(db_table_structure)
    return db_table_structure


def update_table_structure_service(db: Session, table_structure_id: int, table_structure_update, space_id: int = None):
    db_table_structure = get_table_structure_by_id(db, table_structure_id, space_id)
    if db_table_structure is None:
        raise HTTPException(status_code=404, detail="Table structure not found")

    update_data = table_structure_update.dict(exclude_unset=True)
    apply_table_structure_update(db, db_table_structure, update_data)
    db.commit()
    db.refresh(db_table_structure)
    return db_table_structure


def create_table_field_service(db: Session, table_structure_id: int, table_field):
    table_structure = get_table_structure_by_id(db, table_structure_id)
    if table_structure is None:
        raise HTTPException(status_code=404, detail="Table structure not found")

    db_table_field = create_table_field(db, table_field.dict(), table_structure_id)
    db.commit()
    db.refresh(db_table_field)
    return db_table_field


def update_table_field_service(db: Session, table_field_id: int, table_field):
    db_table_field = get_table_field_by_id(db, table_field_id)
    if db_table_field is None:
        raise HTTPException(status_code=404, detail="Table field not found")

    update_data = table_field.dict(exclude_unset=True)
    apply_table_field_update(db, db_table_field, update_data)
    db.commit()
    db.refresh(db_table_field)
    return db_table_field


def delete_table_structure_service(db: Session, table_structure_id: int, space_id: int = None):
    """Delete a table structure and its fields"""
    db_table_structure = get_table_structure_by_id(db, table_structure_id, space_id)
    if db_table_structure is None:
        raise HTTPException(status_code=404, detail="Table structure not found")

    delete_table_structure(db, table_structure_id, space_id)
    db.commit()
    return {"message": "Table structure deleted successfully"}


def get_database_tables_service(db: Session, knowledge_access_id: int, space_id: int = None) -> List[TableInfo]:
    """Get list of tables from the external database associated with knowledge access"""
    # Get knowledge access
    knowledge_access = get_knowledge_access_active_by_id(db, knowledge_access_id, space_id)
    if knowledge_access is None:
        raise HTTPException(status_code=404, detail="Knowledge access not found")

    # Get data source
    data_source = get_data_source_active_by_id(db, knowledge_access.data_source_id, space_id)
    if data_source is None:
        raise HTTPException(status_code=404, detail="Data source not found")

    # Get existing table names
    existing_table_names = get_existing_table_names(db, knowledge_access_id, space_id)

    connection = None
    try:
        connection = _connect_external_database(data_source)

        with connection.cursor() as cursor:
            if _is_postgresql(data_source):
                table_infos = _fetch_postgresql_tables(
                    cursor,
                    existing_table_names,
                    getattr(data_source, "_postgres_schema", "public"),
                )
            else:
                table_infos = _fetch_mysql_tables(
                    cursor,
                    data_source.default_database,
                    existing_table_names,
                )

        return table_infos

    except (pymysql.Error, psycopg2.Error) as e:
        _db_error_to_http(e)
    finally:
        if connection is not None:
            connection.close()


def _fetch_mysql_tables(cursor, database_name: str, existing_table_names: set) -> List[TableInfo]:
    cursor.execute("SHOW TABLES")
    tables = cursor.fetchall()

    table_infos = []
    for table in tables:
        table_name = list(table.values())[0]
        cursor.execute("""
            SELECT TABLE_COMMENT
            FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
        """, (database_name, table_name))
        comment_result = cursor.fetchone()
        table_comment = comment_result['TABLE_COMMENT'] if comment_result else None
        table_infos.append(TableInfo(
            table_name=table_name,
            table_comment=table_comment if table_comment else None,
            is_imported=table_name in existing_table_names,
        ))
    return table_infos


def _fetch_postgresql_tables(cursor, existing_table_names: set, schema_name: str = "public") -> List[TableInfo]:
    cursor.execute("""
        SELECT
            n.nspname AS table_schema,
            c.relname AS table_name,
            obj_description(c.oid) AS table_comment
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind IN ('r', 'p')
          AND n.nspname NOT IN ('pg_catalog', 'information_schema')
          AND n.nspname NOT LIKE 'pg_toast%%'
          AND n.nspname = %s
        ORDER BY n.nspname, c.relname
    """, (schema_name,))
    rows = cursor.fetchall()
    table_infos = []
    for row in rows:
        table_name = row["table_name"]
        table_infos.append(TableInfo(
            table_name=table_name,
            table_comment=row.get("table_comment") or None,
            is_imported=table_name in existing_table_names,
        ))
    return table_infos


def get_table_fields_from_database(connection, table_name: str) -> List[TableFieldInfo]:
    """Get field information for a specific table from external database"""
    with connection.cursor() as cursor:
        # Get field information including comments
        cursor.execute(f"""
            SELECT 
                COLUMN_NAME,
                COLUMN_TYPE,
                COLUMN_COMMENT
            FROM information_schema.COLUMNS
            WHERE TABLE_NAME = %s
            ORDER BY ORDINAL_POSITION
        """, (table_name,))
        fields = cursor.fetchall()
        
        return [
            TableFieldInfo(
                field_name=field['COLUMN_NAME'],
                field_type=field['COLUMN_TYPE'],
                field_comment=field['COLUMN_COMMENT'] if field['COLUMN_COMMENT'] else None
            )
            for field in fields
        ]


def map_mysql_type_to_app_type(mysql_type: str) -> str:
    """Map MySQL type to app field type"""
    mysql_type_lower = mysql_type.lower()
    if 'int' in mysql_type_lower:
        return 'int'
    elif 'float' in mysql_type_lower or 'double' in mysql_type_lower or 'decimal' in mysql_type_lower:
        return 'float'
    elif 'date' in mysql_type_lower and 'time' not in mysql_type_lower:
        return 'date'
    elif 'datetime' in mysql_type_lower or 'timestamp' in mysql_type_lower:
        return 'datetime'
    elif 'text' in mysql_type_lower or 'longtext' in mysql_type_lower or 'mediumtext' in mysql_type_lower:
        return 'text'
    else:
        return 'varchar'


def map_database_type_to_app_type(column_type: str) -> str:
    type_lower = (column_type or "").lower()
    if any(t in type_lower for t in ("int", "serial", "bigserial", "smallserial")):
        return "int"
    if any(t in type_lower for t in ("float", "double", "decimal", "numeric", "real")):
        return "float"
    if type_lower == "date":
        return "date"
    if any(t in type_lower for t in ("timestamp", "datetime", "time with", "time without")):
        return "datetime"
    if any(t in type_lower for t in ("text", "json", "xml")):
        return "text"
    return "varchar"


def _fetch_mysql_table_comment(cursor, database_name: str, table_name: str) -> str | None:
    cursor.execute("""
        SELECT TABLE_COMMENT
        FROM information_schema.TABLES
        WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
    """, (database_name, table_name))
    row = cursor.fetchone()
    return row["TABLE_COMMENT"] if row and row.get("TABLE_COMMENT") else None


def _fetch_mysql_columns(cursor, database_name: str, table_name: str) -> List[dict]:
    cursor.execute("""
        SELECT
            COLUMN_NAME AS field_name,
            COLUMN_TYPE AS field_type,
            COLUMN_COMMENT AS field_comment
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
        ORDER BY ORDINAL_POSITION
    """, (database_name, table_name))
    return list(cursor.fetchall())


def _fetch_postgresql_table_comment(cursor, table_name: str, schema_name: str = "public") -> str | None:
    cursor.execute("""
        SELECT obj_description(c.oid) AS table_comment
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relname = %s
          AND c.relkind IN ('r', 'p')
          AND n.nspname NOT IN ('pg_catalog', 'information_schema')
          AND n.nspname = %s
        ORDER BY CASE WHEN n.nspname = 'public' THEN 0 ELSE 1 END, n.nspname
        LIMIT 1
    """, (table_name, schema_name))
    row = cursor.fetchone()
    return row["table_comment"] if row and row.get("table_comment") else None


def _fetch_postgresql_columns(cursor, table_name: str, schema_name: str = "public") -> List[dict]:
    cursor.execute("""
        SELECT
            a.attname AS field_name,
            format_type(a.atttypid, a.atttypmod) AS field_type,
            col_description(a.attrelid, a.attnum) AS field_comment
        FROM pg_attribute a
        JOIN pg_class c ON c.oid = a.attrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relname = %s
          AND c.relkind IN ('r', 'p')
          AND n.nspname NOT IN ('pg_catalog', 'information_schema')
          AND n.nspname = %s
          AND a.attnum > 0
          AND NOT a.attisdropped
        ORDER BY CASE WHEN n.nspname = 'public' THEN 0 ELSE 1 END, n.nspname, a.attnum
    """, (table_name, schema_name))
    return list(cursor.fetchall())


def import_tables_service(db: Session, knowledge_access_id: int, table_names: List[str], space_id: int = None) -> ImportTablesResponse:
    """Import tables with their fields from external database"""
    # Get knowledge access
    knowledge_access = get_knowledge_access_active_by_id(db, knowledge_access_id, space_id)
    if knowledge_access is None:
        raise HTTPException(status_code=404, detail="Knowledge access not found")

    # Get data source
    data_source = get_data_source_active_by_id(db, knowledge_access.data_source_id, space_id)
    if data_source is None:
        raise HTTPException(status_code=404, detail="Data source not found")

    # Get existing table names
    existing_table_names = get_existing_table_names(db, knowledge_access_id, space_id)

    # Filter out already imported tables
    tables_to_import = [name for name in table_names if name not in existing_table_names]

    if not tables_to_import:
        return ImportTablesResponse(
            imported_count=0,
            imported_tables=[]
        )

    # Connect to external database
    connection = None
    try:
        connection = _connect_external_database(data_source)

        imported_tables = []

        with connection.cursor() as cursor:
            for table_name in tables_to_import:
                if _is_postgresql(data_source):
                    schema_name = getattr(data_source, "_postgres_schema", "public")
                    table_comment = _fetch_postgresql_table_comment(cursor, table_name, schema_name)
                    fields = _fetch_postgresql_columns(cursor, table_name, schema_name)
                else:
                    table_comment = _fetch_mysql_table_comment(cursor, data_source.default_database, table_name)
                    fields = _fetch_mysql_columns(cursor, data_source.default_database, table_name)

                # Create table structure
                table_structure_data = {
                    'table_name': table_name,
                    'table_alias': table_comment if table_comment else None
                }
                db_table_structure = create_table_structure(db, table_structure_data, knowledge_access_id, space_id)
                db.flush()  # Get the ID

                # Create field records
                fields_data = []
                for field in fields:
                    fields_data.append({
                        'field_name': field['field_name'],
                        'field_alias': field['field_comment'] if field.get('field_comment') else None,
                        'field_type': map_database_type_to_app_type(field['field_type']),
                        'is_enabled': True,
                        'is_vectorized': False
                    })

                batch_create_table_fields(db, db_table_structure.id, fields_data)
                imported_tables.append(table_name)

        db.commit()

        return ImportTablesResponse(
            imported_count=len(imported_tables),
            imported_tables=imported_tables
        )

    except (pymysql.Error, psycopg2.Error) as e:
        db.rollback()
        _db_error_to_http(e)
    finally:
        if connection is not None:
            connection.close()
