"""Compile the documented DDI measures into a single read-only PostgreSQL statement."""

from datetime import date
from calendar import monthrange
from zoneinfo import ZoneInfo
from datetime import datetime
import json
import re
from sqlglot import exp

MONTHLY = "public.sales_target_ai4bi"
DAILY = "public.v_ai4bi_ddi_sales"
PRODUCT = "public.prod_master"
DIMS = {
    "month": "year_month",
    "brand": "brand_name_cn",
    "brand_code": "brand_code",
    "province": "province_name_cn",
    "city": "city_name_cn",
    "region": "region",
    "hco": "hco_name",
    "market": "market_type_latest",
    "terminal": "terminal_type_latest",
    "channel": "terminal_channel_latest",
    "platform": "terminal_platform_latest",
    "ta": "ta",
    "bu": "bu",
    "tier": "tier",
    "sales_rep": "ts_name",
    "manager": "sam_name",
    "director": "rd_name",
    "day": "sales_date",
}
MEASURES = {
    "sales_quantity": ("实际数量", "sales_qty"),
    "sales_amount": ("实际金额CNY", "sales_amt"),
    "sales_amount_usd": ("实际金额USD", "sales_amt_asp"),
    "target_quantity": ("预估数量", "target_qty"),
    "target_amount": ("预估金额CNY", "target_amt"),
    "target_amount_usd": ("预估金额USD", "target_amt_asp"),
    "quantity_attainment_rate": ("数量进度", "sales_qty/target_qty"),
    "amount_attainment_rate": ("金额进度CNY", "sales_amt/target_amt"),
    "amount_attainment_rate_usd": ("金额进度USD", "sales_amt_asp/target_amt_asp"),
}
SPECIAL = {
    "forecast_quantity": "数量预估进度",
    "forecast_amount": "金额预估进度CNY",
    "forecast_amount_usd": "金额预估进度USD",
    "mtd_actual": "MTD实际数量",
    "mtd_target": "当月预估数量",
    "mtd_time": "MTD时间进度",
    "mtd_rate": "MTD实际进度",
    "mtd_average": "MTD日均",
    "mtd_remaining": "待完成数量",
    "mtd_daily_remaining": "每日待完成数量",
}
OPERATIONS = (
    "total",
    "rank",
    "share",
    "concentration",
    "yoy",
    "mom",
    "compare",
    "member_growth",
)
DATE_CONFIG = "public.data_range_config"


def literal(value):
    return exp.Literal.string(str(value)).sql(dialect="postgres")


def quote(value):
    return '"' + value.replace('"', '""') + '"'


def choices(items, allowed, limit):
    if (
        not isinstance(items, list)
        or len(items) > limit
        or any(x not in allowed for x in items)
    ):
        raise ValueError("指标或维度不在业务口径中")
    return list(dict.fromkeys(items))


def month(value):
    text = str(value)
    if not re.fullmatch(r"(?:19|20)\d{2}(?:0[1-9]|1[0-2])", text):
        raise ValueError("月份需要采用 YYYYMM")
    return int(text)


def shift_month(ym, amount):
    y, m = divmod(ym, 100)
    y, m = divmod(y * 12 + m - 1 + amount, 12)
    return y * 100 + m + 1


def source_period(plan, source):
    start, end = plan.get("start"), plan.get("end")
    if not start and not end:
        selector = plan.get("period", "year")
        if selector == "latest":
            expr = f"(SELECT MAX(year_month) FROM {source})"
            return expr, expr
        if selector == "anchor":
            expr = f"(SELECT max_daily_yearmonth FROM {DATE_CONFIG} LIMIT 1)"
            return expr, expr
        year = datetime.now(ZoneInfo("Asia/Shanghai")).year
        return year * 100 + 1, year * 100 + 12
    start, end = month(start or end), month(end or start)
    if start > end:
        raise ValueError("开始月份晚于结束月份")
    return start, end


def predicate(filters, columns):
    conditions = []
    if not isinstance(filters, dict) or len(filters) > 12:
        raise ValueError("无效的筛选条件")
    for name, values in filters.items():
        if (
            name not in columns
            or not isinstance(values, list)
            or not 1 <= len(values) <= 100
        ):
            raise ValueError("所选口径不支持该筛选字段")
        conditions.append(
            columns[name] + " IN (" + ", ".join(literal(v) for v in values) + ")"
        )
    return conditions


def special(plan, metrics, dims):
    if any(m not in SPECIAL for m in metrics) or any(
        d not in {"brand", "brand_code"} for d in dims
    ):
        raise ValueError("预估进度与 MTD 按品牌计算，请按品牌查询")
    forecasts = any(m.startswith("forecast_") for m in metrics)
    if forecasts and any(m.startswith("mtd_") for m in metrics):
        raise ValueError("预估进度与 MTD 的统计月份不同，请分别查询")
    lo, hi = source_period(dict({"period": "anchor"}, **plan), DAILY)
    if forecasts:
        anchor = "(extract(year from reference_date)::int*100+extract(month from reference_date)::int)"
        lo = hi = anchor
    keys = {"brand": "b.brand_name_cn", "brand_code": "b.brand_code"}
    filters = predicate(plan.get("filters") or {}, keys)
    where = " WHERE " + " AND ".join(filters) if filters else ""
    formulas = {
        "mtd_actual": "d.qty",
        "mtd_target": "m.tq",
        "mtd_time": "a.elapsed/a.days",
        "mtd_rate": "d.qty/NULLIF(m.tq,0)",
        "mtd_average": "d.qty/NULLIF(a.elapsed,0)",
        "mtd_remaining": "CASE WHEN m.tq IS NOT NULL AND d.qty IS NOT NULL THEN GREATEST(m.tq-d.qty,0) END",
        "mtd_daily_remaining": "CASE WHEN m.tq IS NULL OR d.qty IS NULL THEN NULL WHEN a.days=a.elapsed AND d.qty>=m.tq THEN 0 ELSE GREATEST(m.tq-d.qty,0)/NULLIF(a.days-a.elapsed,0) END",
    }
    for m, actual, target in (
        ("forecast_quantity", "sq", "tq"),
        ("forecast_amount", "sa", "ta"),
        ("forecast_amount_usd", "su", "tu"),
    ):
        formulas[m] = (
            f"m.{actual}/NULLIF(c.coverage,0)/NULLIF(a.elapsed,0)*a.days/NULLIF(m.{target},0)"
        )
    selected = [keys[d] + " AS " + quote(d) for d in (dims or ["brand"])]
    selected += [formulas[m] + " AS " + quote(SPECIAL[m]) for m in metrics]
    return f"""WITH anchor AS (SELECT max_ddi_version AS reference_date FROM {DATE_CONFIG} LIMIT 1),
a AS (SELECT reference_date, EXTRACT(day FROM reference_date)::numeric AS elapsed,
 EXTRACT(day FROM date_trunc('month',reference_date)+interval '1 month - 1 day')::numeric AS days FROM anchor),
b AS (SELECT brand_code, MAX(brand_name_cn) AS brand_name_cn FROM {PRODUCT} GROUP BY brand_code),
p AS (SELECT prod_code_codi, MAX(brand_code) AS brand_code FROM {PRODUCT} GROUP BY prod_code_codi),
d AS (SELECT p.brand_code, SUM(s.sales_qty)::numeric AS qty FROM {DAILY} s JOIN p USING(prod_code_codi) CROSS JOIN a
WHERE s.year_month BETWEEN {lo} AND {hi} GROUP BY p.brand_code),
m AS (SELECT brand_code, SUM(sales_qty)::numeric sq,SUM(target_qty)::numeric tq,SUM(sales_amt) sa,
SUM(target_amt) ta,SUM(sales_amt_asp) su,SUM(target_amt_asp) tu FROM {MONTHLY} CROSS JOIN a
WHERE year_month BETWEEN {lo} AND {hi} GROUP BY brand_code),
c AS (SELECT brand_code, MAX(coverage) AS coverage FROM public.ddi_coverage GROUP BY brand_code)
SELECT {", ".join(selected)} FROM b CROSS JOIN a LEFT JOIN m USING(brand_code)
LEFT JOIN d USING(brand_code) LEFT JOIN c USING(brand_code){where} ORDER BY b.brand_code"""


def compile_sql(plan):
    metrics = choices(plan.get("metrics"), set(MEASURES) | set(SPECIAL), 16)
    dims = choices(plan.get("dimensions", []), DIMS, 6)
    ops = choices(plan.get("operations", ["total"]), OPERATIONS, 5) or ["total"]
    if not metrics:
        raise ValueError("请选择业务指标")
    if any(m in SPECIAL for m in metrics):
        return special(plan, metrics, dims)
    daily = plan.get("source") == "daily" or "day" in dims
    source = DAILY if daily else MONTHLY
    cols = {k: "s." + v for k, v in DIMS.items() if k != "day" or daily}
    if daily:
        cols = {
            k: cols[k]
            for k in ("month", "day", "market", "terminal", "channel", "platform")
        }
        cols.update(brand="p.brand_name_cn", brand_code="p.brand_code")
        source_sql = f"{source} s LEFT JOIN (SELECT prod_code_codi,MAX(brand_code) AS brand_code,MAX(brand_name_cn) AS brand_name_cn FROM {PRODUCT} GROUP BY prod_code_codi) p USING(prod_code_codi)"
    else:
        source_sql = source + " s"
    lo, hi = source_period(plan, source)
    comparisons = [op for op in ops if op in ("yoy", "mom", "compare", "member_growth")]

    def aggregate(start, end, offset=0, dimensions=None):
        grouped = dims if dimensions is None else dimensions
        cond = predicate(plan.get("filters") or {}, cols)
        cond.append(f"s.year_month BETWEEN {start} AND {end}")
        for field, sign in (("day_from", ">="), ("day_to", "<=")):
            if plan.get(field):
                if not daily:
                    raise ValueError("日过滤需要采用日明细")
                datevalue = date.fromisoformat(plan[field])
                if offset:
                    shifted = shift_month(
                        datevalue.year * 100 + datevalue.month, -offset
                    )
                    y, m = divmod(shifted, 100)
                    datevalue = date(y, m, min(datevalue.day, monthrange(y, m)[1]))
                cond.append("s.sales_date " + sign + " DATE " + literal(str(datevalue)))
        group = []
        for dim in grouped:
            if dim not in cols:
                raise ValueError("该数据表不含所选维度")
            expr = cols[dim]
            if dim == "month" and offset:
                expr = f"to_char(to_date(s.year_month::text,'YYYYMM')+interval '{offset} months','YYYYMM')::int"
            if dim == "day" and offset:
                expr = f"(s.sales_date + interval '{offset} months')::date"
            group.append(expr + " AS " + quote(dim))

        def summed(field, fill_empty=True):
            if daily:
                expr = {
                    "sales_qty": "s.sales_qty",
                    "sales_amt": "s.sales_qty*s.price_latest",
                    "sales_amt_asp": "s.sales_qty*s.asp_price",
                }.get(field)
                if not expr:
                    raise ValueError("预估数据来自月汇总表")
            else:
                expr = "s." + field
            result = "SUM(" + expr + ")"
            if (
                not daily
                and field.startswith("sales_")
                and any(d in dims for d in ("month", "market", "terminal"))
            ):
                result += " FILTER (WHERE s.sales_qty<>0)"
            if fill_empty and ("brand" in grouped or "brand_code" in grouped):
                result = "COALESCE(" + result + ",0)"
            return result

        measures = []
        for idx, metric in enumerate(metrics):
            parts = MEASURES[metric][1].split("/")
            expr = summed(parts[0], fill_empty=len(parts) == 1)
            if len(parts) > 1:
                expr = f"{expr}::numeric/NULLIF({summed(parts[1], fill_empty=False)},0)"
            measures.append(f"{expr} AS v{idx}")
        group_by = (
            " GROUP BY " + ",".join(str(i + 1) for i in range(len(grouped)))
            if grouped
            else ""
        )
        return (
            "SELECT "
            + ", ".join(group + measures)
            + " FROM "
            + source_sql
            + " WHERE "
            + " AND ".join(cond)
            + group_by
        )

    ctes = ["a AS (" + aggregate(lo, hi) + ")"]
    selected = ["a." + quote(d) for d in dims] + [
        f"a.v{i} AS " + quote(MEASURES[m][0]) for i, m in enumerate(metrics)
    ]
    joins = []
    for j, op in enumerate(comparisons):
        fixed = isinstance(lo, int) and isinstance(hi, int)
        width = (hi // 100 - lo // 100) * 12 + hi % 100 - lo % 100 + 1 if fixed else 1
        delta = 12 if op in ("yoy", "member_growth") else width
        if op == "mom" and "month" in dims:
            delta = 1
        if op == "compare":
            start, end = month(plan["compare_start"]), month(plan["compare_end"])
            if not fixed:
                raise ValueError("指定对照期时请给出报告期")
            delta = (lo // 100 - start // 100) * 12 + lo % 100 - start % 100
        elif fixed:
            start, end = shift_month(lo, -delta), shift_month(hi, -delta)
        else:

            def shifted(expr):
                return f"to_char(to_date(({expr})::text,'YYYYMM') - interval '{delta} months','YYYYMM')::int"

            start, end = shifted(lo), shifted(hi)
        key = f"b{j}"
        ctes.append(f"{key} AS (" + aggregate(start, end, delta) + ")")
        joins.append(
            "LEFT JOIN "
            + key
            + " ON "
            + (
                " AND ".join(
                    f"a.{quote(d)} IS NOT DISTINCT FROM {key}.{quote(d)}" for d in dims
                )
                or "TRUE"
            )
        )
        label = {
            "yoy": "同比",
            "mom": "环比",
            "compare": "对照期",
            "member_growth": "同比",
        }[op]
        for i, m in enumerate(metrics):
            title = MEASURES[m][0]
            selected.extend(
                [
                    f"{key}.v{i} AS " + quote(title + label + "基数"),
                    f"a.v{i}-{key}.v{i} AS " + quote(title + label + "变动量"),
                    f"(a.v{i}-{key}.v{i})::numeric/NULLIF({key}.v{i},0) AS "
                    + quote(title + label + "增速"),
                ]
            )
    limit = max(1, min(1000, int(plan.get("limit") or 10)))
    if "share" in ops:
        ctes.append("overall AS (" + aggregate(lo, hi, dimensions=[]) + ")")
        joins.append("CROSS JOIN overall")
        selected += [
            f"a.v{i}::numeric/NULLIF(overall.v{i},0) AS "
            + quote(MEASURES[m][0] + "占比")
            for i, m in enumerate(metrics)
        ]
    if "rank" in ops:
        selected.append(
            "DENSE_RANK() OVER(ORDER BY a.v0 DESC NULLS LAST) AS " + quote("排名")
        )
    order = (
        "a.v0 DESC NULLS LAST"
        if any(o in ops for o in ("rank", "concentration"))
        else ", ".join("a." + quote(d) for d in dims)
    )
    if "concentration" in ops:
        ctes.append(
            "ranked AS (SELECT v0,ROW_NUMBER() OVER (ORDER BY v0 DESC NULLS LAST) AS rn FROM a)"
        )
        query = f'SELECT SUM(v0) FILTER (WHERE rn<={limit})::numeric/NULLIF(SUM(v0),0) AS "TopN集中度" FROM ranked'
    else:
        query = "SELECT " + ", ".join(selected) + " FROM a " + " ".join(joins)
        if "member_growth" in ops:
            dim = plan.get("member_dimension", "brand")
            if dim not in dims or not plan.get("benchmark"):
                raise ValueError("比较成员平均增速需要维度和基准成员")
            title = MEASURES[metrics[0]][0] + "同比增速"
            ctes.append("changes AS (" + query + ")")
            ctes.append(
                "averages AS (SELECT "
                + quote(dim)
                + ", AVG("
                + quote(title)
                + ") AS growth FROM changes GROUP BY 1)"
            )
            query = (
                "SELECT "
                + quote(dim)
                + ', growth AS "平均增速", growth-(SELECT growth FROM averages WHERE '
                + quote(dim)
                + "="
                + literal(plan["benchmark"])
                + ') AS "与基准增速差" FROM averages ORDER BY 1'
            )
        elif order:
            query += " ORDER BY " + order
        if "rank" in ops:
            query += f" LIMIT {limit}"
    return "WITH " + ",\n".join(ctes) + "\n" + query


def scoped_sql(sql, scope):
    """Constrain both current and comparison facts before aggregation."""
    from sqlglot import exp, parse_one

    if not scope or scope.get("mode") == "all":
        return sql
    if (
        scope.get("mode") != "restricted"
        or not scope.get("organizations")
        or not scope.get("regions")
    ):
        raise ValueError("此账号尚未获得业务数据范围授权")

    def allowed(values):
        if not isinstance(values, list) or len(values) > 250:
            raise ValueError("无效的账号授权范围")
        return ",".join(literal(v) for v in values)

    orgs, regions = allowed(scope["organizations"]), allowed(scope["regions"])
    condition = f"(auth.bu IN ({orgs}) OR auth.hco_code IN ({orgs})) AND auth.region IN ({regions})"
    tree = parse_one(sql, read="postgres")
    for table in list(tree.find_all(exp.Table)):
        if table.db != "public":
            continue
        if table.name == "sales_target_ai4bi":
            select_sql = (
                f"SELECT auth.* FROM public.sales_target_ai4bi auth WHERE {condition}"
            )
        elif table.name == "v_ai4bi_ddi_sales":
            select_sql = f"SELECT d.* FROM public.v_ai4bi_ddi_sales d WHERE EXISTS (SELECT 1 FROM public.sales_target_ai4bi auth WHERE {condition} AND auth.hco_code=d.affiliate_hco_code)"
        else:
            continue
        table.replace(
            parse_one(select_sql, read="postgres").subquery(table.alias_or_name)
        )
    return tree.sql(dialect="postgres")


def normalize_plan(plan, question):
    """Canonicalize explicit natural-language dates and limits before applying the SQL allowlist."""
    plan = dict(plan)
    chinese = "零一二三四五六七八九"

    def positive_number(raw):
        if raw.isdigit():
            return int(raw)
        if raw == "两":
            return 2
        if "十" in raw:
            a, b = raw.split("十", 1)
            return (chinese.index(a) if a else 1) * 10 + (chinese.index(b) if b else 0)
        return chinese.index(raw)

    top = re.search(
        r"(?:top\s*|前\s*)([1-9]\d{0,2}|[一二两三四五六七八九十]{1,3})", question, re.I
    )
    if top:
        plan["limit"] = positive_number(top.group(1))
    date_range = re.search(
        r"(20\d{2})年(\d{1,2})月(\d{1,2})日?\s*(?:到|至|[-~～])\s*(?:(20\d{2})年)?(?:(\d{1,2})月)?(\d{1,2})日",
        question,
    )
    filters = dict(plan.get("filters") or {})
    if date_range:
        y, m, d, y2, m2, d2 = date_range.groups()
        a = date(int(y), int(m), int(d))
        z = date(int(y2 or y), int(m2 or m), int(d2))
        plan.update(
            day_from=a.isoformat(),
            day_to=z.isoformat(),
            start=a.year * 100 + a.month,
            end=z.year * 100 + z.month,
            source="daily",
        )
        for key in (
            "day",
            "sales_date",
            "day_from",
            "day_to",
            "year_month",
            "month",
            "date",
            "date_range",
        ):
            filters.pop(key, None)
    for key in ("country", "region", "province", "scope", "national"):
        if filters.get(key) in (["全国"], ["全国合计"], ["中国"]):
            filters.pop(key, None)
    plan["filters"] = filters
    if ("每日待完成" in question or "日均待完成" in question) and "按品牌" in question:
        if set(plan.get("metrics") or []) <= {"mtd_daily_remaining", "mtd_remaining"}:
            plan.update(metrics=["mtd_daily_remaining"], dimensions=["brand"])
    if (
        "按品牌" in question
        and "平均" in question
        and "增速" in question
        and "同比" in question
    ):
        baseline = re.search(
            r"(?:与|和|相对)\s*([^，。、的\s]{1,22})(?:的平均增速|相比)", question
        )
        if baseline:
            plan.update(
                operations=["member_growth"],
                dimensions=["brand", "month"],
                member_dimension="brand",
                benchmark=baseline.group(1),
            )
            if plan.get("metrics") and (
                "人民币" in question or "金额" in question and "美元" not in question
            ):
                plan["metrics"] = ["sales_amount"]
            filters.pop("brand", None)
    return plan


def plan_instructions():
    return (
        "你是吉利德 DDI 的 PostgreSQL 查询规划器。只输出一个 JSON 对象。根据用户要求选择一个或多个指标。"
        "指标 ID 与名称："
        + json.dumps(
            {**{k: v[0] for k, v in MEASURES.items()}, **SPECIAL}, ensure_ascii=False
        )
        + "。字段为 metrics 数组，dimensions 数组（可选 "
        + ",".join(DIMS)
        + "），operations 数组（"
        + ",".join(OPERATIONS)
        + "），"
        "start、end 为 YYYYMM 整数；最近完整数据月若未给具体月份用 period=latest，配置中的统计月或当月MTD用 period=anchor。"
        "明确的 YTD/QTD 转成起止月份。默认按今年、新查询未指定币种用人民币。filters 为维度键到精确字符串数组的映射。"
        "source 为 monthly 或 daily。通常用 monthly，日明细或按天才用 daily。日明细金额按对应价格。历史 MTD 给指定月份，"
        "forecast_* 是按品牌的月末推算，实际进度用 attainment_rate。当月预估和MTD实际进度属于MTD指标。"
        "日区间用 day_from/day_to（YYYY-MM-DD）。指定的两期比较用 compare_start、compare_end。"
        "rank 需要 limit 和分组，share 与 concentration 的分母保留全部成员，不把排名对象放进 filters。"
        "member_growth 要给 dimensions=[维度,month]、member_dimension 和 benchmark。同比环比可以一起请求。"
        "不得创造字段。例：人民币销售金额指定日区间：metrics=[sales_amount]、source=daily、day_from/day_to、filters={}。全国不是筛选。"
        "Top 3 的 limit=3，前五的 limit=5；每日待完成指标为 mtd_daily_remaining，不含 day 维度。"
        "同维度成员增速使用基础指标（例如 sales_amount），不要把 growth 当成指标。"
        "增速未指明比较期间且不能从上下文确定时返回 clarification 字符串。"
        "没有匹配的口径时返回 clarification，禁止猜测数据。北京时间 "
        + str(datetime.now(ZoneInfo("Asia/Shanghai")).date())
    )
