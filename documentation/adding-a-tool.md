# Adding a tool

General-purpose tools are discrete functions grouped into capability libraries under `tools/libraries/`.
A stateless library exports a `TOOLS` list; roles compose those lists or select individual tools.
Core agent modules can own their instance-bound tools directly. For example,
`agent/memory.py` exposes `MemoryEngine.get_tools()` for harness registration,
using the same `Tool`, `ToolResult`, and execution policies as library tools.
There is no tool inheritance hierarchy. See [the capability inventory](tooling.md).

## Define an operation

```python
from tools.index import Tool, ToolResult


def run(arguments, pubsub):
    return ToolResult(content=arguments["message"])


TOOL = Tool(
    name="custom.echo",
    description="Return a message unchanged.",
    function=run,
    parameters={
        "type": "object",
        "properties": {"message": {"type": "string"}},
        "required": ["message"],
        "additionalProperties": False,
    },
)

TOOLS = [TOOL]
```

Callables receive `(arguments, pubsub)`, even when they do not use PubSub.
Parameters follow JSON Schema Draft 2020-12. Registration validates schemas;
execution validates arguments and fills top-level property defaults before invoking
an optional `prepare_arguments` function, then validates the prepared arguments again.
Preparation must not execute the requested operation or introduce side effects.

Canonical names use capability namespaces: `fs.read`, `web.fetch`, `custom.echo`.
Adapters encode dots as double underscores (`fs__read`) in provider schemas and
history, and decode returned calls. Native provider replay remains untouched.
Names must fit the shared provider-safe 64-character limit after encoding.
Double underscores and ambiguous underscore/dot boundaries are reserved.
Legacy unnamespaced names remain supported.

## Return an explicit result

`ToolResult` contains:

- `status`: `success`, `error`, `denied`, or `timeout`.
- `content`: concise model-facing text.
- `metadata`: JSON-serializable details such as resolved paths, source URLs,
  exit codes, and explicit truncation indicators.

Return an error status for expected failures rather than a successful string
starting with `Error`. Uncaught exceptions become error results. A timeout or
error does not imply that a mutation was rolled back. Bound expensive work and
output inside the tool; the registry does not impose a universal output limit.

Existing string-returning tools still work and are normalized to successful
results. `Toolbox.execute_result()` returns the structured object; `execute()`
retains its `(content, is_error)` interface and `run_tool()` returns content.
The agent renders structured results as JSON in the model's transcript.

## Approval and isolation

```python
from tools.index import ExecutionPolicy

policy = ExecutionPolicy(requires_approval=True)
```

Attach `policy=policy` to a `Tool` to require approval on every registry invocation.
The host supplies `Toolbox(..., approve=callback)`, where the callback accepts the
tool and prepared arguments and returns `True` only for approval. No callback,
denial, EOF, or interruption fails closed. The CLI offers Approve once / Deny,
defaulting to Deny. Approval decisions also emit `tool.approval` events.

The callback sees a defensive copy of the exact prepared arguments, including
defaults. `shell.run` resolves its working directory before approval. Approval is
for the invocation, not a frozen filesystem snapshot or a security sandbox.
Always dispatch through the registry: directly calling a tool's Python function
bypasses registry approval.

`ExecutionPolicy(isolated=True)` is descriptive metadata, not a sandbox switch.
A tool declaring it must implement and enforce its own isolation, as `python.run`
does. Do not label a subprocess or stripped environment as a security sandbox.

## Compose into a role

```python
from tools.libraries.custom import TOOLS as CUSTOM_TOOLS
from tools.libraries.fs import TOOLS as FILESYSTEM_TOOLS

TOOLS = [*FILESYSTEM_TOOLS, *CUSTOM_TOOLS]
```

Names must be unique in a toolbox. Re-registering the same object is permitted;
registering a different object under an existing name is rejected.
Shared harness operations (tasks, messaging, roles, optional memory) are registered
separately and persist across role changes. See [Adding a role](adding-a-role.md).
