"""Five-field Cron scheduling with IANA time zones and explicit DST handling."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def _field(value, lo, hi):
    values = set()
    for item in value.split(","):
        base, separator, step_text = item.partition("/")
        try:
            step = int(step_text) if separator else 1
            if step < 1:
                raise ValueError()
            if base == "*":
                start, end = lo, hi
            elif "-" in base:
                start_text, end_text = base.split("-", 1)
                start, end = int(start_text), int(end_text)
            else:
                start = int(base)
                end = hi if separator else start
            if not lo <= start <= end <= hi:
                raise ValueError()
        except (ValueError, TypeError):
            raise ValueError("Cron 字段无效，仅支持数字、*、范围、列表和 / 步长") from None
        values.update(range(start, end + 1, step))
    return values


def next_run(expression, timezone_name="Asia/Shanghai", after=None):
    parts = expression.split()
    if len(parts) != 5 or len(expression) > 100:
        raise ValueError("Cron 必须包含 5 个字段：分 时 日 月 周")
    minute, hour, day, month, weekday = [
        _field(value, lo, hi)
        for value, (lo, hi) in zip(parts, [(0, 59), (0, 23), (1, 31), (1, 12), (0, 7)])
    ]
    weekday = {value % 7 for value in weekday}
    try:
        zone = ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        raise ValueError("无效的 IANA 时区") from None
    after = datetime.now(timezone.utc).timestamp() if after is None else after
    start = datetime.fromtimestamp(after, zone).date()
    for offset in range(366 * 8 + 1):
        date = start + timedelta(days=offset)
        dom = date.day in day
        dow = (date.weekday() + 1) % 7 in weekday
        matches_day = (dom and dow) if parts[2] == "*" or parts[4] == "*" else (dom or dow)
        if date.month not in month or not matches_day:
            continue
        candidates = set()
        for h in hour:
            for m in minute:
                wall = datetime(date.year, date.month, date.day, h, m)
                for fold in (0, 1):
                    candidate = wall.replace(tzinfo=zone, fold=fold).timestamp()
                    # Reject nonexistent spring-forward wall times.
                    if candidate > after and datetime.fromtimestamp(candidate, zone).replace(tzinfo=None) == wall:
                        candidates.add(int(candidate))
        if candidates:
            return min(candidates)
    raise ValueError("Cron 在未来八年内没有有效执行时间")
