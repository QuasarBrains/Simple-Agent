from tools.index import Tool
from utils.pubsub import PubSub
import requests
from typing import Any


def run(args: Any, ps: PubSub):
    if not args or "url" not in args:
        return "Error running web_request: No URL provided."

    url = args["url"]
    method = args.get("method", "GET").upper()
    headers = args.get("headers", {})
    params = args.get("params", {})
    data = args.get("data", None)

    try:
        response = requests.request(
            method, url, headers=headers, params=params, data=data
        )
        response.raise_for_status()
        text_response = response.text
        if len(text_response) > 2000:
            return f"URL Content [Truncated]:\n```\n{text_response[:2000]}\n```"
        return f"URL Content:\n```\n{response.text}\n```"
    except requests.exceptions.HTTPError as http_err:
        return f"HTTP error occurred: {http_err}"
    except Exception as err:
        return f"Error occurred: {err}"


web_request = Tool(
    name="web_request",
    description="Make a web request to fetch content from a URL",
    function=run,
    parameters={
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The URL to make the request to.",
            },
            "method": {
                "type": "string",
                "description": "HTTP method (GET, POST, etc.). Default is GET.",
                "default": "GET",
            },
            "headers": {
                "type": "object",
                "description": "HTTP headers to send with the request.",
            },
            "params": {
                "type": "object",
                "description": "Query parameters to send with the request.",
            },
            "data": {
                "type": "string",
                "description": "Data to send with the request for POST, PUT, etc.",
            },
        },
        "required": ["url"],
    },
)
