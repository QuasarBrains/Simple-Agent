from tools.index import Tool, ToolResult


def notify(arguments, pubsub):
    pubsub.publish("new_agent_message", arguments["content"])
    return ToolResult(
        content="Update delivered. Continue working; no reply was requested."
    )


def ask(arguments, pubsub):
    pubsub.publish("new_agent_message", arguments["content"])
    return ToolResult(
        content="Question delivered. Execution is paused until the user replies; unfinished tasks remain open.",
        metadata={"wait_for": "user"},
    )


def finish(arguments, pubsub):
    if arguments.get("content"):
        pubsub.publish("new_agent_message", arguments["content"])
    return ToolResult(
        content="Turn finished. Execution is paused until new user input or an external stimulus arrives; unfinished tasks remain open.",
        metadata={"wait_for": "stimulus"},
    )


def parameters(required=True):
    return {
        "type": "object",
        "properties": {
            "content": {"type": "string", "minLength": 1, "pattern": r"\S"},
        },
        "required": ["content"] if required else [],
        "additionalProperties": False,
    }


NOTIFY = Tool(
    name="interaction.notify",
    description=(
        "Send a nonblocking progress update while continuing work. Does not ask for input or end "
        "the turn. Use ask for a question, or finish for a completed answer."
    ),
    function=notify,
    parameters=parameters(),
)
ASK = Tool(
    name="interaction.ask",
    description=(
        "Ask the user a question that needs a reply, then pause execution until the user responds. "
        "Open tasks are preserved but do not keep running. This ends the current tool batch; "
        "do not include later calls. Use finish instead when no answer is required."
    ),
    function=ask,
    parameters=parameters(),
)
FINISH = Tool(
    name="interaction.finish",
    description=(
        "Deliver a completed answer and end the turn without asking a question. Pause until new "
        "user input or an external stimulus wakes the agent. Optional content can be omitted if "
        "the answer has already been displayed. Does not complete or delete tasks. This ends the "
        "current tool batch; do not include later calls."
    ),
    function=finish,
    parameters=parameters(required=False),
)
TOOLS = [NOTIFY, ASK, FINISH]
WAIT_MODES = {ASK.name: "user", FINISH.name: "stimulus"}

__all__ = ["TOOLS", "WAIT_MODES"]
