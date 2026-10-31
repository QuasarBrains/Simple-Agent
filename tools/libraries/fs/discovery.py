"""Bounded filesystem enumeration and line search; ignore files are not interpreted."""

import fnmatch
import re

from tools.index import Tool

from ._common import (
    LIMIT,
    MAX_FILE_BYTES,
    OUTPUT,
    PATH,
    SCAN,
    Output,
    entries,
    guarded,
    resolve,
    schema,
    text,
)

BASE = {"path": PATH, "limit": LIMIT, "max_chars": OUTPUT, "max_entries": SCAN}
GLOB = {"type": "string", "minLength": 1, "maxLength": 1024, "default": "*"}
LIST_PARAMETERS = schema(
    {**BASE, "recursive": {"type": "boolean", "default": False}}, ["path"]
)
FIND_PARAMETERS = schema({**BASE, "pattern": GLOB}, ["path", "pattern"])
SEARCH_PARAMETERS = schema(
    {
        **BASE,
        "query": {"type": "string", "minLength": 1, "maxLength": 4096},
        "regex": {"type": "boolean", "default": False},
        "case_sensitive": {"type": "boolean", "default": True},
        "glob": GLOB,
        "max_files": {
            "type": "integer",
            "minimum": 1,
            "maximum": 10000,
            "default": 1000,
        },
    },
    ["path", "query"],
)


def matches(path, root, pattern):
    relative = path.relative_to(root).as_posix()
    if "/" not in pattern:
        return fnmatch.fnmatchcase(path.name, pattern)
    return fnmatch.fnmatchcase(relative, pattern) or (
        pattern.startswith("**/") and matches(path, root, pattern[3:])
    )


def discover(arguments, recursive, pattern=None):
    root = resolve(arguments["path"])
    if not root.is_dir():
        raise ValueError(f"Not a directory: {root}")
    output = Output(arguments)
    state = {"scanned_entries": 0, "scan_limited": False}
    count = 0
    iterator = entries(root, recursive, arguments.get("max_entries", 10000), state)
    try:
        for path in iterator:
            if pattern is not None and not matches(path, root, pattern):
                continue
            if count >= arguments.get("limit", 200):
                output.reasons.append("limit")
                break
            kind = (
                "symlink"
                if path.is_symlink()
                else "directory"
                if path.is_dir()
                else "file"
            )
            if not output.add(f"{kind}\t{path}"):
                break
            count += 1
    finally:
        iterator.close()
    if state["scan_limited"]:
        output.reasons.append("max_entries")
    return output.finish(
        arguments,
        path=str(root),
        returned_entries=count,
        scanned_entries=state["scanned_entries"],
    )


@guarded(LIST_PARAMETERS)
def run_list(arguments, pubsub=None):
    return discover(arguments, arguments.get("recursive", False))


@guarded(FIND_PARAMETERS)
def run_find(arguments, pubsub=None):
    return discover(arguments, True, arguments["pattern"])


@guarded(SEARCH_PARAMETERS)
def run_search(arguments, pubsub=None):
    root = resolve(arguments["path"])
    if not root.exists():
        raise FileNotFoundError(str(root))
    query = arguments["query"]
    sensitive = arguments.get("case_sensitive", True)
    expression = None
    if arguments.get("regex", False):
        try:
            expression = re.compile(query, 0 if sensitive else re.IGNORECASE)
        except re.error as error:
            raise ValueError(f"Invalid regex: {error}") from error
    needle = query if sensitive else query.casefold()
    output = Output(arguments)
    state = {"scanned_entries": 0, "scan_limited": False}
    scanned_files = skipped_files = returned = total_bytes = 0
    iterator = (
        entries(root, True, arguments.get("max_entries", 10000), state)
        if root.is_dir()
        else iter([root])
    )
    try:
        for path in iterator:
            if path.is_symlink() or not path.is_file():
                continue
            if root.is_dir() and not matches(path, root, arguments.get("glob", "*")):
                continue
            if scanned_files >= arguments.get("max_files", 1000):
                output.reasons.append("max_files")
                break
            scanned_files += 1
            try:
                size = path.stat().st_size
                if total_bytes + min(size, MAX_FILE_BYTES) > 32 * MAX_FILE_BYTES:
                    output.reasons.append("max_total_bytes")
                    break
                total_bytes += min(size, MAX_FILE_BYTES)
                content = text(path)
            except (OSError, UnicodeError, ValueError):
                skipped_files += 1
                continue
            stop = False
            for number, line in enumerate(content.splitlines(), 1):
                found = (
                    expression.search(line) is not None
                    if expression is not None
                    else needle in (line if sensitive else line.casefold())
                )
                if not found:
                    continue
                if returned >= arguments.get("limit", 200):
                    output.reasons.append("limit")
                    stop = True
                    break
                if not output.add(f"{path}:{number}: {line}"):
                    stop = True
                    break
                returned += 1
            if stop:
                break
    finally:
        close = getattr(iterator, "close", None)
        if close:
            close()
    if state["scan_limited"]:
        output.reasons.append("max_entries")
    if skipped_files:
        output.reasons.append("skipped_files")
    return output.finish(
        arguments,
        path=str(root),
        returned_matches=returned,
        scanned_files=scanned_files,
        skipped_files=skipped_files,
        scanned_entries=state["scanned_entries"],
    )


LIST_TOOL = Tool(
    "fs.list",
    "List entries, optionally recursively, without following directory symlinks. No implicit ignore rules.",
    run_list,
    LIST_PARAMETERS,
)
FIND_TOOL = Tool(
    "fs.find",
    "Discover entries recursively using case-sensitive shell globs (not regex). Slashless patterns match basenames; slash patterns match relative paths; **/ includes root entries. No implicit ignore rules.",
    run_find,
    FIND_PARAMETERS,
)
SEARCH_TOOL = Tool(
    "fs.search",
    "Search UTF-8 files (up to 4 MiB each, 128 MiB total) for literal text or Python regex, returning matching numbered lines. glob filters paths; no gitignore interpretation. Symlinks and unreadable/binary/oversized files are skipped with metadata.",
    run_search,
    SEARCH_PARAMETERS,
)
