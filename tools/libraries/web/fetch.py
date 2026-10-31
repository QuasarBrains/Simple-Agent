import requests
from bs4 import BeautifulSoup

from tools.index import Tool, ToolResult

from ._common import (
    MAX_DOWNLOAD_BYTES,
    OUTPUT,
    TIMEOUT,
    download,
    failure,
    guarded,
    network_failure,
    schema,
    validate_url,
)

PARAMETERS = schema(
    {
        "url": {"type": "string", "minLength": 1, "maxLength": 4096},
        "max_chars": OUTPUT,
        "max_bytes": {
            "type": "integer",
            "minimum": 1,
            "maximum": MAX_DOWNLOAD_BYTES,
            "default": 1024 * 1024,
        },
        "timeout": TIMEOUT,
    },
    ["url"],
)


@guarded(PARAMETERS)
def run_fetch(arguments, pubsub=None):
    metadata = {"requested_url": arguments["url"], "title": ""}
    try:
        validate_url(arguments["url"])
        data, encoding = download(
            arguments["url"],
            timeout=arguments.get("timeout", 15),
            max_bytes=arguments.get("max_bytes", 1024 * 1024),
            metadata=metadata,
        )
        media_type = metadata["content_type"].split(";", 1)[0].strip().lower()
        text = data.decode(encoding, errors="replace")
        if media_type in {"text/html", "application/xhtml+xml", ""}:
            soup = BeautifulSoup(text, "html.parser")
            if soup.title:
                metadata["title"] = " ".join(soup.title.stripped_strings)[:500]
            for element in soup(
                [
                    "script",
                    "style",
                    "noscript",
                    "template",
                    "svg",
                    "nav",
                    "footer",
                    "header",
                    "form",
                ]
            ):
                element.decompose()
            body = soup.find("main") or soup.find("article") or soup.body or soup
            text = "\n".join(
                line
                for part in body.get_text(separator="\n").splitlines()
                if (line := " ".join(part.split()))
            )
        elif not (
            media_type.startswith("text/")
            or media_type in {"application/json", "application/xml"}
            or media_type.endswith(("+json", "+xml"))
        ):
            return failure(
                f"Unsupported content type '{media_type}'; fetch supports HTML and text, not binary files.",
                arguments,
                metadata,
            )
        reasons = []
        if metadata["download_truncated"]:
            reasons.append("max_bytes")
        cap = arguments.get("max_chars", 12000)
        if len(text) > cap:
            reasons.append("max_chars")
        content = text[:cap]
        return ToolResult(
            status="success",
            content=content,
            metadata={
                **metadata,
                "truncated": bool(reasons),
                "truncation_reasons": reasons,
                "returned_chars": len(content),
            },
        )
    except requests.RequestException as error:
        return network_failure(error, arguments, metadata)
    except ValueError as error:
        return failure(error, arguments, metadata)


TOOL = Tool(
    "web.fetch",
    "Fetch readable HTML/text over HTTP(S), with bounded streaming download and output. "
    "No JavaScript, browser, or network permission enforcement. timeout is per connect/read operation.",
    run_fetch,
    PARAMETERS,
)
