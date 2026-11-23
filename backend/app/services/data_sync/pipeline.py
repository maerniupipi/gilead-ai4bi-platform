"""Configurable HTTP JSON ingestion with validated, atomic table replacement."""
from concurrent.futures import ThreadPoolExecutor
import time

import httpx
import pandas as pd
from sqlalchemy import create_engine, text

from . import loader, schema


class ApiClient:
    def __init__(self, config, transport=None, sleeper=time.sleep):
        self.config = config
        self.transport = transport
        self.sleeper = sleeper

    def _request(self, page_no):
        cfg = self.config
        for attempt in range(cfg.retry_times):
            try:
                with httpx.Client(timeout=cfg.timeout, transport=self.transport, follow_redirects=False) as client:
                    params = {**cfg.request_params, cfg.page_param: page_no, cfg.page_size_param: cfg.page_size}
                    response = client.request(cfg.method, cfg.base_url, headers=cfg.headers,
                        **({"params": params} if cfg.method == "GET" else {"json": params}))
                response.raise_for_status()
                records = response.json()
                if cfg.records_path:
                    for key in cfg.records_path.split("."):
                        if not isinstance(records, dict) or key not in records:
                            raise RuntimeError("源接口缺少配置的记录路径")
                        records = records[key]
                if not isinstance(records, list) or any(not isinstance(item, dict) for item in records):
                    raise RuntimeError("源接口 data 必须是对象数组")
                if len(records) > cfg.page_size:
                    raise RuntimeError("源接口返回行数大于请求的分页大小")
                return records
            except (httpx.HTTPError, ValueError, RuntimeError) as exc:
                if attempt + 1 == cfg.retry_times:
                    # HTTP exceptions may contain a credential-bearing URL or body.
                    raise RuntimeError(f"源接口第 {page_no} 页请求失败（{type(exc).__name__}）") from None
                self.sleeper(2 ** (attempt + 1))

    def pages(self):
        cfg = self.config
        workers = cfg.max_workers
        with ThreadPoolExecutor(max_workers=workers) as executor:
            for start in range(1, cfg.max_pages + 1, workers):
                numbers = range(start, min(start + workers, cfg.max_pages + 1))
                futures = {number: executor.submit(self._request, number) for number in numbers}
                for number, future in futures.items():
                    records = future.result()
                    if records:
                        yield number, records
                    # totalCount is intentionally not used: it is unreliable upstream.
                    if len(records) < cfg.page_size:
                        for pending in futures.values():
                            pending.cancel()
                        return
        raise RuntimeError("分页超过 max_pages 上限，旧表保留")


def _validate_count(config, count):
    if count < config.min_rows:
        raise RuntimeError(f"数据量 {count} 低于门禁 {config.min_rows}，旧表保留")


def _small_table(engine, config, client, progress):
    records = []
    for page, rows in client.pages():
        normalized = schema.normalize_record_columns(rows, config.column_case)
        schema.validate_records_against_table(engine, config.target_table, normalized)
        records.extend(normalized)
        progress(stage="fetching", page_no=page, fetched_rows=len(records), message=f"第 {page} 页已校验")
    _validate_count(config, len(records))
    progress(stage="replacing", total_rows=len(records), message="校验通过，事务内写入目标数据")
    # DataFrame.to_sql preserves rollback through the externally managed connection.
    schema_name, table_name = schema.split_table_name(config.target_table)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE TABLE {schema.quote_table_name(config.target_table)}"))
        pd.DataFrame(records).to_sql(table_name, conn, schema=schema_name, if_exists="append", index=False,
                                     method="multi", chunksize=min(5000, max(1, 30000 // len(records[0]))))
        actual = conn.execute(text(f"SELECT COUNT(*) FROM {schema.quote_table_name(config.target_table)}")).scalar_one()
        if actual != len(records):
            raise RuntimeError("目标表行数不符，事务已回滚")
    return len(records)


def _large_table(engine, config, client, progress, run_id):
    columns = schema.get_ordered_table_column_names(engine, config.target_table)
    # Keep other runs' failed artifacts; only this run's directory is removed on success.
    work_dir = loader.create_work_dir(config.table_key + "_" + run_id, config.tmp_dir)
    files, part_counts, buffered = [], [], []
    fetched = 0
    source_rows = 0

    def flush(records):
        filename, count = loader.write_tsv_part(work_dir, config.table_key, len(files) + 1, columns, records)
        files.append(filename)
        part_counts.append(count)

    for page, records in client.pages():
        normalized = schema.normalize_record_columns(records, config.column_case)
        schema.validate_records_against_table(engine, config.target_table, normalized)
        source_rows += len(normalized)
        buffered.extend(normalized)
        fetched += len(normalized)
        while len(buffered) >= config.part_rows:
            flush(buffered[:config.part_rows])
            del buffered[:config.part_rows]
        progress(stage="fetching", page_no=page, fetched_rows=fetched,
                 message=f"第 {page} 页已校验；源数据 {source_rows} 行，有效 {fetched} 行，分片 {len(files)} 个")
    if buffered:
        flush(buffered)
    _validate_count(config, fetched)
    progress(stage="staging", total_rows=fetched, message=f"分页校验完成，开始 COPY {len(files)} 个分片")
    loaded = 0

    def on_part(index, total):
        nonlocal loaded
        loaded += part_counts[index - 1]
        progress(stage="staging", loaded_rows=loaded, message=f"COPY 分片 {index}/{total} 完成，待提交暂存表")

    loader.copy_parts_to_stage(engine, config.target_table, columns, files, fetched, on_part=on_part)
    progress(stage="replacing", message="暂存表已校验，事务内替换正式表")
    loader.replace_table_from_stage(engine, config.target_table, columns, fetched)
    loader.cleanup_work_dir(work_dir)
    return fetched


def run_pipeline(config, progress, run_id, *, engine=None, client=None):
    own_engine = engine is None
    engine = engine or create_engine(config.database_url, pool_pre_ping=True, pool_size=3, max_overflow=1,
        connect_args={"connect_timeout": 15, "options": f"-c statement_timeout={config.statement_timeout_ms}"})
    lock_key = ".".join(schema.split_table_name(config.target_table))
    try:
        progress(stage="preparing", message="检查目标表及 PostgreSQL 运行锁")
        # Keep this connection for the entire run; its advisory lock is session-scoped.
        with engine.connect() as guard:
            acquired = guard.execute(text("SELECT pg_try_advisory_lock(hashtext('ai4bi_data_sync'), hashtext(:key))"),
                                     {"key": lock_key}).scalar_one()
            guard.commit()
            if not acquired:
                raise RuntimeError("该表已有同步进程运行")
            try:
                schema.ensure_table_exists(engine, config.target_table)
                progress(stage="fetching", message="开始分页拉取并校验数据")
                return _large_table(engine, config, client or ApiClient(config), progress, run_id)
            finally:
                guard.execute(text("SELECT pg_advisory_unlock(hashtext('ai4bi_data_sync'), hashtext(:key))"),
                              {"key": lock_key})
                guard.commit()
    finally:
        if own_engine:
            engine.dispose()
