from itertools import islice

from ddgs import DDGS
from ddgs.exceptions import DDGSException, TimeoutException

from tools.index import Tool
from tools.libraries.web._common import failure, guarded

from ._common import PARAMETERS as COMMON_PARAMETERS
from ._common import query, search_result

PARAMETERS = COMMON_PARAMETERS | {
    "properties": COMMON_PARAMETERS["properties"]
    | {
        "mode": {
            "type": "string",
            "enum": ["web", "news"],
            "default": "web",
            "description": "Use news for headlines and dated articles; web for general pages.",
        },
        "time_range": {
            "type": "string",
            "enum": ["day", "week", "month", "year"],
            "description": "Optional provider recency filter. day means roughly the past 24 hours, not a guaranteed local calendar date; verify article dates.",
        },
        "region": {
            "type": "string",
            "minLength": 2,
            "maxLength": 16,
            "default": "us-en",
            "description": "Search locale, for example us-en, uk-en, or wt-wt.",
        },
    }
}
TIME_RANGES = {"day": "d", "week": "w", "month": "m", "year": "y"}


@guarded(PARAMETERS)
def run_with_duckduckgo(arguments, pubsub=None):
    text = query(arguments)
    count = arguments.get("count", 5)
    mode = arguments.get("mode", "web")
    metadata = {
        "provider": "duckduckgo",
        "mode": mode,
        "region": arguments.get("region", "us-en"),
        "time_range": arguments.get("time_range"),
    }
    try:
        client = DDGS(timeout=arguments.get("timeout", 15))
        search = client.news if mode == "news" else client.text
        hits = search(
            text,
            max_results=count,
            backend="duckduckgo",
            region=metadata["region"],
            timelimit=TIME_RANGES.get(arguments.get("time_range")),
        )
        rows = [
            {
                "title": row.get("title"),
                "url": row.get("href") or row.get("url"),
                "excerpt": row.get("body") or row.get("snippet") or row.get("excerpt"),
                "date": row.get("date"),
            }
            for row in islice(hits, count)
        ]
        metadata.pop("provider")
        return search_result(rows, arguments, "duckduckgo", **metadata)
    except TimeoutException as error:
        return failure(
            f"DuckDuckGo timed out; retry or increase timeout. {error}",
            arguments,
            metadata,
            status="timeout",
        )
    except DDGSException as error:
        return failure(
            f"DuckDuckGo search failed; the provider may be unavailable or rate limiting. {error}",
            arguments,
            metadata,
        )
    except Exception as error:
        return failure(
            f"DuckDuckGo client failed ({type(error).__name__}): {error}",
            arguments,
            metadata,
        )


TOOL = Tool(
    "search.with_duckduckgo",
    "Search DuckDuckGo for up to 10 results with title, URL, excerpt, provider and optional date. "
    "For current news use mode=news with time_range=day, then fetch sources to verify publication dates "
    "and claims. Recency filters are provider hints, not date guarantees. "
    "Uses only the DuckDuckGo backend, not automatic cross-provider metasearch. "
    "Query, excerpts and total output are bounded; no network permission enforcement.",
    run_with_duckduckgo,
    PARAMETERS,
)
