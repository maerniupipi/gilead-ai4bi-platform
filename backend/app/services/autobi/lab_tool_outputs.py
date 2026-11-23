"""Return intermediate results from the same pipeline used by the laboratory editor."""

from sqlglot import exp, parse
from sqlglot.errors import SqlglotError


def output_stage(advanced, features):
    configured = advanced.get("output_stage")
    requested = features.get("lab_output")
    stage = requested or configured
    if stage is not None and stage not in ("recall", "sql"):
        raise ValueError("未知的实验室输出阶段")
    if requested and configured and requested != configured:
        raise ValueError("所选实验室与请求的输出阶段不匹配")
    return stage


def recall_items(by_step):
    items = []
    seen = set()
    for step, kind in ((3, "knowledge_term"), (6, "table_column"), (7, "table_value"),
                       (11, "table_value"), (12, "table_value"), (9, "table_value"), (1, "table_value")):
        response = (by_step.get(step) or {}).get("response") or {}
        for hit in response.get("results") or ():
            meta = hit.get("metadata") or {}
            term = str(meta.get("data_detail") or meta.get("field_value") or hit.get("content") or "")
            table = str(meta.get("field_table") or "")
            field = str(meta.get("field_code") or "")
            key = (kind, table, field, term)
            if term and key not in seen:
                seen.add(key)
                items.append({"type": kind, "table": table, "field": field, "text": term[:1800],
                              "content": str(meta.get("quote_extend") or "")[:1800]})
    return items


def sql_output(sql, scope, policy, database_type=None):
    sql = (sql or "").strip()
    dialect = (database_type or "").lower()
    dialect = {"postgresql": "postgres", "mssql": "tsql", "sqlserver": "tsql"}.get(dialect, dialect)
    try:
        statements = parse(sql, read=dialect or None) if sql else []
    except (SqlglotError, ValueError):
        statements = []
    if (len(statements) != 1 or not isinstance(statements[0], (exp.Select, exp.SetOperation))
            or any(isinstance(n, (exp.DML, exp.DDL, exp.Into, exp.Lock)) for n in statements[0].walk())):
        return {"kind": "clarification", "message": "实验室未生成可用的只读 SQL，请补全原子问题或检查生成 SQL 的提示词。"}
    if scope and scope.get("mode") != "all":
        if policy != "ddi" or scope.get("mode") != "restricted":
            raise ValueError("实验室缺少适用的数据范围授权")
        from .ddi_atomic_samples import sample_sql
        sql = sample_sql(sql, scope)
    return {"kind": "sql", "sql": sql}
