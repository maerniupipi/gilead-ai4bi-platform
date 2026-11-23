from fastapi import HTTPException
from sqlalchemy.orm import Session

from ....core.crypto import encrypt_password, decrypt_password
from ....schemas.data_source import DataSourceTestRequest, DataSourceTestResponse
from ....repositories.knowledge.data_source.repository import (
    apply_data_source_update,
    create_data_source,
    get_data_source_active_by_id,
    get_data_source_active_by_name,
    list_data_sources_active,
    soft_delete_data_source,
)


def create_data_source_service(db: Session, data_source, space_id: int = None):
    existing_data_source = get_data_source_active_by_name(db, data_source.name, space_id)
    if existing_data_source:
        raise HTTPException(status_code=400, detail="Data source name already exists")

    data_dict = data_source.dict()
    # Encrypt password before storing
    if data_dict.get("password"):
        data_dict["password"] = encrypt_password(data_dict["password"])
    if space_id is not None:
        data_dict['space_id'] = space_id
    db_data_source = create_data_source(db, data_dict)
    db.commit()
    db.refresh(db_data_source)
    return db_data_source


def list_data_source_service(db: Session, skip: int, limit: int, space_id: int = None):
    return list_data_sources_active(db, skip, limit, space_id)


def get_data_source_service(db: Session, data_source_id: int, space_id: int = None):
    data_source = get_data_source_active_by_id(db, data_source_id, space_id)
    if data_source is None:
        raise HTTPException(status_code=404, detail="Data source not found")
    return data_source


def update_data_source_service(db: Session, data_source_id: int, data_source_update, space_id: int = None):
    db_data_source = get_data_source_active_by_id(db, data_source_id, space_id)
    if db_data_source is None:
        raise HTTPException(status_code=404, detail="Data source not found")

    # 如果更新名称，检查新名称是否已存在
    if getattr(data_source_update, "name", None) and data_source_update.name != db_data_source.name:
        existing_data_source = get_data_source_active_by_name(db, data_source_update.name, space_id)
        if existing_data_source:
            raise HTTPException(status_code=400, detail="Data source name already exists")

    update_data = data_source_update.dict(exclude_unset=True)
    # Encrypt password before storing (if provided)
    if update_data.get("password"):
        update_data["password"] = encrypt_password(update_data["password"])
    if space_id is not None and 'space_id' not in update_data:
        update_data['space_id'] = space_id
    apply_data_source_update(db, db_data_source, update_data)
    db.commit()
    db.refresh(db_data_source)
    return db_data_source


def delete_data_source_service(db: Session, data_source_id: int, space_id: int = None):
    db_data_source = get_data_source_active_by_id(db, data_source_id, space_id)
    if db_data_source is None:
        raise HTTPException(status_code=404, detail="Data source not found")

    soft_delete_data_source(db, db_data_source)
    db.commit()
    return {"message": "Data source deleted successfully"}


def get_decrypted_password(data_source) -> str:
    """Decrypt the stored password of a data source (for internal consumers)."""
    return decrypt_password(data_source.password)


def reveal_password_service(db: Session, data_source_id: int, space_id: int = None) -> dict:
    """Admin-only: decrypt and return plaintext password."""
    data_source = get_data_source_active_by_id(db, data_source_id, space_id)
    if data_source is None:
        raise HTTPException(status_code=404, detail="Data source not found")
    return {"password": decrypt_password(data_source.password)}


def test_data_source_connection(req: DataSourceTestRequest) -> DataSourceTestResponse:
    """Test database connectivity from form data (plaintext password)."""
    db_type = (req.database_type or "").strip().lower()
    try:
        if db_type in {"postgresql", "postgres", "pgsql"}:
            import psycopg2
            conn = psycopg2.connect(
                host=req.host,
                port=req.port,
                user=req.username,
                password=req.password,
                dbname=req.default_database,
                connect_timeout=5,
            )
            cur = conn.cursor()
            cur.execute("SELECT version()")
            version = cur.fetchone()[0]
            cur.close()
            conn.close()
            return DataSourceTestResponse(
                success=True,
                message="PostgreSQL 连接成功",
                response_data={"version": version},
            )
        elif db_type in {"mysql", ""}:
            import pymysql
            conn = pymysql.connect(
                host=req.host,
                port=req.port,
                user=req.username,
                password=req.password,
                database=req.default_database,
                connect_timeout=5,
            )
            cur = conn.cursor()
            cur.execute("SELECT version()")
            version = cur.fetchone()[0]
            cur.close()
            conn.close()
            return DataSourceTestResponse(
                success=True,
                message="MySQL 连接成功",
                response_data={"version": version},
            )
        else:
            return DataSourceTestResponse(
                success=False,
                message=f"暂不支持的数据源类型: {req.database_type}",
            )
    except Exception as e:
        return DataSourceTestResponse(success=False, message=str(e))
