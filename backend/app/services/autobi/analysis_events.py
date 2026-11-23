"""Protocol-neutral decoding shared by BI presentation adapters."""
import json


def decode(chunk):
    if isinstance(chunk, dict):
        return chunk
    for line in str(chunk).splitlines():
        if line.startswith("data:"):
            return json.loads(line[5:].strip())
    return {}


def features(value):
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value:
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except (TypeError, ValueError):
            pass
    return {}


def normalize(payload):
    if str(payload.get("status_code") or "").upper() in {"FAILED", "ERROR"}:
        raise RuntimeError("分析引擎返回失败状态")
    if isinstance(payload.get("message"), dict):
        msg = dict(payload["message"])
        msg["features"] = features(msg.get("features"))
        return msg
    typ = payload.get("type")
    if typ == "error":
        raise RuntimeError(payload.get("message") or "分析执行失败")
    if typ == "summary":
        return {"type": "text", "content": payload.get("delta", "")}
    if typ == "bailian_progress":
        return {"type": "progress", "content": payload.get("progress", "")}
    if typ == "bailian_sql":
        return {"type": "sql_citations", "features": {"sql_citations": [{
            "query": payload.get("query", ""), "sql": payload.get("sql", ""),
        }]}}
    if typ == "bailian_data":
        return {"type": "data_citations", "features": {"data_citations": [{
            "query": payload.get("query", ""), "data": payload.get("data", []),
            "columns": payload.get("columns", []),
            "total_count": payload.get("total_count", len(payload.get("data", []))),
        }]}}
    if typ == "bailian_chart" and payload.get("sql_data"):
        spec, data = payload.get("chart_spec") or {}, payload["sql_data"]
        def keys(value):
            return value if isinstance(value, list) else [value] if value else []
        xs, ys = keys(spec.get("xaxis")), keys(spec.get("yaxis"))
        cols = [{"key": key, "name": key, "target": "xaxis" if key in xs else "yaxis" if key in ys else ""}
                for key in data.get("columns", [])]
        return {"type": "chart_citations", "features": {"chart_citations": [{
            "query": spec.get("title", ""), "chart": {"type": spec.get("type", "A"),
            "columns": cols, "data": data.get("rows", [])},
        }]}}
    return payload
