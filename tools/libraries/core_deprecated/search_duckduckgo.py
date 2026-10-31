from typing import Any

from ddgs import DDGS

from tools.index import Tool
from utils.pubsub import PubSub


def run_search_duckduckgo(args: Any, pubsub: PubSub) -> str:
    if not args or "query" not in args:
        return "Error running search_duckduckgo: No query provided."

    query = args.get("query")

    results = DDGS().text(query, backend="duckduckgo")

    if not results:
        return "No results found for the given query."

    results_str = ""
    for result in results:
        title = result.get("title")
        href = result.get("href")
        body = result.get("body")
        results_str += f"{title} ({href}): {body}\n"

    return results_str


search_duckduckgo = Tool(
    name="search_duckduckgo",
    description="Search DuckDuckGo for information on a given query.",
    function=run_search_duckduckgo,
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search term for finding relevant DuckDuckGo search results.",
            },
        },
        "required": ["query"],
    },
)
