"""Ad-hoc read-only SQL on the selected connection, independent of knowledge bases."""
from contextlib import closing
from datetime import date, datetime, time
from decimal import Decimal
import re
import time as clock

from fastapi import HTTPException
import sqlglot
import sqlparse
from sqlglot import exp

from .service import get_data_source_service, get_decrypted_password

DEFAULT_LIMIT = 100
FETCH_CEILING = 100000


def prepare_query(sql: str, dialect: str):
    value = (sql or '').strip()
    if not value:
        raise HTTPException(400, '请输入 SQL')
    statements = [part for part in sqlparse.split(value) if sqlparse.format(part, strip_comments=True).strip(' ;\n\t')]
    if len(statements) != 1:
        raise HTTPException(400, '每次执行一条 SQL，可选中编辑器中的语句执行')
    try:
        tree = sqlglot.parse_one(value, read=dialect)
    except sqlglot.errors.SqlglotError:
        # SQLGlot is used to add LIMIT and identify writes, not as a dialect
        # whitelist. The selected database validates its own read-only syntax.
        return value.rstrip(';'), False
    # EXPLAIN is represented as Command by some SQLGlot dialects.
    if isinstance(tree, exp.Command) and str(tree.this).upper() == 'EXPLAIN':
        # Skip leading comments without stripping SQL hints or changing literals.
        # Matching against the original commented string used to recurse forever.
        offset = 0
        for token in sqlparse.parse(value)[0].tokens:
            if not (token.is_whitespace or isinstance(token, sqlparse.sql.Comment)
                    or token.ttype in sqlparse.tokens.Comment):
                break
            offset += len(token.value)
        prefix = re.match(r'EXPLAIN\s*(?:\([^)]*\)\s*|(?:ANALYZE\s+|VERBOSE\s+)*)', value[offset:], flags=re.I)
        if prefix is None:
            return value.rstrip(';'), False
        boundary = offset + prefix.end()
        inner = value[boundary:]
        prepared, applied = prepare_query(inner, dialect)
        return value[:boundary] + prepared, applied
    forbidden = (exp.DML, exp.DDL, exp.Into, exp.Lock, exp.Drop, exp.Alter,
                 exp.TruncateTable, exp.Grant, exp.Revoke, exp.Copy)
    if any(isinstance(node, forbidden) for node in tree.walk()):
        raise HTTPException(400, '数据查询仅允许读取，不能新增、修改或删除数据及表结构')
    if isinstance(tree, exp.Query):
        limit = tree.args.get('limit')
        if limit is None:
            tree = tree.limit(DEFAULT_LIMIT)
        return tree.sql(dialect=dialect), limit is None
    if isinstance(tree, exp.Values):
        return f'SELECT * FROM ({tree.sql(dialect=dialect)}) AS query_result LIMIT {DEFAULT_LIMIT}', True
    if isinstance(tree, (exp.Show, exp.Describe)):
        return value.rstrip(';'), False
    # Read-only commands/extensions unknown to SQLGlot are allowed through.
    # INSERT/UPDATE/DELETE/DDL are rejected above and by the database transaction.
    return value.rstrip(';'), False


def _dialect(source):
    kind = str(source.database_type or '').strip().lower()
    if kind in {'postgres', 'postgresql', 'pgsql'}:
        return 'postgres'
    if kind == 'mysql':
        return 'mysql'
    raise HTTPException(400, '数据查询目前支持 PostgreSQL 和 MySQL')


def _connect(source, database=None):
    password = get_decrypted_password(source)
    if _dialect(source) == 'postgres':
        import psycopg2
        return psycopg2.connect(host=source.host, port=source.port, user=source.username,
            password=password, dbname=database or source.default_database, connect_timeout=10)
    import pymysql
    return pymysql.connect(host=source.host, port=source.port, user=source.username,
        password=password, database=database or source.default_database, connect_timeout=10,
        read_timeout=60, write_timeout=15, autocommit=False)


def _value(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, (bytes, memoryview)):
        return bytes(value).hex()
    return value


def query_catalog(db, source_id, *, database=None, space_id=None):
    source = get_data_source_service(db, source_id, space_id)
    dialect = _dialect(source)
    try:
        with closing(_connect(source, database)) as connection:
            with connection.cursor() as cursor:
                if dialect == 'postgres':
                    cursor.execute("SELECT datname FROM pg_database WHERE datallowconn AND NOT datistemplate AND has_database_privilege(datname, 'CONNECT') ORDER BY datname")
                    databases = [r[0] for r in cursor.fetchall()]
                    cursor.execute("SELECT schema_name FROM information_schema.schemata ORDER BY schema_name")
                    schemas = [r[0] for r in cursor.fetchall()]
                else:
                    cursor.execute('SHOW DATABASES')
                    databases = [r[0] for r in cursor.fetchall()]
                    schemas = []
            connection.rollback()
        return {'databases': databases, 'schemas': schemas, 'database': database or source.default_database, 'dialect': dialect}
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(400, _error_message(error, source)) from error


def _error_message(error, source):
    message = str(error)
    password = get_decrypted_password(source)
    if password:
        message = message.replace(password, '***')
    return message


def execute_query(db, source_id, sql, *, database=None, schema=None, space_id=None):
    source = get_data_source_service(db, source_id, space_id)
    dialect = _dialect(source)
    executed_sql, default_limit = prepare_query(sql, dialect)
    started = clock.perf_counter()
    try:
        with closing(_connect(source, database)) as connection:
            try:
                if dialect == 'postgres':
                    connection.set_session(readonly=True, autocommit=False)
                with connection.cursor() as cursor:
                    if dialect == 'postgres':
                        cursor.execute("SELECT set_config('statement_timeout', '60000', true)")
                        if schema:
                            quoted_schema = '"' + schema.replace('"', '""') + '"'
                            cursor.execute("SELECT set_config('search_path', %s, true)", (quoted_schema,))
                    else:
                        cursor.execute('START TRANSACTION READ ONLY')
                    cursor.execute(executed_sql)
                    if cursor.description is None:
                        raise HTTPException(400, '该语句没有可读取的查询结果')
                    used = set()
                    columns = []
                    for index, column in enumerate(cursor.description):
                        name = str(column[0])
                        key = name
                        suffix = 2
                        while key in used:
                            key = f'{name}_{suffix}'
                            suffix += 1
                        used.add(key)
                        columns.append({'key': key, 'name': name})
                    # Metadata commands do not all accept LIMIT. Bound their
                    # displayed results while ordinary queries retain explicit limits.
                    try:
                        is_query = isinstance(sqlglot.parse_one(executed_sql, read=dialect), exp.Query)
                    except sqlglot.errors.SqlglotError:
                        is_query = False
                    maximum = FETCH_CEILING if is_query else DEFAULT_LIMIT
                    records = cursor.fetchmany(maximum + 1)
                    truncated = len(records) > maximum
                    rows = [{column['key']: _value(value) for column, value in zip(columns, record)} for record in records[:maximum]]
            finally:
                connection.rollback()
        return {'sql': executed_sql, 'columns': columns, 'rows': rows, 'row_count': len(rows),
                'elapsed_ms': round((clock.perf_counter() - started) * 1000),
                'default_limit_applied': default_limit, 'truncated': truncated,
                'database': database or source.default_database, 'schema': schema, 'dialect': dialect}
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(400, _error_message(error, source)) from error
