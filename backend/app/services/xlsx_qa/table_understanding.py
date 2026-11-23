"""
XLSX 表格智能问答 · 表理解生成

上传成功后，用已经落库的样本数据（前 10 行 + 随机 90 行）让 LLM 输出一份
业务导向的 Markdown"表理解报告"，之后所有阶段（plan / text_to_sql / chart / summary）
都会把它拼进 schema prompt，以避免仅靠字段名猜含义造成的偏差。

只读取模块自己的动态表，不触碰其它库表。
"""
from __future__ import annotations

import logging
import random
from typing import Any, List, Optional, Sequence

from sqlalchemy import text
from sqlalchemy.engine import Engine

from . import llm_client, prompts

logger = logging.getLogger(__name__)


async def generate_understanding(
    *,
    engine: Engine,
    choice: llm_client.LlmChoice,
    data_table_name: str,
    file_name: str,
    sheet_name: Optional[str],
    total_rows: int,
    columns_json: Sequence[dict],
    head_size: int = 10,
    random_size: int = 90,
    head_rows: Optional[List[List[Any]]] = None,
    random_rows: Optional[List[List[Any]]] = None,
    language: Optional[str] = None,
) -> str:
    """采样 → 调 LLM → 返回 Markdown 文本（失败时抛异常，调用方自行兜底）。

    可通过外部传入 `head_rows` / `random_rows` 复用别处已经拿到的样本，避免重复
    `ORDER BY RAND()`。
    """
    if head_rows is None or random_rows is None:
        head_rows, random_rows = _sample_rows(
            engine, data_table_name, total_rows, head_size=head_size, random_size=random_size
        )
    column_list = [dict(c) for c in columns_json]

    schema_block = prompts.build_schema_prompt(
        file_name=file_name,
        sheet_name=sheet_name or "Sheet1",
        data_table_name=data_table_name,
        total_rows=total_rows,
        columns=column_list,
    )

    user_payload = _render_user(
        schema_block=schema_block,
        head_rows=head_rows,
        random_rows=random_rows,
        column_list=column_list,
        language=language,
    )

    logger.info(
        "xlsx_qa.understanding.generate table=%s head=%d random=%d columns=%d",
        data_table_name, len(head_rows), len(random_rows), len(column_list),
    )

    system = prompts._with_language_policy(prompts.UNDERSTAND_SYSTEM, language)
    md = await llm_client.chat_text(
        choice,
        system=system,
        user=user_payload,
        temperature=0.3,
        max_tokens=1800,
        timeout=120.0,
    )
    return (md or "").strip()


async def generate_suggested_questions(
    *,
    engine: Engine,
    choice: llm_client.LlmChoice,
    data_table_name: str,
    file_name: str,
    sheet_name: Optional[str],
    total_rows: int,
    columns_json: Sequence[dict],
    head_size: int = 10,
    random_size: int = 30,
    max_items: int = 5,
    head_rows: Optional[List[List[Any]]] = None,
    random_rows: Optional[List[List[Any]]] = None,
    language: Optional[str] = None,
) -> List[str]:
    """基于字段 + 小样本让 LLM 产出若干条业务口径的推荐问题。失败时抛异常。

    可通过外部传入 `head_rows` / `random_rows` 复用已有采样，避免重复采样开销。
    """
    if head_rows is None:
        head_rows, _ = _sample_rows(
            engine, data_table_name, total_rows, head_size=head_size, random_size=0
        )
    if random_rows is None:
        _, rand_rows = _sample_rows(
            engine, data_table_name, total_rows, head_size=0, random_size=random_size
        )
    else:
        # 外部给的随机样本可能偏大，这里再裁一下
        rand_rows = random_rows[: random_size]
    column_list = [dict(c) for c in columns_json]
    schema_block = prompts.build_schema_prompt(
        file_name=file_name,
        sheet_name=sheet_name or "Sheet1",
        data_table_name=data_table_name,
        total_rows=total_rows,
        columns=column_list,
    )
    header = [c.get("column_name") or "" for c in column_list]
    user = (
        f"{schema_block}\n\n"
        f"# Sample Data · First {len(head_rows)} Rows\n"
        f"{_rows_as_markdown_table(header, head_rows, limit=15)}\n\n"
        f"# Sample Data · Random {len(rand_rows)} Rows\n"
        f"{_rows_as_markdown_table(header, rand_rows, limit=40)}\n\n"
        "Output the JSON as instructed in the system prompt."
    )
    suggest_system = prompts._with_language_policy(prompts.SUGGEST_QUESTIONS_SYSTEM, language)
    obj = await llm_client.chat_json(
        choice,
        system=suggest_system,
        user=user,
        temperature=0.4,
        max_tokens=500,
        timeout=90.0,
    )
    raw = obj.get("questions") if isinstance(obj, dict) else None
    if not isinstance(raw, list):
        return []
    out: List[str] = []
    seen: set[str] = set()
    for q in raw:
        s = str(q or "").strip().rstrip("。").strip()
        if not s or s in seen:
            continue
        if len(s) > 40:
            s = s[:40]
        out.append(s)
        seen.add(s)
        if len(out) >= max_items:
            break
    return out


# ---------------------------------------------------------------------------
# 采样
# ---------------------------------------------------------------------------

def _sample_rows(
    engine: Engine,
    table: str,
    total_rows: int,
    *,
    head_size: int,
    random_size: int,
) -> tuple[List[List[Any]], List[List[Any]]]:
    """返回 (前 head_size 行, 随机 random_size 行)；都是 [[..values..]]。"""
    if total_rows <= 0:
        return [], []

    head = _query_rows(engine, f"SELECT * FROM `{table}` LIMIT {int(head_size)}")

    # 等步长采样（等价于 reservoir sampling），避免大表 ORDER BY RAND() 全表扫描
    rand_n = max(0, int(random_size))
    if rand_n <= 0:
        return head, []
    # 计算步长：每隔 step 行取一行，跳过 head 部分
    skip = max(head_size, 0)
    remaining = max(total_rows - skip, 0)
    if remaining <= 0:
        return head, []
    step = max(1, remaining // rand_n)
    rand_sql = (
        f"SELECT * FROM `{table}` WHERE `_row_index` > {skip} "
        f"AND MOD(`_row_index` - {skip + 1}, {step}) = 0 LIMIT {rand_n}"
    )
    try:
        rand = _query_rows(engine, rand_sql)
    except Exception as e:  # noqa: BLE001
        logger.warning("xlsx_qa.understanding sample fallback: %s", e)
        rand = _query_rows(
            engine,
            f"SELECT * FROM `{table}` LIMIT {rand_n} OFFSET {max(0, min(total_rows - rand_n, skip))}",
        )
    return head, rand


def _query_rows(engine: Engine, sql: str) -> List[List[Any]]:
    if engine.dialect.name == "postgresql":
        import sqlglot
        sql = sqlglot.transpile(sql, read="mysql", write="postgres")[0]
    with engine.connect() as conn:
        cursor = conn.execute(text(sql))
        return [list(r) for r in cursor.fetchall()]


# ---------------------------------------------------------------------------
# 提示渲染
# ---------------------------------------------------------------------------

def _render_user(
    *,
    schema_block: str,
    head_rows: List[List[Any]],
    random_rows: List[List[Any]],
    column_list: List[dict],
    language: Optional[str] = None,
) -> str:
    header = [c.get("column_name") or "" for c in column_list]
    lines: List[str] = []
    lines.append("# Table Schema")
    lines.append(schema_block)
    lines.append("")
    lines.append(f"# Sample Data · First {len(head_rows)} Rows (in order)")
    lines.append(_rows_as_markdown_table(header, head_rows, limit=20))
    lines.append("")
    lines.append(f"# Sample Data · Random {len(random_rows)} Rows (shuffled)")
    lines.append(_rows_as_markdown_table(header, random_rows, limit=120))
    lines.append("")
    lines.append(
        "Based on the table schema and the two sample batches above, "
        "output the business-understanding report as instructed in the system prompt."
    )
    return "\n".join(lines)


def _rows_as_markdown_table(headers: List[str], rows: List[List[Any]], *, limit: int) -> str:
    if not headers or not rows:
        return "（空）"
    rows = rows[:limit]
    head_line = "| " + " | ".join(headers) + " |"
    sep_line = "| " + " | ".join(["---"] * len(headers)) + " |"
    body: List[str] = []
    for r in rows:
        cells = []
        for v in r:
            cells.append(_fmt_cell(v))
        # 长度对不齐时做截断或补空
        if len(cells) < len(headers):
            cells += [""] * (len(headers) - len(cells))
        body.append("| " + " | ".join(cells[: len(headers)]) + " |")
    return "\n".join([head_line, sep_line, *body])


def _fmt_cell(v: Any) -> str:
    if v is None:
        return ""
    s = str(v)
    s = s.replace("|", "\\|").replace("\n", " ").replace("\r", " ")
    if len(s) > 40:
        s = s[:40] + "…"
    return s


def sample_rows(
    engine: Engine,
    table: str,
    total_rows: int,
    *,
    head_size: int = 10,
    random_size: int = 90,
) -> tuple[List[List[Any]], List[List[Any]]]:
    """对外暴露的采样入口：返回 (前 head_size 行, 随机 random_size 行)。"""
    return _sample_rows(engine, table, total_rows, head_size=head_size, random_size=random_size)


def append_knowledge_to_understanding(
    existing_md: str,
    knowledge_items: List[dict],
) -> str:
    """将新知识追加到表理解末尾，返回更新后的 MD 字符串。

    防重复：只追加 alias 尚未出现在 existing_md 中的条目。
    """
    if not knowledge_items:
        return existing_md

    existing_md = (existing_md or "").strip()

    # 过滤掉已存在的别名
    new_items: List[dict] = []
    for item in knowledge_items:
        alias = str(item.get("alias") or "").strip()
        if alias and alias.lower() not in existing_md.lower():
            new_items.append(item)

    if not new_items:
        return existing_md

    # 构建追加片段
    lines: List[str] = []
    lines.append("")
    lines.append("## 7. Domain Knowledge & Aliases (learned from user questions)")
    for item in new_items:
        alias = str(item.get("alias") or "").strip()
        maps_to = str(item.get("maps_to") or "").strip()
        column_hint = str(item.get("column_hint") or "").strip()
        desc = str(item.get("description") or "").strip()

        parts = [f"**{alias}**"]
        if maps_to:
            parts.append(f" {maps_to}")
        if desc:
            parts.append(f" — {desc}")
        if column_hint:
            parts.append(f" (maps to `{column_hint}` column)")
        else:
            parts.append(" (maps to relevant column)")

        lines.append(f"- {''.join(parts)}")

    return existing_md + "\n" + "\n".join(lines)


__all__ = ["generate_understanding", "generate_suggested_questions", "sample_rows", "append_knowledge_to_understanding"]
