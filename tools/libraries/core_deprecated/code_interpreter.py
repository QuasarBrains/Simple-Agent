from typing import Any

from tools.index import Tool
from utils.pubsub import PubSub


def execute_python_code(args: Any, ps: PubSub):
    if not args or "code" not in args:
        return "Error running execute_python_code: No code provided."

    code = args["code"]
    try:
        # Create a dictionary to serve as the local namespace for exec
        local_namespace = {}

        # Execute the code
        exec(code, {}, local_namespace)

        # Extract the result from the local namespace
        result = local_namespace.get(
            "result", "No result variable found in the executed code."
        )

        return f"Execution result:\n{result}"
    except Exception as e:
        return f"Error executing code: {e}"


python_interpreter = Tool(
    name="python_interpreter",
    description="Execute Python code and return the value of the 'result' variable.",
    function=execute_python_code,
    parameters={
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "The Python code to execute. Use 'result' variable to return a result.",
            },
        },
        "required": ["code"],
    },
)
