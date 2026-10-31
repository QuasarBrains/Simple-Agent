import platform
import subprocess
from typing import Any

from tools.index import Tool
from utils.pubsub import PubSub


def run(args: Any, ps: PubSub):
    if not args or "command" not in args:
        return "Error running exec_command: No command provided."

    try:
        result = subprocess.run(
            args["command"],
            shell=True,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return f"Command output:\n{result.stdout}"
    except subprocess.CalledProcessError as e:
        return f"Error executing command: {e.stderr}"


# Get the current platform information
current_platform = platform.system()

exec_command = Tool(
    name="exec_command",
    description=f"Execute a system command and return the output. Current platform: {current_platform}",
    function=run,
    parameters={
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The system command to execute.",
            },
        },
        "required": ["command"],
    },
)
