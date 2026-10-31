"""Canonical tool names and their provider-safe wire representation."""

import re

_CANONICAL_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_-]*(?:\.[A-Za-z_][A-Za-z0-9_-]*)*")
_WIRE_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_-]{0,63}")


def validate_tool_name(name: str) -> str:
    if not isinstance(name, str) or not _CANONICAL_NAME.fullmatch(name):
        raise ValueError(f"Invalid canonical tool name: {name!r}")
    if "__" in name:
        raise ValueError("Canonical tool names cannot contain reserved '__'")
    encoded = name.replace(".", "__")
    if encoded.replace("__", ".") != name:
        raise ValueError(f"Ambiguous underscore/dot boundary in tool name: {name!r}")
    if not _WIRE_NAME.fullmatch(encoded):
        raise ValueError(
            "Encoded tool names must be provider-safe and at most 64 characters"
        )
    return name


def encode_tool_name(name: str) -> str:
    return validate_tool_name(name).replace(".", "__")


def decode_tool_name(name: str) -> str:
    return name.replace("__", ".")
