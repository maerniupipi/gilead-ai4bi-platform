"""Display names for ChatBI exports; physical storage continues to use UUIDs."""
import re
import unicodedata
from datetime import datetime, timedelta, timezone


def question_summary(question: str | None) -> str:
    summary = re.sub(r"<[^>]+>", "", question or "")
    summary = re.sub(r"\s+", "_", summary)
    summary = "".join(char for char in summary if not unicodedata.category(char).startswith("C"))
    summary = re.sub(r'[\\/:*?"<>|，。！？、；：,.!?;]', "", summary)
    summary = re.sub(r"^(?:ppt[_\-\s]+)+", "", summary.strip("._ "), flags=re.IGNORECASE)
    return summary.strip("._ ")[:40].rstrip("._ ") or "未命名问题"


def export_file_name(kind: str, summary_type: str | None, first_question: str | None, created_at: datetime) -> str:
    # Keep the established six-digit microsecond serial, independent of the
    # host timezone. The separate UUID remains the storage/identity key.
    created_at = created_at.astimezone(timezone(timedelta(hours=8)))
    timestamp = created_at.strftime("%Y%m%d%H%M%S") + f"{created_at.microsecond:06d}"
    summary = question_summary(first_question)
    if kind == "xlsx":
        return f"AI4BI_Insight_Data_{summary}_{timestamp}.xlsx"
    mode = "SUMMARY" if summary_type == "AI_SUMMARY" else "ALL"
    return f"AI4BI_Insight_Report_{mode}{summary}_{timestamp}.pptx"
