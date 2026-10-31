"""UTF-8 text reading with inclusive, one-based line ranges (no PDF extraction)."""

from tools.index import Tool

from ._common import OUTPUT, PATH, guarded, resolve, result, schema, text

PARAMETERS = schema(
    {
        "path": PATH,
        "start_line": {"type": "integer", "minimum": 1, "default": 1},
        "end_line": {"type": "integer", "minimum": 1},
        "max_chars": OUTPUT,
    },
    ["path"],
)


@guarded(PARAMETERS)
def run_read(arguments, pubsub=None):
    path = resolve(arguments["path"])
    start = arguments.get("start_line", 1)
    end = arguments.get("end_line")
    if end is not None and end < start:
        raise ValueError("end_line must be >= start_line")
    lines = text(path).splitlines()
    selected = lines[start - 1 : end]
    content = "\n".join(
        f"{number}: {line}" for number, line in enumerate(selected, start)
    )
    return result(
        content,
        arguments,
        path=str(path),
        total_lines=len(lines),
        start_line=start,
        end_line=min(end or len(lines), len(lines)),
        selected_lines=len(selected),
    )


TOOL = Tool(
    "fs.read",
    "Read UTF-8 text (up to 4 MiB), with one-based inclusive line ranges and line numbers.",
    run_read,
    PARAMETERS,
)
