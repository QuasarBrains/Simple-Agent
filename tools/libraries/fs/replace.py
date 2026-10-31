"""Exact replacements; ambiguity never silently edits the first occurrence."""

from tools.index import Tool

from ._common import MAX_FILE_BYTES, PATH, guarded, resolve, result, schema, text

PARAMETERS = schema(
    {
        "path": PATH,
        "old_text": {"type": "string", "minLength": 1, "maxLength": MAX_FILE_BYTES},
        "new_text": {"type": "string", "maxLength": MAX_FILE_BYTES},
        "replace_all": {"type": "boolean", "default": False},
    },
    ["path", "old_text", "new_text"],
)


@guarded(PARAMETERS)
def run_replace(arguments, pubsub=None):
    path = resolve(arguments["path"])
    original = text(path)
    old = arguments["old_text"]
    count = original.count(old)
    if not count:
        raise ValueError("old_text was not found; file unchanged")
    if count != 1 and not arguments.get("replace_all", False):
        raise ValueError(
            f"old_text matches {count} times; set replace_all=true; file unchanged"
        )
    new = arguments["new_text"]
    size = len(original.encode("utf-8")) + count * (
        len(new.encode("utf-8")) - len(old.encode("utf-8"))
    )
    if size > MAX_FILE_BYTES:
        raise ValueError(f"Replacement exceeds {MAX_FILE_BYTES} bytes; file unchanged")
    data = original.replace(old, new).encode("utf-8")
    path.write_bytes(data)
    return result(
        "Replacement applied.",
        arguments,
        path=str(path),
        replacements=count,
        bytes_written=len(data),
    )


TOOL = Tool(
    "fs.replace",
    "Replace exact nonoverlapping text in a UTF-8 file. Requires one match unless replace_all=true. Preserves newline bytes.",
    run_replace,
    PARAMETERS,
)
