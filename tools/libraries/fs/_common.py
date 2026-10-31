"""Shared limits and validation; no sandbox or access policy is imposed here."""

import os
from functools import wraps
from pathlib import Path

from tools.index import ToolResult

MAX_FILE_BYTES = 4 * 1024 * 1024
PATH = {"type": "string", "minLength": 1, "maxLength": 4096}
OUTPUT = {"type": "integer", "minimum": 1, "maximum": 100000, "default": 20000}
LIMIT = {"type": "integer", "minimum": 1, "maximum": 10000, "default": 200}
SCAN = {"type": "integer", "minimum": 1, "maximum": 100000, "default": 10000}


def schema(properties, required):
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def validate(arguments, spec):
    if not isinstance(arguments, dict):
        raise ValueError("Arguments must be an object")
    if set(arguments) - set(spec["properties"]):
        raise ValueError("Unknown arguments")
    for key in spec["required"]:
        if key not in arguments:
            raise ValueError(f"Missing required argument: {key}")
    for key, value in arguments.items():
        rule = spec["properties"][key]
        kind = rule["type"]
        valid = {
            "string": isinstance(value, str),
            "boolean": type(value) is bool,
            "integer": type(value) is int,
        }[kind]
        if not valid:
            raise ValueError(f"{key} must be {kind}")
        if kind == "string" and not rule.get("minLength", 0) <= len(value) <= rule.get(
            "maxLength", float("inf")
        ):
            raise ValueError(f"{key} has invalid length")
        if kind == "integer" and not rule.get(
            "minimum", -float("inf")
        ) <= value <= rule.get("maximum", float("inf")):
            raise ValueError(f"{key} is out of range")
        if "enum" in rule and value not in rule["enum"]:
            raise ValueError(f"Invalid {key}")


def guarded(spec):
    def decorate(function):
        @wraps(function)
        def run(arguments, pubsub=None):
            try:
                validate(arguments, spec)
                return function(arguments, pubsub)
            except PermissionError as error:
                return failure("denied", error, arguments)
            except (OSError, ValueError, UnicodeError, RuntimeError) as error:
                return failure("error", error, arguments)

        return run

    return decorate


def failure(status, error, arguments):
    cap = arguments.get("max_chars", 2000) if isinstance(arguments, dict) else 2000
    cap = min(cap, 2000) if type(cap) is int and cap > 0 else 2000
    message = str(error)
    truncated = len(message) > cap
    return ToolResult(
        status=status,
        content=message[:cap],
        metadata={
            "truncated": truncated,
            "truncation_reasons": ["max_chars"] if truncated else [],
            "returned_chars": len(message[:cap]),
        },
    )


def resolve(path):
    return Path(path).expanduser().resolve()


def text(path):
    if not path.is_file():
        raise ValueError(f"Not a regular file: {path}")
    with path.open("rb") as stream:
        data = stream.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise ValueError(f"File exceeds {MAX_FILE_BYTES} byte text limit: {path}")
    result = data.decode("utf-8")
    if "\x00" in result:
        raise ValueError(f"Binary files are not supported: {path}")
    return result


def result(content, arguments, **metadata):
    cap = arguments.get("max_chars", 20000)
    reasons = metadata.pop("truncation_reasons", [])
    if len(content) > cap:
        content = content[:cap]
        reasons.append("max_chars")
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


class Output:
    """Collect whole records only, stopping before exceeding the character cap."""

    def __init__(self, arguments):
        self.cap = arguments.get("max_chars", 20000)
        self.records = []
        self.size = 0
        self.reasons = []

    def add(self, record):
        size = len(record) + bool(self.records)
        if self.size + size > self.cap:
            self.reasons.append("max_chars")
            return False
        self.records.append(record)
        self.size += size
        return True

    def finish(self, arguments, **metadata):
        return result(
            "\n".join(self.records),
            arguments,
            truncation_reasons=self.reasons,
            **metadata,
        )


def entries(root, recursive, budget, state):
    """Bound directory enumeration, including nonmatching entries. Never follow links."""
    stack = [root]
    while stack:
        directory = stack.pop()
        with os.scandir(directory) as iterator:
            for entry in iterator:
                if state["scanned_entries"] >= budget:
                    state["scan_limited"] = True
                    return
                state["scanned_entries"] += 1
                path = Path(entry.path)
                yield path
                if recursive and entry.is_dir(follow_symlinks=False):
                    stack.append(path)
