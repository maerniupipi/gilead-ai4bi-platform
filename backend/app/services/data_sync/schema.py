"""Adapted from synchronization pipeline/utils/schema.py; preserves schema validation.
"""
from __future__ import annotations

import datetime as dt
import re
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import Engine, text


def quote_ident(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def split_table_name(table_name: str) -> tuple[str, str]:
    if "." in table_name:
        schema_name, plain_table_name = table_name.split(".", 1)
        return schema_name, plain_table_name
    return "public", table_name


def quote_table_name(table_name: str) -> str:
    schema_name, plain_table_name = split_table_name(table_name)
    return f"{quote_ident(schema_name)}.{quote_ident(plain_table_name)}"


def get_table_columns(engine: Engine, table_name: str) -> dict[str, dict[str, Any]]:
    schema_name, plain_table_name = split_table_name(table_name)
    sql = text(
        """
        SELECT
            column_name,
            data_type,
            udt_name,
            character_maximum_length,
            numeric_precision,
            numeric_scale,
            datetime_precision,
            ordinal_position
        FROM information_schema.columns
        WHERE table_schema = :schema_name
          AND table_name = :table_name
        ORDER BY ordinal_position
        """
    )
    with engine.connect() as conn:
        rows = conn.execute(
            sql, {"schema_name": schema_name, "table_name": plain_table_name}
        ).mappings().all()
    return {row["column_name"]: dict(row) for row in rows}


def ensure_table_exists(engine: Engine, table_name: str) -> None:
    if not get_table_columns(engine, table_name):
        raise RuntimeError(f"Target table does not exist: {table_name}")


def get_ordered_table_column_names(engine: Engine, table_name: str) -> list[str]:
    columns = get_table_columns(engine, table_name)
    if not columns:
        raise RuntimeError(f"Target table does not exist: {table_name}")
    return [
        column_name
        for column_name, _meta in sorted(
            columns.items(), key=lambda item: item[1]["ordinal_position"]
        )
    ]


def create_stage_table_if_missing(engine: Engine, table_name: str) -> str:
    ensure_table_exists(engine, table_name)
    stage_table = f"{table_name}_stage"
    stage_columns = get_table_columns(engine, stage_table)
    if stage_columns:
        validate_table_structures_match(engine, table_name, stage_table)
        return stage_table

    with engine.begin() as conn:
        conn.execute(
            text(
                f"CREATE TABLE {quote_table_name(stage_table)} "
                f"(LIKE {quote_table_name(table_name)} INCLUDING ALL)"
            )
        )
    return stage_table


def validate_table_structures_match(
    engine: Engine,
    source_table: str,
    target_table: str,
) -> None:
    source_columns = get_table_columns(engine, source_table)
    target_columns = get_table_columns(engine, target_table)
    if not source_columns:
        raise RuntimeError(f"Source table does not exist: {source_table}")
    if not target_columns:
        raise RuntimeError(f"Target table does not exist: {target_table}")

    source_names = set(source_columns.keys())
    target_names = set(target_columns.keys())
    missing_columns = sorted(source_names - target_names)
    extra_columns = sorted(target_names - source_names)
    if missing_columns or extra_columns:
        raise RuntimeError(
            f"Stage table structure mismatch: {target_table}; "
            f"missing={missing_columns}, extra={extra_columns}"
        )

    type_errors = []
    for column_name in sorted(source_names):
        source_meta = source_columns[column_name]
        target_meta = target_columns[column_name]
        comparable_fields = [
            "data_type",
            "udt_name",
            "character_maximum_length",
            "numeric_precision",
            "numeric_scale",
        ]
        for field_name in comparable_fields:
            if source_meta[field_name] != target_meta[field_name]:
                type_errors.append(
                    f"{column_name}.{field_name}: "
                    f"{source_meta[field_name]} != {target_meta[field_name]}"
                )

    if type_errors:
        raise RuntimeError(
            f"Stage table type mismatch for {target_table}: "
            + "; ".join(type_errors)
        )


def normalize_record_columns(
    data: list[dict],
    normalize_columns: str = "lower",
) -> list[dict]:
    mapped_rows = []
    for row_idx, row in enumerate(data):
        mapped_row = {}
        for source_name, value in row.items():
            target_name = _normalize_column_name(source_name, normalize_columns)
            if target_name in mapped_row:
                raise RuntimeError(
                    f"Row {row_idx} has duplicate normalized column: {target_name}"
                )
            mapped_row[target_name] = value
        mapped_rows.append(mapped_row)
    return mapped_rows


def _normalize_column_name(column_name: str, mode: str) -> str:
    if mode == "lower":
        return column_name.lower()
    if mode in {"none", ""}:
        return column_name
    raise RuntimeError(f"Unsupported column normalization mode: {mode}")


def validate_records_against_table(
    engine: Engine,
    table_name: str,
    records: list[dict],
    *,
    require_exact_columns: bool = True,
) -> dict[str, Any]:
    if not records:
        raise RuntimeError("No records available for schema validation")

    table_columns = get_table_columns(engine, table_name)
    if not table_columns:
        raise RuntimeError(f"Target table does not exist: {table_name}")

    table_column_names = set(table_columns.keys())
    api_columns = set()
    for row_idx, record in enumerate(records):
        row_columns = set(record.keys())
        api_columns.update(row_columns)
        if require_exact_columns:
            missing_columns = sorted(table_column_names - row_columns)
            extra_columns = sorted(row_columns - table_column_names)
            if missing_columns or extra_columns:
                raise RuntimeError(
                    f"Schema column mismatch for {table_name} row {row_idx}: "
                    f"missing={missing_columns}, extra={extra_columns}"
                )

    type_errors: list[str] = []
    unchecked_null_only: list[str] = []
    for column_name in sorted(api_columns & table_column_names):
        values = [
            record.get(column_name)
            for record in records
            if record.get(column_name) is not None
        ]
        if not values:
            unchecked_null_only.append(column_name)
            continue
        column_meta = table_columns[column_name]
        for value in values[:20]:
            if not _value_matches_pg_type(value, column_meta):
                type_errors.append(
                    f"{column_name}: value={value!r} incompatible with "
                    f"{column_meta['data_type']}"
                )
                break

    if type_errors:
        raise RuntimeError(
            f"Schema type mismatch for {table_name}: " + "; ".join(type_errors)
        )

    return {
        "table": table_name,
        "columns": sorted(api_columns),
        "unchecked_null_only": unchecked_null_only,
    }


def _value_matches_pg_type(value: Any, column_meta: dict[str, Any]) -> bool:
    data_type = column_meta["data_type"]
    udt_name = column_meta["udt_name"]

    if data_type in {"bigint", "integer", "smallint"} or udt_name in {"int8", "int4", "int2"}:
        return _is_integer(value)
    if data_type in {"numeric", "decimal", "real", "double precision"}:
        return _is_numeric(value)
    if data_type in {"character varying", "character", "text"}:
        return _is_scalar(value)
    if data_type == "date":
        return _is_date(value)
    if data_type.startswith("timestamp"):
        return _is_timestamp(value)
    if data_type == "boolean":
        return isinstance(value, bool) or str(value).lower() in {"true", "false", "0", "1"}
    return True


def _is_scalar(value: Any) -> bool:
    return isinstance(value, (str, int, float, bool, Decimal, dt.date, dt.datetime))


def _is_integer(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return True
    if isinstance(value, str):
        return bool(re.fullmatch(r"[-+]?\d+", value.strip()))
    return False


def _is_numeric(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float, Decimal)):
        return True
    if isinstance(value, str):
        try:
            Decimal(value.strip())
            return True
        except (InvalidOperation, ValueError):
            return False
    return False


def _is_date(value: Any) -> bool:
    if isinstance(value, dt.datetime):
        return True
    if isinstance(value, dt.date):
        return True
    if not isinstance(value, str):
        return False
    text_value = value.strip()
    try:
        dt.date.fromisoformat(text_value)
        return True
    except ValueError:
        return False


def _is_timestamp(value: Any) -> bool:
    if isinstance(value, dt.datetime):
        return True
    if isinstance(value, dt.date):
        return True
    if not isinstance(value, str):
        return False
    text_value = value.strip().replace("Z", "+00:00")
    try:
        dt.datetime.fromisoformat(text_value)
        return True
    except ValueError:
        return _is_date(text_value)
