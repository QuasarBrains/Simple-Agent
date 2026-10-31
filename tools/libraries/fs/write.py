"""Explicit UTF-8 file creation or overwrite; parent creation is opt-in."""

from tools.index import Tool

from ._common import MAX_FILE_BYTES, PATH, guarded, resolve, result, schema

PARAMETERS = schema(
    {
        "path": PATH,
        "content": {"type": "string", "maxLength": MAX_FILE_BYTES},
        "overwrite": {"type": "boolean", "default": False},
        "create_parents": {"type": "boolean", "default": False},
    },
    ["path", "content"],
)


@guarded(PARAMETERS)
def run_write(arguments, pubsub=None):
    path = resolve(arguments["path"])
    if path.exists() and not path.is_file():
        raise ValueError(f"Not a regular file: {path}")
    data = arguments["content"].encode("utf-8")
    if len(data) > MAX_FILE_BYTES:
        raise ValueError(f"Content exceeds {MAX_FILE_BYTES} bytes")
    if arguments.get("create_parents", False):
        path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb" if arguments.get("overwrite", False) else "xb") as stream:
        stream.write(data)
    return result("File written.", arguments, path=str(path), bytes_written=len(data))


TOOL = Tool(
    "fs.write",
    "Write UTF-8 text (up to 4 MiB). Existing files require overwrite=true; parent creation is opt-in.",
    run_write,
    PARAMETERS,
)
