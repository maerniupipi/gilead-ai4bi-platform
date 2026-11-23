"""
XLSX 表格智能问答 · SQL 安全校验 & 执行器

LLM 生成的 SQL 直接打进 MySQL 前必须双层校验：
  1. 结构层：sqlparse 解析，只允许单条 SELECT；禁用所有写入/DDL/DCL。
  2. 白名单层：FROM 的表必须 ∈ 允许表集合（当前文档的动态表 + 可选子查询别名）。
  3. 包层：若 LLM 忘记 LIMIT，自动在外层套一个 LIMIT。

公开 API：
  - validate_select_sql(sql, allowed_tables) → normalized_sql
  - run_select(engine, sql, allowed_tables, max_rows, timeout_ms)
    → (columns, rows, fetched_row_count, truncated)
    ``fetched_row_count`` is ``len(rows)`` (never greater than ``max_rows``).
    ``truncated`` is true iff the server still had at least one more row beyond ``max_rows``.
"""
from __future__ import annotations

import logging
import re
from typing import Iterable, List, Sequence, Tuple

import sqlparse
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlparse.sql import (
    Identifier,
    IdentifierList,
    Parenthesis,
    TokenList,
)
from sqlparse.tokens import DML, Keyword, Punctuation

logger = logging.getLogger(__name__)


class SqlSafetyError(ValueError):
    """SQL 安全校验失败。"""


_FORBIDDEN_KEYWORDS = {
    # 写 / 破坏类：SELECT-only 已在 get_type() 校验中兜底，这里做深度扫描防子查询偷渡
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE", "CREATE",
    "GRANT", "REVOKE", "USE", "CALL", "SHOW", "RENAME",
    "LOCK", "UNLOCK", "HANDLER", "LOAD", "COMMIT", "ROLLBACK", "SAVEPOINT",
    "SET",
    # 注意：不要把 REPLACE / MERGE 列进来——REPLACE 是常用 MySQL 字符串函数
    # （REPLACE(col, ',', '')）；DML 形式的 REPLACE INTO 已由 SELECT-only 拦截。
}


def validate_select_sql(sql: str, allowed_tables: Iterable[str]) -> str:
    """校验并返回"规范化"后的 SQL（若缺 LIMIT 会在外层包一层）。"""
    if not sql or not sql.strip():
        raise SqlSafetyError("SQL 为空")

    raw = sql.strip().rstrip(";")
    # 去掉 trailing 分号后不允许再出现分号（防止多语句）
    if ";" in raw:
        raise SqlSafetyError("SQL 中不允许出现分号 (;)")

    statements = sqlparse.parse(raw)
    non_empty = [s for s in statements if s.tokens and str(s).strip()]
    if len(non_empty) != 1:
        raise SqlSafetyError("仅允许一条 SQL 语句")

    stmt = non_empty[0]
    stmt_type = (stmt.get_type() or "").upper()
    if stmt_type != "SELECT":
        raise SqlSafetyError(f"仅允许 SELECT 语句（当前：{stmt_type or 'UNKNOWN'}）")

    # 深度扫描禁用关键字（防止子查询/CTE 混入）
    upper = raw.upper()
    for kw in _FORBIDDEN_KEYWORDS:
        if re.search(rf"\b{kw}\b", upper):
            raise SqlSafetyError(f"禁用的 SQL 关键字：{kw}")

    # CTE (WITH 子句) 中定义的临时表名也算合法，加入白名单。
    cte_names = _extract_cte_names(stmt)

    # 提取所有涉及的表，做白名单校验
    allowed = {t.lower() for t in allowed_tables} | {n.lower() for n in cte_names}
    referenced = _extract_tables(stmt)
    if not referenced:
        raise SqlSafetyError("无法识别 SQL 中引用的表")
    for t in referenced:
        if t.lower() not in allowed:
            raise SqlSafetyError(f"不允许访问的表：{t}")

    # 若没有 LIMIT，外层包一层
    return raw


def inject_limit(sql: str, default_limit: int) -> str:
    """若未显式 LIMIT，追加 `LIMIT N`；已有则不动。"""
    if re.search(r"\blimit\b\s+\d+", sql, flags=re.IGNORECASE):
        return sql
    return f"{sql}\nLIMIT {int(default_limit)}"


def run_select(
    engine: Engine,
    sql: str,
    *,
    allowed_tables: Sequence[str],
    max_rows: int = 1000,
    timeout_ms: int = 10000,
) -> Tuple[List[str], List[list], int, bool]:
    """校验 + 执行 SELECT，返回 (columns, rows, fetched_row_count, truncated)。

    ``fetched_row_count`` 恒为 ``len(rows)``（至多 ``max_rows`` 行）。
    ``truncated`` 为真表示结果集在 LIMIT 之外仍至少还有一行未返回。
    """
    safe_sql = validate_select_sql(sql, allowed_tables)
    safe_sql = inject_limit(safe_sql, max_rows)

    # MySQL 8 的硬超时：MAX_EXECUTION_TIME（毫秒）作为 optimizer hint
    postgres = engine.dialect.name == "postgresql"
    if postgres:
        import sqlglot
        from sqlglot import exp
        tree = sqlglot.parse_one(safe_sql, read="mysql")
        permitted = {name.lower() for name in allowed_tables}
        permitted.update(cte.alias.lower() for cte in tree.find_all(exp.CTE))
        if any(t.db or t.catalog or t.name.lower() not in permitted for t in tree.find_all(exp.Table)):
            raise SqlSafetyError("只能读取当前工作表")
        safe_sql = tree.sql(dialect="postgres")
    elif not safe_sql.lower().lstrip().startswith("select /*+"):
        safe_sql = re.sub(
            r"^\s*select\b",
            f"SELECT /*+ MAX_EXECUTION_TIME({int(timeout_ms)}) */",
            safe_sql,
            count=1,
            flags=re.IGNORECASE,
        )

    logger.info("xlsx_qa.sql.exec allowed=%s sql=%s", list(allowed_tables), safe_sql)
    with engine.connect() as conn:
        if postgres:
            conn.exec_driver_sql("SET TRANSACTION READ ONLY")
            conn.exec_driver_sql(f"SET LOCAL statement_timeout = {int(timeout_ms)}")
        cursor = conn.execute(text(safe_sql))
        columns = list(cursor.keys())
        fetched = cursor.fetchmany(max_rows + 1)
        truncated = len(fetched) > max_rows
        rows = [list(r) for r in fetched[:max_rows]]
    return columns, rows, len(rows), truncated


# ---------------------------------------------------------------------------
# 表名抽取（基于 sqlparse token 树）
# ---------------------------------------------------------------------------

def _extract_tables(stmt: TokenList) -> List[str]:
    """递归收集 FROM / JOIN 后的表名（一期禁 JOIN，但仍做完整解析避免漏报）。"""
    tables: List[str] = []
    _walk_from(stmt, tables, in_from=False)
    # 去重保序
    seen = set()
    result: List[str] = []
    for t in tables:
        key = t.lower()
        if key not in seen:
            seen.add(key)
            result.append(t)
    return result


def _walk_from(token_list: TokenList, acc: List[str], *, in_from: bool) -> None:
    for tok in token_list.tokens:
        if tok.ttype is Keyword and tok.normalized.upper() in {"FROM", "JOIN"}:
            in_from = True
            continue
        # sqlparse 常把 "ORDER BY" / "GROUP BY" 合成一个 Keyword（normalized 为整串），
        # 不能只匹配 "ORDER"，否则 in_from 无法结束，会把 ORDER BY 后的列名误当成表名。
        if tok.ttype is Keyword and tok.normalized.upper() in {
            "WHERE",
            "GROUP",
            "GROUP BY",
            "HAVING",
            "ORDER",
            "ORDER BY",
            "LIMIT",
            "OFFSET",
            "UNION",
            "ON",
            "USING",
        }:
            in_from = False
        if in_from:
            # 派生表（子查询 as t）：递归进入子查询找真正的基表，**不要**把派生别名当表。
            if isinstance(tok, Identifier) and _is_derived_table(tok):
                for sub in tok.tokens:
                    if isinstance(sub, Parenthesis):
                        _walk_from(sub, acc, in_from=False)
                continue
            if isinstance(tok, IdentifierList):
                for item in tok.get_identifiers():
                    if isinstance(item, Identifier) and _is_derived_table(item):
                        for sub in item.tokens:
                            if isinstance(sub, Parenthesis):
                                _walk_from(sub, acc, in_from=False)
                        continue
                    name = _table_name(item)
                    if name:
                        acc.append(name)
                continue
            if isinstance(tok, Identifier):
                # 基表 (可能带别名："t a" 或 "t AS a")；取 real_name，**不再递归**，防止把别名当表。
                real = (tok.get_real_name() or "").strip("`")
                if real:
                    acc.append(real)
                continue
            name = _table_name(tok)
            if name:
                acc.append(name)
            continue
        # 非 FROM 上下文：递归子查询 / 标识符，找 nested SELECT
        if isinstance(tok, Parenthesis):
            _walk_from(tok, acc, in_from=False)
        elif isinstance(tok, (IdentifierList, Identifier)):
            _walk_from(tok, acc, in_from=in_from)


def _extract_cte_names(stmt: TokenList) -> List[str]:
    """扫描顶层 `WITH a AS (...), b AS (...)` 返回 CTE 名字列表。

    sqlparse 里 WITH 之后通常是一个 IdentifierList（多 CTE）或单个 Identifier（单 CTE），
    每个 Identifier 的 real_name 即为 CTE 名字。
    """
    names: List[str] = []
    seen_with = False
    for tok in stmt.tokens:
        if tok.ttype is not None and tok.ttype.parent is Keyword and tok.normalized.upper() == "WITH":
            seen_with = True
            continue
        # 兼容 sqlparse 把 WITH 标为 Token.Keyword.CTE
        if not seen_with:
            tv = getattr(tok, "ttype", None)
            tv_name = (getattr(tv, "tokens", None) or getattr(tok, "normalized", None) or "")
            if isinstance(tv_name, str) and tv_name.upper() == "WITH":
                seen_with = True
                continue
            # ttype 本身是 CTE
            if tok.ttype is not None and "CTE" in str(tok.ttype).upper():
                seen_with = True
                continue
        if not seen_with:
            continue
        if tok.is_whitespace:
            continue
        if isinstance(tok, IdentifierList):
            for item in tok.get_identifiers():
                n = (item.get_real_name() or "").strip("`")
                if n:
                    names.append(n)
            break
        if isinstance(tok, Identifier):
            n = (tok.get_real_name() or "").strip("`")
            if n:
                names.append(n)
            break
        # 遇到 SELECT 等关键字意味着 CTE 段结束
        if tok.ttype is Keyword or tok.ttype is DML:
            break
    return names


def _is_derived_table(ident: Identifier) -> bool:
    """Identifier 的首个非空 token 是 Parenthesis → 派生表（子查询）。"""
    for t in ident.tokens:
        if t.is_whitespace:
            continue
        return isinstance(t, Parenthesis)
    return False


def _table_name(tok) -> str:
    """从 token 中提取裸表名（去掉反引号、别名、库名前缀）。"""
    if isinstance(tok, IdentifierList):
        # 交给递归层处理
        return ""
    if isinstance(tok, Identifier):
        real = tok.get_real_name() or ""
        return real.strip("`")
    if tok.ttype is Punctuation:
        return ""
    # 其它裸 token，不处理
    return ""


__all__ = [
    "SqlSafetyError",
    "validate_select_sql",
    "inject_limit",
    "run_select",
]
