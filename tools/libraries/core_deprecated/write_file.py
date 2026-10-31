from typing import Any

from tools.index import Tool
from utils.pubsub import PubSub


def run(args: Any, ps: PubSub):
    if not args:
        return "Error running send_message_to_user: No message provided."
    try:
        contents = args.get("content")
        with open(args["file_path"], "w") as file:
            file.write(contents)
        with open(args["file_path"], "r") as file:
            content = file.read()
            return f"New file content: \n{content}"

        return "File not read."
    except Exception as e:
        return f"Error writing to file: {e}"


write_file = Tool(
    name="write_file",
    description="Write to a file",
    function=run,
    parameters={
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "The path to the file to read.",
            },
            "content": {
                "type": "string",
                "description": "The content to write to the file.",
            },
            "mode": {
                "type": "string",
                "enum": ["w", "a", "x"],
                "description": "The mode to open the file in. Defaults to 'w'.",
            },
        },
        "required": ["file_path", "content", "mode"],
    },
)
