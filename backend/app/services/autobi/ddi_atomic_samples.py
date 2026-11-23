"""Resolve a maintained atomic question against this lab's own knowledge base."""

from sqlalchemy import select
from sqlglot import exp, parse
from sqlglot.errors import SqlglotError
from sqlglot.optimizer.scope import traverse_scope

from ...models.knowledge_access import SampleLibrary
from ...models.knowledge_base import KbSampleLibrary, KnowledgeBase
from .ddi_metrics import scoped_sql


def exact_sample(db, kb_id, question):
    title = question.strip().rstrip("？?。").rstrip()
    names = [title + suffix for suffix in ("", "？", "?", "。")]
    rows = db.execute(
        select(SampleLibrary.sql_content)
        .join(KbSampleLibrary, KbSampleLibrary.sample_id == SampleLibrary.id)
        .join(KnowledgeBase, KnowledgeBase.id == KbSampleLibrary.knowledge_base_id)
        .where(KnowledgeBase.id == kb_id, KnowledgeBase.space_id == SampleLibrary.space_id,
               KnowledgeBase.knowledge_access_id == SampleLibrary.knowledge_access_id,
               SampleLibrary.is_deleted.is_(False), SampleLibrary.sample_name.in_(names))
        .distinct().limit(2)
    ).scalars().all()
    if len(rows) > 1:
        raise ValueError("知识库中同一原子问题关联了多条不同的 SQL，请在样例库中确认。")
    return rows[0] if rows else None


_TABLES = {"sales_target_ai4bi", "v_ai4bi_ddi_sales", "data_range_config",
           "prod_master", "ddi_coverage", "teri_hierachy"}
_NODES = set("""
select with cte union intersect except from join table identifier tablealias alias column
star distinct subquery where having group order ordered limit offset window windowspec
literal null boolean paren add sub mul div mod neg eq neq gt gte lt lte and or not is
between in like ilike case if coalesce nullif sum count avg min max round abs greatest least
lag lead rank denserank rownumber firstvalue lastvalue cast datatype datatypeparam
dateadd datesub datetrunc timestamptrunc extract interval var currentdate currenttimestamp
""".split())
_TYPES = {"DATE", "TIMESTAMP", "TIMESTAMPTZ", "DECIMAL", "DOUBLE", "FLOAT", "INT",
          "BIGINT", "TEXT", "VARCHAR", "BOOLEAN"}


def sample_sql(sql, scope):
    try:
        statements = parse(sql, read="postgres")
        if len(statements) != 1 or not isinstance(statements[0], exp.Select):
            raise ValueError("原子样例需要一条 PostgreSQL SELECT 查询。")
        tree = statements[0]
        if any(n.key not in _NODES for n in tree.walk()) or any(
            n.this.value not in _TYPES for n in tree.find_all(exp.DataType)
        ):
            raise ValueError("原子样例包含不支持的查询操作，请检查样例 SQL。")
        tables = set()
        for block in traverse_scope(tree):
            for _, source in block.selected_sources.values():
                if not isinstance(source, exp.Table):
                    continue
                name = source.name.lower()
                if (not isinstance(source.this, exp.Identifier) or name not in _TABLES
                        or source.catalog or source.db not in ("", "public")):
                    raise ValueError("原子样例只能访问当前 DDI 数据源的业务表。")
                source.set("db", exp.to_identifier("public"))
                source.set("this", exp.to_identifier(name))
                tables.add(name)
        if not tables:
            raise ValueError("原子样例需要查询业务表。")
        if scope and scope.get("mode") != "all" and tables & {"ddi_coverage", "teri_hierachy"}:
            raise ValueError("当前用户的行级授权尚不覆盖该样例的明细表。")
        return scoped_sql(tree.sql(dialect="postgres", comments=False), scope)
    except SqlglotError as exc:
        raise ValueError("原子样例的 PostgreSQL 语法无效。") from exc
