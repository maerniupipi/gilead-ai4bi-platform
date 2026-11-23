"""Adapted from synchronization pipeline/utils/copy_loader.py; transactional stage replacement.
"""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from sqlalchemy import Engine, text

from .schema import (
    create_stage_table_if_missing,
    quote_ident,
    quote_table_name,
    validate_table_structures_match,
)


def create_work_dir(prefix: str, root_dir: str = "tmp") -> str:
    os.makedirs(root_dir, exist_ok=True)
    return tempfile.mkdtemp(prefix=f"{prefix}_", dir=root_dir)


def cleanup_old_work_dirs(prefix: str, root_dir: str = "tmp") -> None:
    root_path = Path(root_dir)
    if not root_path.exists():
        return
    for path in root_path.glob(f"{prefix}_*"):
        if path.is_dir():
            cleanup_work_dir(str(path))


def cleanup_work_dir(path: str) -> None:
    shutil.rmtree(path, ignore_errors=True)


def write_tsv_part(
    work_dir: str,
    table_name: str,
    page_no: int,
    columns: list[str],
    records: list[dict],
) -> tuple[str, int]:
    file_path = Path(work_dir) / f"{table_name}_part_{page_no:06d}.tsv"
    expected_columns = set(columns)
    with open(file_path, "w", encoding="utf-8", newline="") as f:
        f.write(_copy_row(columns))
        for row_idx, record in enumerate(records):
            _validate_copy_columns(table_name, page_no, row_idx, expected_columns, record)
            f.write(_copy_row(record.get(column) for column in columns))
    return str(file_path), len(records)


def copy_parts_to_stage(
    engine: Engine,
    table_name: str,
    columns: list[str],
    part_files: list[str],
    expected_count: int,
    on_part=None,
) -> None:
    stage_table = create_stage_table_if_missing(engine, table_name)
    validate_table_structures_match(engine, table_name, stage_table)

    raw_conn = engine.raw_connection()
    try:
        cursor = raw_conn.cursor()
        cursor.execute(f"TRUNCATE TABLE {quote_table_name(stage_table)}")
        for index, part_file in enumerate(part_files, 1):
            with open(part_file, "r", encoding="utf-8", newline="") as f:
                cursor.copy_expert(_copy_sql(stage_table, columns), f)
            if on_part is not None:
                on_part(index, len(part_files))
        cursor.execute(f"SELECT COUNT(*) FROM {quote_table_name(stage_table)}")
        actual_count = cursor.fetchone()[0]
        if actual_count != expected_count:
            raise RuntimeError(
                f"Stage table {stage_table} row count mismatch: "
                f"expected {expected_count}, got {actual_count}"
            )
        raw_conn.commit()
    except Exception:
        raw_conn.rollback()
        raise
    finally:
        raw_conn.close()


def replace_table_from_stage(
    engine: Engine,
    table_name: str,
    columns: list[str],
    expected_count: int,
) -> None:
    stage_table = f"{table_name}_stage"
    column_list = _column_list(columns)
    with engine.begin() as conn:
        # MVCC readers keep seeing the previous committed snapshot throughout
        # replacement. TRUNCATE would hold ACCESS EXCLUSIVE for the whole copy.
        conn.execute(text("SET LOCAL lock_timeout = '5s'"))
        conn.execute(text(f"DELETE FROM {quote_table_name(table_name)}"))
        conn.execute(
            text(
                f"INSERT INTO {quote_table_name(table_name)} ({column_list}) "
                f"SELECT {column_list} FROM {quote_table_name(stage_table)}"
            )
        )
        actual_count = conn.execute(
            text(f"SELECT COUNT(*) FROM {quote_table_name(table_name)}")
        ).scalar_one()
        if actual_count != expected_count:
            raise RuntimeError(
                f"Table {table_name} row count mismatch: "
                f"expected {expected_count}, got {actual_count}"
            )


def _copy_sql(table_name: str, columns: list[str]) -> str:
    return (
        f"COPY {quote_table_name(table_name)} ({_column_list(columns)}) "
        "FROM STDIN WITH (FORMAT csv, DELIMITER E'\\t', NULL '\\N', HEADER true)"
    )


def _column_list(columns: list[str]) -> str:
    return ", ".join(quote_ident(column) for column in columns)


def _copy_value(value):
    if value is None:
        return r"\N"
    return _quote_copy_value(str(value))


def _copy_row(values) -> str:
    return "\t".join(_copy_value(value) for value in values) + "\n"


def _quote_copy_value(value: str) -> str:
    needs_quote = (
        value == r"\N"
        or value == ""
        or "\t" in value
        or "\n" in value
        or "\r" in value
        or '"' in value
    )
    if not needs_quote:
        return value
    return '"' + value.replace('"', '""') + '"'


def _validate_copy_columns(
    table_name: str,
    page_no: int,
    row_idx: int,
    expected_columns: set[str],
    record: dict,
) -> None:
    row_columns = set(record.keys())
    missing_columns = sorted(expected_columns - row_columns)
    extra_columns = sorted(row_columns - expected_columns)
    if missing_columns or extra_columns:
        raise RuntimeError(
            f"COPY column mismatch for {table_name} page {page_no} row {row_idx}: "
            f"missing={missing_columns}, extra={extra_columns}"
        )
