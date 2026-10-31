import json
import re
from html import unescape

from bs4 import BeautifulSoup

from tools.index import ToolResult
from tools.libraries.web._common import OUTPUT, TIMEOUT, schema

PARAMETERS = schema(
    {
        "query": {"type": "string", "minLength": 1, "maxLength": 500},
        "count": {"type": "integer", "minimum": 1, "maximum": 10, "default": 5},
        "max_chars": OUTPUT,
        "timeout": TIMEOUT,
    },
    ["query"],
)


def query(arguments):
    value = arguments["query"].strip()
    if not value:
        raise ValueError("query must contain non-whitespace characters.")
    return value


def plain(value):
    text = str(value or "")
    if re.search(r"</?[A-Za-z][^>]*>", text):
        text = " ".join(BeautifulSoup(text, "html.parser").stripped_strings)
    else:
        text = unescape(text)
    return " ".join(text.split())


def search_result(rows, arguments, provider, **metadata):
    records = []
    reasons = list(metadata.pop("truncation_reasons", []))
    cap = arguments.get("max_chars", 12000)
    for row in rows:
        record = {
            "title": plain(row.get("title")),
            "url": str(row.get("url") or ""),
            "excerpt": plain(row.get("excerpt")),
            "provider": provider,
        }
        if row.get("date"):
            record["date"] = str(row["date"])
            if row.get("date_kind"):
                record["date_kind"] = str(row["date_kind"])
        for field, limit in (
            ("title", 300),
            ("url", 2048),
            ("excerpt", 1000),
            ("date", 100),
            ("date_kind", 40),
        ):
            if len(record.get(field, "")) > limit:
                record[field] = record[field][:limit]
                if "field_limits" not in reasons:
                    reasons.append("field_limits")
        if len(json.dumps(records + [record], ensure_ascii=False)) > cap:
            reasons.append("max_chars")
            break
        records.append(record)
    content = json.dumps(records, ensure_ascii=False)
    return ToolResult(
        status="success",
        content=content,
        metadata={
            **metadata,
            "query": arguments["query"].strip(),
            "provider": provider,
            "results": records,
            "count": len(records),
            "requested_count": arguments.get("count", 5),
            "truncated": bool(reasons),
            "truncation_reasons": reasons,
            "returned_chars": len(content),
        },
    )
