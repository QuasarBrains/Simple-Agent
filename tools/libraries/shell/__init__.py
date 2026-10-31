"""Approval-gated host shell execution; approval belongs to the registry."""

from pathlib import Path

from tools.index import ExecutionPolicy, Tool
from tools.process import (
    DEFAULT_OUTPUT_CHARS,
    DEFAULT_TIMEOUT,
    LIMIT_PROPERTIES,
    failure,
    run_process,
    validate,
)

PARAMETERS = {
    "type": "object",
    "properties": {
        "command": {"type": "string", "minLength": 1},
        "cwd": {
            "type": "string",
            "minLength": 1,
            "description": "Defaults to the resolved process current working directory at invocation; relative paths resolve there. '~' is expanded.",
        },
        **LIMIT_PROPERTIES,
    },
    "required": ["command"],
    "additionalProperties": False,
}


def prepare_arguments(args):
    return args | {
        "cwd": str(Path(args.get("cwd", Path.cwd())).expanduser().resolve(strict=True))
    }


def run(args, pubsub):
    invalid = validate(args, PARAMETERS)
    if invalid is not None:
        return invalid
    try:
        cwd = Path(args.get("cwd", Path.cwd())).expanduser().resolve(strict=True)
        return run_process(
            ["/bin/sh", "-c", args["command"]],
            cwd=cwd,
            timeout=args.get("timeout", DEFAULT_TIMEOUT),
            max_output_chars=args.get("max_output_chars", DEFAULT_OUTPUT_CHARS),
        )
    except (OSError, ValueError, RuntimeError) as error:
        return failure(error)


TOOLS = [
    Tool(
        name="shell.run",
        description=(
            "Run /bin/sh on the host after registry approval. NOT isolated: inherits host "
            "environment, credentials, filesystem and network access; no environment overrides. "
            "cwd defaults to the resolved current working directory at invocation; timeout defaults "
            "to 30 seconds (maximum 120). Combined output is bounded. Process groups are killed "
            "on completion/timeout, but deliberately detached descendants may escape cleanup."
        ),
        function=run,
        parameters=PARAMETERS,
        policy=ExecutionPolicy(requires_approval=True),
        prepare_arguments=prepare_arguments,
    )
]

__all__ = ["TOOLS"]
