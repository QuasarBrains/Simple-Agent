from typing import Any

from tools.index import Tool
from utils.formatting import parse_range
from utils.pubsub import PubSub


def run(args: Any, pubsub: PubSub):
    try:
        file_path = args.get("file_path")
        selection = args.get("selection", "1-")
        content = args.get("content", "")

        # Read the file lines
        with open(file_path, "r") as f:
            lines = f.readlines()

        start, end = parse_range(range=selection, length=len(lines))

        if start is None or end is None:
            return "Invalid selection range"

        # Insert content with newline if needed
        new_content = lines[:start] + [content + "\n"] + lines[end:]

        new_content = "".join(new_content)

        with open(file_path, "w") as f:
            f.write(new_content)

        return f"New file contents:\n```\n{add_line_numbers(new_content)}\n```"
    except Exception as e:
        import traceback

        traceback.print_exc()
        return f"There was an error editing the file: {e}"


edit_file = Tool(
    name="edit_file",
    description="Edit a file",
    function=run,
    parameters={
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "The path to the file to edit.",
            },
            "selection": {
                "type": "string",
                "pattern": "^d+-d+$",
                "description": "The inclusive target line numbers to select, formatted (start-end), you may omit the end and/or start to select from the beginning or to the end. '-' selects the entire file.",
            },
            "content": {
                "type": "string",
                "description": "The content to replace the selection with.",
            },
        },
        "required": ["file_path", "selection", "content"],
    },
)


def add_line_numbers(content: str) -> str:
    lines = content.split("\n")
    lines_with_numbers = []
    for i, line in enumerate(lines):
        lines_with_numbers.append(f"{i+1}: {line}")
    return "\n".join(lines_with_numbers)
