"""
XLSX 表格智能问答 · 解析器

职责：
  1. 从 xlsx bytes 读入 → pandas DataFrame（一期只取第一个非空 Sheet）
  2. 列名规范化：中文/空格/关键字/冲突 → 安全的 snake_case；兜底 col_N
  3. 类型推断：BIGINT / DOUBLE / DATETIME / TINYINT / VARCHAR / TEXT
  4. 动态建 MySQL 表
  5. 批量 INSERT（分批）

设计：所有环节都是**可替换的小组件**（ColumnNormalizer / TypeInferrer / DynamicTableBuilder）
     未来要支持 csv / parquet / 多 sheet 合并，只需加同形状的入口函数。
"""
from __future__ import annotations

import io
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, List, Optional, Tuple

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------

@dataclass
class ParsedColumn:
    raw_header: str       # 原表头（可能中文）
    column_name: str      # 物理列名（snake_case 或 col_N）
    column_type: str      # BIGINT / DOUBLE / DATETIME / TINYINT / VARCHAR(512) / TEXT
    sample: List[Any] = field(default_factory=list)
    distinct: int = 0


@dataclass
class ParsedSheet:
    sheet_name: str
    total_rows: int
    total_columns: int
    columns: List[ParsedColumn]
    df: pd.DataFrame  # 列名已改为 column_name（物理列名）


@dataclass
class ParseOptions:
    max_rows: int = 100_000
    max_columns: int = 200
    sample_for_type_inference: int = 1000
    sample_values_per_column: int = 5
    # 物理列名长度上限（MySQL 标识符 64，预留前缀）
    column_name_max_len: int = 60


# ---------------------------------------------------------------------------
# 列名规范化
# ---------------------------------------------------------------------------

_SQL_RESERVED = {
    "order", "group", "select", "from", "where", "table", "index", "key",
    "primary", "references", "insert", "update", "delete", "drop", "alter",
    "create", "join", "inner", "outer", "left", "right", "on", "limit",
    "offset", "union", "values", "like", "not", "null", "is", "and", "or",
    "by", "as", "case", "when", "then", "else", "end", "having", "with",
}


class ColumnNormalizer:
    """把原始表头转为 MySQL 安全的列名。"""

    def __init__(self, max_len: int = 60) -> None:
        self.max_len = max_len

    def normalize(self, raw_headers: Iterable[Any]) -> List[str]:
        used: dict[str, int] = {}
        result: List[str] = []
        for idx, raw in enumerate(raw_headers):
            base = self._to_snake(raw)
            if not base:
                base = f"col_{idx + 1}"
            if base in _SQL_RESERVED:
                base = f"c_{base}"
            if len(base) > self.max_len:
                base = base[: self.max_len].rstrip("_") or f"col_{idx + 1}"

            # 冲突处理：base / base_2 / base_3 ...
            if base not in used:
                used[base] = 1
                result.append(base)
            else:
                used[base] += 1
                candidate = f"{base}_{used[base]}"
                while candidate in used:
                    used[base] += 1
                    candidate = f"{base}_{used[base]}"
                used[candidate] = 1
                result.append(candidate)
        return result

    @staticmethod
    def _to_snake(raw: Any) -> str:
        s = str(raw if raw is not None else "").strip()
        if not s:
            return ""
        # 全部小写；中文字符直接丢弃（作为物理列名用英文 + 兜底 col_N 更稳）
        # 中文头完全保留在 raw_header 里给 LLM prompt 使用
        s = s.lower()
        # 将非 [a-z0-9_] 统一换成 _
        s = re.sub(r"[^a-z0-9_]+", "_", s)
        s = re.sub(r"_+", "_", s).strip("_")
        # 首字符必须是字母或下划线
        if s and s[0].isdigit():
            s = f"c_{s}"
        return s


# ---------------------------------------------------------------------------
# 类型推断
# ---------------------------------------------------------------------------

class TypeInferrer:
    """统一类型策略：所有业务列一律按 TEXT 字符串入库。

    设计取舍：
      - 早期尝试过"数值 / 日期 / 布尔"自动推断，但 xlsx 里混合格式很常见
        （同一列既有 "1,234.56" 又有 "N/A"，或日期混着 "待定"），自动推断经常
        把列判错，导致大量值丢 NULL，或入库失败。
      - 字符串统一存储最稳——Excel 里"看见什么就是什么"。
      - 下游做聚合时，MySQL 会对数值字符串做隐式 CAST（`SUM('123.45')` 可行）；
        TEXT_TO_SQL 层的提示词会提醒模型必要时加 CAST。
    """

    def infer(self, series: pd.Series) -> Tuple[str, List[Any]]:
        clean = series.dropna()
        if clean.empty:
            return "TEXT", []
        samples = [str(v) for v in self._samples(clean, 5)]
        return "TEXT", samples

    @staticmethod
    def _samples(series: pd.Series, n: int) -> List[Any]:
        vals = series.drop_duplicates().head(n).tolist()
        return [_jsonable(v) for v in vals]


def _jsonable(v: Any) -> Any:
    """把 pandas / numpy 值转成 Python 原生，便于 JSON 存储。"""
    if v is None:
        return None
    if isinstance(v, (bool, int, float, str)):
        return v
    if isinstance(v, pd.Timestamp):
        return v.isoformat()
    try:
        import numpy as np  # 延迟导入
        if isinstance(v, np.generic):
            return v.item()
    except ImportError:  # pragma: no cover
        pass
    return str(v)


# ---------------------------------------------------------------------------
# 动态建表 / 批量插入
# ---------------------------------------------------------------------------

def build_data_table_name(module_id: int, doc_id: int, sheet_index: int = 0) -> str:
    return f"xlsx_qa_data_m{int(module_id)}_d{int(doc_id)}_s{int(sheet_index)}"


class DynamicTableBuilder:
    """创建 / 删除 动态数据表。使用原生 DDL（参数化不支持表名/列名）。

    所有传入的 column_name 必须已通过 ColumnNormalizer 校验（只包含 [a-z0-9_]），
    这里仍做二次正则白名单拦截，兜底防注入。
    """

    _COL_RE = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")
    _TBL_RE = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")

    def create(self, engine: Engine, table_name: str, columns: List[ParsedColumn]) -> None:
        if not self._TBL_RE.match(table_name):
            raise ValueError(f"非法表名：{table_name}")
        if engine.dialect.name == "postgresql":
            quote = engine.dialect.identifier_preparer.quote_identifier
            fields = ["_row_id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY", "_row_index INTEGER NOT NULL"]
            for col in columns:
                if not self._COL_RE.fullmatch(col.column_name):
                    raise ValueError(f"非法列名：{col.column_name}")
                kind = {"DOUBLE": "DOUBLE PRECISION", "DATETIME": "TIMESTAMP", "TINYINT": "SMALLINT"}.get(col.column_type, col.column_type)
                if not re.fullmatch(r"TEXT|BIGINT|INTEGER|DOUBLE PRECISION|TIMESTAMP|SMALLINT|DATE|VARCHAR\([0-9]+\)", kind):
                    raise ValueError(f"未知工作表字段类型：{kind}")
                fields.append(f"{quote(col.column_name)} {kind}")
            with engine.begin() as conn:
                conn.exec_driver_sql(f"CREATE TABLE IF NOT EXISTS {quote(table_name)} ({', '.join(fields)})")
                conn.exec_driver_sql(f"CREATE INDEX IF NOT EXISTS {quote(table_name + '_row_idx')} ON {quote(table_name)} (_row_index)")
            return
        col_defs: List[str] = [
            "`_row_id` INT NOT NULL AUTO_INCREMENT",
            "`_row_index` INT NOT NULL",
        ]
        for col in columns:
            if not self._COL_RE.match(col.column_name):
                raise ValueError(f"非法列名：{col.column_name}")
            col_defs.append(f"`{col.column_name}` {col.column_type} NULL")
        col_defs.append("PRIMARY KEY (`_row_id`)")
        col_defs.append("KEY `ix_row_index` (`_row_index`)")
        ddl = (
            f"CREATE TABLE IF NOT EXISTS `{table_name}` (\n  "
            + ",\n  ".join(col_defs)
            + "\n) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;"
        )
        with engine.begin() as conn:
            conn.exec_driver_sql(ddl)
        logger.info("xlsx_qa.parser.create_table %s cols=%s", table_name, len(columns))

    def drop(self, engine: Engine, table_name: str) -> None:
        if not self._TBL_RE.match(table_name):
            logger.warning("xlsx_qa.parser.drop skip illegal table=%s", table_name)
            return
        with engine.begin() as conn:
            conn.exec_driver_sql(f"DROP TABLE IF EXISTS {engine.dialect.identifier_preparer.quote_identifier(table_name)}")
        logger.info("xlsx_qa.parser.drop_table %s", table_name)


def insert_dataframe(
    engine: Engine,
    table_name: str,
    columns: List[ParsedColumn],
    df: pd.DataFrame,
    *,
    batch_size: int = 5000,
) -> int:
    """把 DataFrame 批量写入动态数据表。

    df 的列名必须已经是物理列名（column_name）。
    """
    if not DynamicTableBuilder._TBL_RE.match(table_name):
        raise ValueError(f"非法表名：{table_name}")
    if df.empty:
        return 0

    col_names = [c.column_name for c in columns]
    quote = engine.dialect.identifier_preparer.quote_identifier
    cols_sql = ", ".join(quote(c) for c in ["_row_index", *col_names])
    placeholders = ", ".join(["%s"] * (len(col_names) + 1))
    insert_sql = f"INSERT INTO {quote(table_name)} ({cols_sql}) VALUES ({placeholders})"

    written = 0
    # 预处理：把 NaT/NaN 转 None，Timestamp → str
    df_clean = df.where(df.notna(), None)

    rows_iter = df_clean.itertuples(index=False, name=None)
    batch: List[tuple] = []
    # 用 pymysql 游标更快；这里用 SQLAlchemy raw connection 通用处理
    raw_conn = engine.raw_connection()
    try:
        cursor = raw_conn.cursor()
        for row_idx, row in enumerate(rows_iter, start=1):
            safe_row = tuple(_coerce_value(v) for v in row)
            batch.append((row_idx, *safe_row))
            if len(batch) >= batch_size:
                cursor.executemany(insert_sql, batch)
                written += len(batch)
                batch.clear()
        if batch:
            cursor.executemany(insert_sql, batch)
            written += len(batch)
        raw_conn.commit()
    finally:
        raw_conn.close()
    logger.info("xlsx_qa.parser.insert %s rows=%s", table_name, written)
    return written


def _coerce_value(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, float) and (pd.isna(v)):
        return None
    if isinstance(v, pd.Timestamp):
        if pd.isna(v):
            return None
        return v.to_pydatetime()
    try:
        import numpy as np
        if isinstance(v, np.generic):
            return v.item()
    except ImportError:
        pass
    return v


# ---------------------------------------------------------------------------
# 顶层 parse_xlsx
# ---------------------------------------------------------------------------

def parse_xlsx(
    data: bytes,
    *,
    sheet_indices: Optional[List[int]] = None,
    options: ParseOptions | None = None,
) -> List[ParsedSheet]:
    """把 xlsx 字节流解析成 ParsedSheet 列表。

    若不指定 sheet_indices，则取所有非空 Sheet（最多 5 个）；
    若指定，则只解析对应索引的 Sheet（0-based，最多 5 个）。

    返回的每个 DataFrame 列名已改为物理列名（snake_case / col_N）。
    不负责建表 / 插入，那是 service 层的编排。
    """
    opt = options or ParseOptions()

    # 优先使用 calamine 引擎（更快），不可用时回退 openpyxl
    try:
        import python_calamine  # noqa: F401
        _xlsx_engine = "calamine"
    except ImportError:
        _xlsx_engine = "openpyxl"

    with io.BytesIO(data) as buf:
        xls = pd.ExcelFile(buf, engine=_xlsx_engine)
        sheet_names = xls.sheet_names or []
        # 确定要解析哪些 Sheet
        if sheet_indices is not None:
            # 指定的索引（0-based），去重 & 排序 & 最多 5 个
            indices = sorted(set(sheet_indices))[:5]
            target_names = [sheet_names[i] for i in indices if i < len(sheet_names)]
        else:
            # 默认：所有非空 Sheet，最多 5 个
            target_names = sheet_names[:5]

        parsed_sheets: List[ParsedSheet] = []
        for name in target_names:
            df = pd.read_excel(xls, sheet_name=name, dtype=object)
            if df is None or df.empty or len(df.columns) == 0:
                continue
            if len(parsed_sheets) >= 5:
                break
            picked_name = str(name)

            if len(df.columns) > opt.max_columns:
                raise ValueError(
                    f"Sheet「{picked_name}」列数超过上限 {opt.max_columns}：当前 {len(df.columns)}"
                )
            if len(df) > opt.max_rows:
                raise ValueError(
                    f"Sheet「{picked_name}」行数超过上限 {opt.max_rows}：当前 {len(df)}"
                )

            normalizer = ColumnNormalizer(max_len=opt.column_name_max_len)
            raw_headers = [str(h) if h is not None else "" for h in df.columns.tolist()]
            column_names = normalizer.normalize(raw_headers)

            df.columns = column_names

            inferrer = TypeInferrer()
            columns: List[ParsedColumn] = []
            sample_df = df.head(opt.sample_for_type_inference)
            for idx, col in enumerate(column_names):
                col_type, sample = inferrer.infer(sample_df[col])
                columns.append(
                    ParsedColumn(
                        raw_header=raw_headers[idx],
                        column_name=col,
                        column_type=col_type,
                        sample=sample[: opt.sample_values_per_column],
                        distinct=int(df[col].nunique(dropna=True)),
                    )
                )

            for meta in columns:
                df[meta.column_name] = df[meta.column_name].map(_to_text_preserve_null)

            parsed_sheets.append(
                ParsedSheet(
                    sheet_name=picked_name,
                    total_rows=int(len(df)),
                    total_columns=int(len(columns)),
                    columns=columns,
                    df=df,
                )
            )

    if not parsed_sheets:
        raise ValueError("XLSX 文件没有可用的 Sheet 或内容为空")

    return parsed_sheets


def _to_text_preserve_null(v: Any) -> Any:
    """把任意值转成文本，保留 None / NaN。

    - `pd.NA`、`float('nan')`、`pd.NaT` 全部返回 None
    - `pd.Timestamp` → ISO 字符串（保持 Excel 中原始日期样子）
    - `float` 整数值（如 1001.0）→ "1001"（Excel 默认把整数存成 float 会出现这种情况）
    - 其他对象 → str(v)；最后做 strip，避免行尾空白
    """
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(v, pd.Timestamp):
        return v.isoformat()
    if isinstance(v, float):
        if v.is_integer():
            return str(int(v))
        return repr(v)  # 保留 Python 默认最短精度表达，避免 "1.23456" 变 "1.234560"
    if isinstance(v, bool):
        return "true" if v else "false"
    s = str(v)
    return s.strip() if s else s
