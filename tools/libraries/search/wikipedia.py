import json
from urllib.parse import quote

import requests

from tools.index import Tool
from tools.libraries.web._common import download, failure, guarded, network_failure

from ._common import PARAMETERS, query, search_result

API_URL = "https://en.wikipedia.org/w/api.php"
MAX_API_BYTES = 1024 * 1024


@guarded(PARAMETERS)
def run_with_wikipedia(arguments, pubsub=None):
    text = query(arguments)
    count = arguments.get("count", 5)
    metadata = {"provider": "wikipedia"}
    try:
        data, encoding = download(
            API_URL,
            timeout=arguments.get("timeout", 15),
            max_bytes=MAX_API_BYTES,
            metadata=metadata,
            params={
                "action": "query",
                "list": "search",
                "srsearch": text,
                "srlimit": count,
                "srprop": "snippet|timestamp",
                "format": "json",
                "formatversion": 2,
                "utf8": 1,
            },
        )
        if metadata["download_truncated"]:
            return failure(
                "Wikipedia API response exceeds the 1 MiB limit; narrow the query.",
                arguments,
                metadata,
            )
        payload = json.loads(data.decode(encoding))
        if "error" in payload:
            error = payload["error"]
            return failure(
                f"Wikipedia API error: {error}. Adjust the query or retry later.",
                arguments,
                metadata,
            )
        hits = payload.get("query", {}).get("search")
        if not isinstance(hits, list):
            raise ValueError(
                "Wikipedia returned an invalid search response; retry later."
            )
        rows = [
            {
                "title": hit["title"],
                "url": "https://en.wikipedia.org/wiki/"
                + quote(hit["title"].replace(" ", "_"), safe=""),
                "excerpt": hit.get("snippet"),
                "date": hit.get("timestamp"),
                "date_kind": "page_updated",
            }
            for hit in hits[:count]
        ]
        metadata.pop("provider", None)
        return search_result(rows, arguments, "wikipedia", **metadata)
    except requests.RequestException as error:
        return network_failure(error, arguments, metadata)
    except (ValueError, KeyError, TypeError, AttributeError) as error:
        return failure(f"Invalid Wikipedia API response: {error}", arguments, metadata)


TOOL = Tool(
    "search.with_wikipedia",
    "Search English Wikipedia via the MediaWiki search API (not page lookup). "
    "Return up to 10 titles, article URLs, excerpts and page-edit timestamps (not news publication "
    "or event dates). Prefer a news search for today's headlines. API download capped at 1 MiB.",
    run_with_wikipedia,
    PARAMETERS,
)
