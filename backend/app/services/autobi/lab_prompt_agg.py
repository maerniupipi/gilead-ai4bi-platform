"""与前端 autobiLabAggregators / autobiLabChartSpec 对齐的纯函数（实验室网关流水线）。"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Set, Tuple


def build_knowledge_words_for_prompt(results: Optional[List[Dict[str, Any]]]) -> str:
    lines: List[str] = []
    for r in results or []:
        term = (r.get("content") or (r.get("metadata") or {}).get("data_detail") or "").strip()
        if not term:
            continue
        m = r.get("metadata") or {}
        explain = m.get("quote_extend") or m.get("data_detail") or ""
        lines.append(f"「{term}」→ {explain or '（无扩展说明）'}")
    return "\n".join(lines)


def build_knowledge_knowledge_map_object(results: Optional[List[Dict[str, Any]]]) -> Dict[str, str]:
    o: Dict[str, str] = {}
    for r in results or []:
        term = (r.get("content") or (r.get("metadata") or {}).get("data_detail") or "").strip()
        if not term:
            continue
        m = r.get("metadata") or {}
        explain = m.get("quote_extend") or m.get("data_detail") or ""
        o[term] = explain or term
    return o


def build_long_es_query_with_annotations(original_query: str, knowledge_map: Dict[str, str]) -> str:
    entries = list((knowledge_map or {}).items())
    if not entries:
        return original_query
    part = "、".join(f"【{k}】代表【{v}】" for k, v in entries)
    return f"{original_query} 其中，{part}"


def format_recall_table_dot_field(
    field_table: Optional[str],
    field_code: Optional[str],
    content_fallback: str = "",
) -> str:
    """
    召回写入自然语言 / nl2sql 参考：底层存「表&&字段」，展示为「表.字段」。
    """
    fc = (field_code or "").strip()
    if "&&" in fc:
        t, _, c = fc.partition("&&")
        t, c = t.strip(), c.strip()
        if t and c:
            return f"{t}.{c}"
    ft = (field_table or "").strip()
    if ft and fc and "&&" not in fc:
        return f"{ft}.{fc}"
    return fc or (content_fallback or "").strip() or ft or "?"


def _fmt_table_meta(results: List[Dict[str, Any]]) -> str:
    lines = []
    for r in results:
        m = r.get("metadata") or {}
        ref = format_recall_table_dot_field(
            m.get("field_table"),
            m.get("field_code"),
            str(r.get("content") or ""),
        )
        lines.append(
            f"- {ref}：{m.get('field_value') or r.get('content')}"
        )
    return "\n".join(lines)


def _fmt_generic_retriever(results: List[Dict[str, Any]], label: str) -> str:
    lines = []
    for r in results:
        m = r.get("metadata") or {}
        ref = format_recall_table_dot_field(
            m.get("field_table"),
            m.get("field_code"),
            "",
        )
        lines.append(
            f"- [{label}] {r.get('content')} | {ref}"
        )
    return "\n".join(lines)


def _format_step_result_item(result: Any, index: int) -> str:
    if not isinstance(result, dict):
        return f"{index + 1}. {result}"
    metadata = result.get("metadata") or {}
    parts: List[str] = []
    content = result.get("content")
    if content is None:
        content = metadata.get("field_value") or metadata.get("data_detail")
    if content is not None and str(content).strip():
        parts.append(f"内容：{str(content).strip()}")
    ref = format_recall_table_dot_field(
        metadata.get("field_table"), metadata.get("field_code"), ""
    )
    if ref != "?":
        parts.append(f"字段：{ref}")
    if metadata.get("query"):
        parts.append(f"问题：{metadata['query']}")
    if metadata.get("answer"):
        parts.append(f"SQL：{metadata['answer']}")
    if result.get("score") is not None:
        parts.append(f"得分：{result['score']}")
    fallback = json.dumps(result, ensure_ascii=False)
    return f"{index + 1}. {'；'.join(parts) or fallback}"


def build_step_response_nlp(response: Any, title: str = "") -> str:
    """将任一步骤返回转换为适合直接放进 Prompt 的自然语言文本。"""
    if response is None:
        return f"{title + '：' if title else ''}无返回结果"
    if not isinstance(response, dict):
        return str(response)
    if response.get("skipped"):
        return f"{title + '：' if title else ''}已跳过，原因：{response.get('reason') or '未说明'}"

    lines: List[str] = []
    if title:
        lines.append(f"【{title}】")
    results = response.get("results")
    if isinstance(results, list):
        lines.append(f"共召回 {response.get('total', len(results))} 条结果：")
        lines.extend(_format_step_result_item(item, i) for i, item in enumerate(results))
    entities = response.get("entities")
    if isinstance(entities, list) and entities:
        lines.append("识别实体：" + "、".join(str(item) for item in entities))
    if response.get("narrative"):
        lines.append(f"说明：{response['narrative']}")
    if response.get("rewritten_query"):
        lines.append(f"改写问题：{response['rewritten_query']}")
    if response.get("sql"):
        lines.append(f"SQL：{response['sql']}")
    if response.get("content") and not isinstance(results, list):
        lines.append(f"内容：{response['content']}")
    rows = response.get("rows")
    if isinstance(rows, list):
        lines.append(f"查询结果：共 {response.get('row_count', len(rows))} 行")
        lines.append(
            json.dumps(
                {"columns": response.get("columns") or [], "rows": rows},
                ensure_ascii=False,
                indent=2,
            )
        )
    if response.get("chart_spec"):
        lines.append(
            "图表配置："
            + json.dumps(response["chart_spec"], ensure_ascii=False, indent=2)
        )
    minimum = 1 if title else 0
    if len(lines) > minimum:
        return "\n".join(lines)
    return json.dumps(response, ensure_ascii=False, indent=2)


def build_step_feature_values(
    *, step_id: int, api_key: str, title: str, response: Any
) -> Dict[str, str]:
    """
    生成每步的运行时 features。

    无步骤号键表示最近一次同 api_key 的结果；带步骤号键可区分重复 api_key。
    """
    safe_response = to_json_safe(response)
    result = json.dumps(safe_response if safe_response is not None else {}, ensure_ascii=False, indent=2)
    nlp = build_step_response_nlp(safe_response, title or api_key)
    step_prefix = f"step_{step_id}_{api_key}"
    return {
        f"{api_key}_result": result,
        f"{api_key}_nlp": nlp,
        f"{step_prefix}_result": result,
        f"{step_prefix}_nlp": nlp,
    }


def _fmt_sql_template(results: List[Dict[str, Any]]) -> str:
    lines = []
    for r in results:
        m = r.get("metadata") or {}
        q = m.get("query") or r.get("content")
        a = m.get("answer") or ""
        lines.append(f"- 问：{q}\n  SQL：{a}")
    return "\n".join(lines)


def collect_field_tables_from_meta_steps(by_step: Dict[int, Dict[str, Any]]) -> List[str]:
    """第 6/7 步结果中去重 field_table，供表值召回按表并行。"""
    seen: Set[str] = set()
    out: List[str] = []
    for sid in (6, 7):
        res = (by_step.get(sid) or {}).get("response") or {}
        for r in res.get("results") or []:
            ft = ((r.get("metadata") or {}).get("field_table") or "").strip()
            if ft and ft not in seen:
                seen.add(ft)
                out.append(ft)
    return out


def collect_field_codes_for_multi_column(by_step: Dict[int, Dict[str, Any]]) -> List[str]:
    """第 6/7 步结果中去重 field_code（如 table&&col），供多列同值 multi-global 逐路召回。"""
    seen: Set[str] = set()
    out: List[str] = []
    for sid in (6, 7):
        res = (by_step.get(sid) or {}).get("response") or {}
        for r in res.get("results") or []:
            fc = ((r.get("metadata") or {}).get("field_code") or "").strip()
            if fc and fc not in seen:
                seen.add(fc)
                out.append(fc)
    return out


def _recall_field_parts(metadata: Dict[str, Any]) -> Tuple[str, str]:
    """统一表&&字段、表.字段和 field_table + 字段裸名，保留原大小写。"""
    table = str(metadata.get("field_table") or "").strip()
    code = str(metadata.get("field_code") or "").strip()
    if "&&" in code:
        table, field = code.split("&&", 1)
    elif table and code.startswith(table + "."):
        field = code[len(table) + 1:]
    elif "." in code:
        table, field = code.rsplit(".", 1)
    else:
        field = code
    return table.strip(), field.strip()


def collect_qs_recall_values(
    by_step: Dict[int, Dict[str, Any]],
    *,
    multi_column_enabled: Optional[bool] = None,
) -> Dict[str, Dict[str, List[str]]]:
    """多列模式只取第 12 步的双路并集；普通模式合并其余值召回节点。"""
    if multi_column_enabled is None:
        s12 = (by_step.get(12) or {}).get("response") or {}
        multi_column_enabled = bool(s12) and not s12.get("skipped")
    source_steps = (12,) if multi_column_enabled else (1, 7, 9, 11)
    grouped: Dict[str, Dict[str, List[str]]] = {}
    seen: Set[Tuple[str, str, str]] = set()
    for sid in source_steps:
        response = (by_step.get(sid) or {}).get("response") or {}
        if response.get("skipped") or response.get("error"):
            continue
        for result in response.get("results") or []:
            if not isinstance(result, dict):
                continue
            metadata = result.get("metadata") or {}
            if not isinstance(metadata, dict):
                continue
            table, field = _recall_field_parts(metadata)
            if not table or not field:
                continue
            raw_value = metadata.get("field_value")
            if raw_value is None:
                raw_value = result.get("content")
            if not isinstance(raw_value, (str, int, float, bool)):
                continue
            value = str(raw_value).strip()
            key = (table, field, value)
            if not value or key in seen:
                continue
            seen.add(key)
            grouped.setdefault(table, {}).setdefault(field, []).append(value)
    return grouped


def build_qs_recall(
    by_step: Dict[int, Dict[str, Any]],
    field_descriptions: Optional[List[Dict[str, Any]]] = None,
    *,
    multi_column_enabled: Optional[bool] = None,
) -> str:
    """qs_recall：按表输出字段候选值；知识库别名优先，第 6 步说明兜底。"""
    values = collect_qs_recall_values(by_step, multi_column_enabled=multi_column_enabled)
    if not values:
        return "（暂无候选值召回结果）"

    table_aliases: Dict[str, str] = {}
    field_aliases: Dict[Tuple[str, str], str] = {}
    s6 = (by_step.get(6) or {}).get("response") or {}
    if not s6.get("skipped") and not s6.get("error"):
        for result in s6.get("results") or []:
            if not isinstance(result, dict):
                continue
            metadata = result.get("metadata") or {}
            if not isinstance(metadata, dict):
                continue
            table, field = _recall_field_parts(metadata)
            detail = metadata.get("field_value") or result.get("content") or ""
            if not table or not field or not isinstance(detail, str) or "&&" not in detail:
                continue
            table_alias, field_alias = detail.split("&&", 1)
            if table_alias.strip():
                table_aliases.setdefault(table, table_alias.strip())
            if field_alias.strip():
                field_aliases.setdefault((table, field), field_alias.strip())

    for description in field_descriptions or []:
        table = str(description.get("table_name") or "").strip()
        field = str(description.get("field_name") or "").strip()
        table_alias = str(description.get("table_alias") or "").strip()
        field_alias = str(description.get("field_alias") or "").strip()
        if table_alias:
            table_aliases[table] = table_alias
        if field_alias:
            field_aliases[(table, field)] = field_alias

    parts: List[str] = []
    for table, fields in values.items():
        table_alias = table_aliases.get(table)
        table_note = f"{{{table_alias}}}" if table_alias else ""
        lines = [f'表名："{table}"{table_note}', "字段："]
        for field, candidates in fields.items():
            field_alias = field_aliases.get((table, field))
            field_note = f"{{{field_alias}}}" if field_alias else ""
            lines.append(
                f'候选值：字段"{table}.{field}"{field_note}在数据表中有如下值 {candidates!r}'
            )
        parts.append("\n".join(lines))
    return "\n\n".join(parts)


def build_table_field_prompt_data(by_step: Dict[int, Dict[str, Any]]) -> str:
    """nl2sql 的 table_field_prompt_data：仅 ⑥⑦⑨ + ⑪ 或 ⑫，不含 SQL 样例（样例走 icl_example_prompt_data）。"""
    parts: List[str] = []
    s6 = (by_step.get(6) or {}).get("response")
    s7 = (by_step.get(7) or {}).get("response")
    s9 = (by_step.get(9) or {}).get("response")
    s11 = (by_step.get(11) or {}).get("response") or {}
    s12 = (by_step.get(12) or {}).get("response") or {}
    # 多列同值生效时其结果覆盖第 7 步（同 query 的全域值召回），prompt 不再重复渲染 s7
    multi_active = bool(s12 and not s12.get("skipped") and (s12.get("results") or []))
    if s6 and (s6.get("results") or []):
        parts.append("【表字段召回 table-meta】\n" + _fmt_table_meta(s6["results"]))
    if s7 and (s7.get("results") or []) and not multi_active:
        parts.append("【表值(对应字段) global-value-meta】\n" + _fmt_generic_retriever(s7["results"], "值"))
    if s9 and (s9.get("results") or []):
        parts.append("【ES 表值（双次检索合并）】\n" + _fmt_generic_retriever(s9["results"], "ES"))
    if s12 and not s12.get("skipped") and (s12.get("results") or []):
        parts.append("【多列同值召回 multi-global-value-meta】\n" + _fmt_generic_retriever(s12["results"], "值"))
    elif s11 and not s11.get("skipped") and (s11.get("results") or []):
        parts.append("【表值召回 table-value】\n" + _fmt_generic_retriever(s11["results"], "值"))
    if parts:
        parts.append('【实体与字段核对】优先使用实际召回中精确匹配的字段和值。人名与业务/产品编码可能共同组成 area_name 完整值，应保留完整名称和编码；“下面/下属”等关系词不能使已匹配实体失效。产品名称按其命中的产品层级字段筛选，不得擅自改成 BU 维度，也不得补造未召回的字段值。')
    return "\n\n".join(parts) if parts else "（暂无召回结果）"


def build_icl_example_prompt_data(by_step: Dict[int, Dict[str, Any]]) -> str:
    s8 = (by_step.get(8) or {}).get("response")
    if not s8 or not (s8.get("results") or []):
        return ""
    return _fmt_sql_template(s8["results"])


def parse_ner_entities_from_llm(text: str) -> List[str]:
    """解析 NER 模型输出的 JSON，取 ner 字符串数组。"""
    if not text or not str(text).strip():
        return []
    t = str(text).strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", t, re.I)
    if m:
        t = m.group(1).strip()
    brace = re.search(r"\{[\s\S]*\}", t)
    if not brace:
        return []
    try:
        obj = json.loads(brace.group(0))
    except json.JSONDecodeError:
        return []
    ner = obj.get("ner")
    if isinstance(ner, list):
        return [str(x).strip() for x in ner if str(x).strip()]
    return []


def replace_template_vars(template: str, vars_map: Dict[str, Any]) -> str:
    if not template:
        return ""
    s = template
    for k, v in vars_map.items():
        s = re.sub(r"\{\{\s*" + re.escape(k) + r"\s*\}\}", "" if v is None else str(v), s)
    return s


def strip_lab_template_noise(s: str) -> str:
    if not s:
        return ""
    s = re.sub(r"\{%\s*raw\s*%\}", "", s, flags=re.I)
    s = re.sub(r"\{%\s*endraw\s*%\}", "", s, flags=re.I)
    lines = [ln for ln in s.split("\n") if not re.match(r"^\s*\{%", ln)]
    return "\n".join(lines)


def extract_sql_from_model_text(text: str) -> str:
    if not text:
        return ""
    t = text.strip()
    m = re.search(r"```(?:sql)?\s*([\s\S]*?)```", t, re.I)
    if m:
        return m.group(1).strip()
    return t


def normalize_rewritten_query(raw: str, original_query: str) -> str:
    x = (raw or "").strip()
    if not x or re.match(r"^none$", x, re.I):
        return original_query
    return x


def format_sql_execute_result_for_summary(res: Any) -> str:
    if res is None:
        return "（无执行结果）"
    if isinstance(res, dict) and res.get("skipped"):
        return str(res.get("reason") or "（跳过 SQL 执行）")
    if isinstance(res, dict):
        columns = res.get("columns") or []
        rows = res.get("rows") or []
        row_count = res.get("row_count", len(rows))
        try:
            full = {"columns": columns, "rows": rows, "row_count": row_count}
            text = json.dumps(full, ensure_ascii=False, indent=2)
            # The stored/exported result remains complete. Only the model's input
            # is sampled, with an explicit scope and the original total row count.
            max_bytes = 8192
            if len(rows) <= 50 and len(text.encode("utf-8")) <= max_bytes:
                return text
            compact = {"columns": columns, "rows": [], "row_count": row_count,
                       "included_rows": 0, "truncated": True,
                       "summary_scope": "仅解释所提供的样本，不得把样本统计视为全量统计。完整结果保留用于表格和文件导出。"}
            if len(json.dumps(compact, ensure_ascii=False).encode("utf-8")) > max_bytes:
                compact["columns"] = []
                compact["column_count"] = len(columns)
            for row in rows[:50]:
                candidate = {**compact, "rows": compact["rows"] + [row],
                             "included_rows": len(compact["rows"]) + 1}
                if len(json.dumps(candidate, ensure_ascii=False).encode("utf-8")) > max_bytes:
                    break
                compact = candidate
            return json.dumps(compact, ensure_ascii=False)
        except Exception:
            return "（执行结果无法序列化，未提供给总结模型；完整结果请查看表格。）"
    return str(res)


def build_bi_summary_user_message(
    template: str, *, original_query: str, execute_sql: str, sql_data_text: str
) -> str:
    sql = execute_sql or "无"
    data = sql_data_text if sql_data_text is not None else "（占位）10000元"
    head = template or ""
    head = re.sub(r"\{\{\s*rewrite_query\s*\}\}", original_query, head)
    head = re.sub(r"\{\{[\s\S]*?\}\}", "", head)
    head = "\n".join(ln for ln in head.split("\n") if not re.match(r"^\s*\{%", ln))
    body = (
        f"\n\n----------\n问题（用户原始）：\n{original_query}\n\n查询的 SQL：\n{sql}\n\n"
        f"SQL 执行结果：\n{data}\n\n请严格依据上述参考信息作答。"
        "业务金额、销量、目标、达成率属于查询结果，须忠实使用原始数值，不可替换为星号、掩码、x 或虚构数字。"
        "文字中的指标数值展示两位小数；年份、月份、工号和编码保持原样。"
        "NULL 表示缺失，不等于 0；无查询数据时明确说明无数据，不编造结论。"
    )
    return (head.strip() + body).strip()


def parse_chart_spec_from_llm(text: str) -> Optional[Dict[str, Any]]:
    if not text or not str(text).strip():
        return None
    s = str(text).strip()
    # Models may quote SQL/Jinja/mermaid before their final JSON answer. Never
    # treat the first arbitrary code fence as the chart or silently lose it.
    candidates = re.findall(r"```(?:json)?[ \t]*\n([\s\S]*?)```", s, re.I)
    candidates.append(s)
    decoder = json.JSONDecoder()
    for candidate in reversed(candidates):
        for start in reversed([m.start() for m in re.finditer(r"\{", candidate)]):
            try:
                obj, _ = decoder.raw_decode(candidate[start:])
            except ValueError:
                continue
            if isinstance(obj, dict) and ("type" in obj or "primary" in obj or "error" in obj):
                return _normalize_chart_spec(obj)
    return None


def _normalize_chart_spec(o: Any) -> Optional[Dict[str, Any]]:
    if not o or not isinstance(o, dict):
        return None
    xaxis = o.get("xaxis")
    if isinstance(xaxis, str):
        xaxis = [xaxis] if xaxis else []
    if not isinstance(xaxis, list):
        xaxis = []
    yaxis = o.get("yaxis")
    if isinstance(yaxis, str):
        yaxis = [yaxis] if yaxis else []
    if not isinstance(yaxis, list):
        yaxis = []
    raw_type = str(o.get("type") or o.get("primary") or "D").upper()
    letter = re.search(r"[ABCD]", raw_type)
    typ = letter.group(0) if letter else "D"
    return {
        "type": typ,
        "xaxis": xaxis,
        "yaxis": yaxis,
        "title": str(o["title"]) if o.get("title") is not None else "",
        "error": str(o["error"]) if o.get("error") is not None else None,
        "detail": str(o["detail"]) if o.get("detail") is not None else None,
    }


def to_json_safe(obj: Any) -> Any:
    if obj is None:
        return None
    if hasattr(obj, "model_dump"):
        return to_json_safe(obj.model_dump())
    if isinstance(obj, dict):
        return {k: to_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [to_json_safe(v) for v in obj]
    if isinstance(obj, (str, int, float, bool)):
        return obj
    return str(obj)
