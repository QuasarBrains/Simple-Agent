import codecs
from functools import wraps
from urllib.parse import urljoin, urlsplit

import requests
from jsonschema import Draft202012Validator

from tools.index import ToolResult

USER_AGENT = "Simple-Agent/0.1 (read-only web tools)"
DEFAULT_TIMEOUT = 15
MAX_REDIRECTS = 5
MAX_DOWNLOAD_BYTES = 4 * 1024 * 1024
OUTPUT = {"type": "integer", "minimum": 256, "maximum": 50000, "default": 12000}
TIMEOUT = {"type": "integer", "minimum": 1, "maximum": 60, "default": DEFAULT_TIMEOUT}


def schema(properties, required):
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def failure(error, arguments, metadata=None, status="error"):
    cap = arguments.get("max_chars", 2000) if isinstance(arguments, dict) else 2000
    cap = min(cap, 2000) if type(cap) is int and cap > 0 else 2000
    message = str(error)
    return ToolResult(
        status=status,
        content=message[:cap],
        metadata={
            **(metadata or {}),
            "truncated": len(message) > cap,
            "truncation_reasons": ["max_chars"] if len(message) > cap else [],
            "returned_chars": len(message[:cap]),
        },
    )


def network_failure(error, arguments, metadata=None):
    timed_out = isinstance(error, requests.Timeout)
    if isinstance(error, requests.ConnectionError):
        timed_out = "timed out" in str(error).lower()
    advice = (
        "Request timed out; retry or increase timeout."
        if timed_out
        else "Request failed; check the URL, connectivity, and HTTP status before retrying."
    )
    return failure(
        f"{advice} {error}",
        arguments,
        metadata,
        status="timeout" if timed_out else "error",
    )


def guarded(spec):
    def decorate(function):
        @wraps(function)
        def run(arguments, pubsub=None):
            errors = list(Draft202012Validator(spec).iter_errors(arguments))
            if errors:
                return failure(f"Invalid arguments: {errors[0].message}", arguments)
            try:
                return function(arguments, pubsub)
            except (ValueError, TypeError) as error:
                return failure(error, arguments)

        return run

    return decorate


def validate_url(url):
    parsed = urlsplit(url)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Only absolute http:// or https:// URLs are supported.")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("URLs containing credentials are not supported.")
    if any(character.isspace() or ord(character) < 32 for character in url):
        raise ValueError("URL must not contain whitespace or control characters.")
    parsed.port
    return url


def download(url, *, timeout, max_bytes, metadata, params=None):
    current = validate_url(url)
    metadata["requested_url"] = url
    metadata["downloaded_bytes"] = 0
    metadata["retained_bytes"] = 0
    for redirect in range(MAX_REDIRECTS + 1):
        metadata["final_url"] = current
        with requests.get(
            current,
            params=params,
            stream=True,
            timeout=(timeout, timeout),
            allow_redirects=False,
            headers={"User-Agent": USER_AGENT},
        ) as response:
            metadata["final_url"] = response.url or current
            validate_url(metadata["final_url"])
            metadata["http_status"] = response.status_code
            if response.status_code in {301, 302, 303, 307, 308}:
                if redirect == MAX_REDIRECTS:
                    raise ValueError(f"Too many redirects (maximum {MAX_REDIRECTS}).")
                location = response.headers.get("Location")
                if not location:
                    raise ValueError("HTTP redirect did not provide a Location header.")
                current = validate_url(urljoin(metadata["final_url"], location))
                params = None
                continue
            response.raise_for_status()
            if not 200 <= response.status_code < 300:
                raise ValueError(f"Unexpected HTTP status {response.status_code}.")
            metadata["content_type"] = response.headers.get("Content-Type", "")[:256]
            data = bytearray()
            truncated = False
            for chunk in response.iter_content(chunk_size=min(16384, max_bytes + 1)):
                if not chunk:
                    continue
                remaining = max_bytes - len(data)
                data.extend(chunk[:remaining])
                metadata["downloaded_bytes"] += len(chunk)
                metadata["retained_bytes"] = len(data)
                if len(chunk) > remaining:
                    truncated = True
                    break
            metadata["download_truncated"] = truncated
            encoding = response.encoding
            if not encoding or (
                encoding.lower() == "iso-8859-1"
                and "charset=" not in metadata["content_type"].lower()
            ):
                encoding = "utf-8"
            try:
                codecs.lookup(encoding)
            except LookupError:
                encoding = "utf-8"
            return bytes(data), encoding
    raise ValueError("Unable to complete request.")
