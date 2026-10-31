import json
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Literal

from jsonschema import Draft202012Validator, ValidationError

from tools.names import validate_tool_name
from utils.pubsub import PubSub


@dataclass(frozen=True)
class ExecutionPolicy:
    requires_approval: bool = False
    isolated: bool = False


@dataclass
class ToolResult:
    status: Literal["success", "error", "denied", "timeout"] = "success"
    content: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.status not in {"success", "error", "denied", "timeout"}:
            raise ValueError(f"Invalid tool result status: {self.status}")

    @property
    def is_error(self) -> bool:
        return self.status != "success"

    def render(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, allow_nan=False)


@dataclass
class Tool:
    name: str
    description: str
    function: Callable[[Any, PubSub], str | ToolResult]
    parameters: dict[str, Any]
    policy: ExecutionPolicy = field(default_factory=ExecutionPolicy)
    prepare_arguments: Callable[[dict], dict] | None = None


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


class Toolbox:
    def __init__(
        self,
        pubsub: PubSub,
        approve: Callable[[Tool, dict], bool] | None = None,
    ) -> None:
        self.pubsub = pubsub
        self.tools: dict[str, Tool] = {}
        self.approve = approve

    def execute_result(self, call: ToolCall) -> ToolResult:
        tool = self.get_tool(call.name)
        arguments = deepcopy(call.arguments)
        if tool is None:
            result = ToolResult(
                "error", f"Tool '{call.name}' not found in the current role."
            )
        else:
            try:
                Draft202012Validator(tool.parameters).validate(arguments)
                for name, schema in tool.parameters.get("properties", {}).items():
                    if (
                        name not in arguments
                        and isinstance(schema, dict)
                        and "default" in schema
                    ):
                        arguments[name] = deepcopy(schema["default"])
                if tool.prepare_arguments:
                    arguments = tool.prepare_arguments(arguments)
                Draft202012Validator(tool.parameters).validate(arguments)
                json.dumps(arguments, allow_nan=False)
                if tool.policy.requires_approval:
                    approved = (
                        self.approve is not None
                        and self.approve(tool, deepcopy(arguments)) is True
                    )
                    self.pubsub.publish(
                        "tool.approval",
                        {"call_id": call.id, "name": call.name, "approved": approved},
                    )
                    if not approved:
                        result = ToolResult(
                            "denied",
                            "User approval was not granted; nothing was executed.",
                        )
                    else:
                        result = self._invoke(tool, arguments)
                else:
                    result = self._invoke(tool, arguments)
            except ValidationError as error:
                result = ToolResult(
                    "error", f"Invalid arguments for {call.name}: {error.message}"
                )
            except (EOFError, KeyboardInterrupt):
                result = ToolResult("denied", "Approval or execution was interrupted.")
            except Exception as error:
                result = ToolResult("error", f"Tool {call.name} failed: {error}")
        self.tool_log(call.name, result.render(), arguments)
        return result

    def _invoke(self, tool: Tool, arguments: dict) -> ToolResult:
        value = tool.function(arguments, self.pubsub)
        result = (
            value if isinstance(value, ToolResult) else ToolResult(content=str(value))
        )
        result.render()
        return result

    def execute(self, call: ToolCall) -> tuple[str, bool]:
        result = self.execute_result(call)
        return result.content, result.is_error

    def run_tool(self, tool_name: str, arguments: Any) -> str:
        return self.execute(ToolCall("direct", tool_name, arguments))[0]

    def get_tools_listed(self) -> list[Tool]:
        return list(self.tools.values())

    def get_tool(self, tool_name: str) -> Tool | None:
        return self.tools.get(tool_name)

    def tool_log(self, tool_name: str, message: str, arguments: Any = None):
        self.pubsub.publish(
            "toolbox_log", f'Ran {tool_name}({arguments}) and result "{message}"'
        )

    def register_tool(self, tool: Tool):
        validate_tool_name(tool.name)
        Draft202012Validator.check_schema(tool.parameters)
        if tool.name in self.tools and self.tools[tool.name] is not tool:
            raise ValueError(f"Tool '{tool.name}' is already registered.")
        self.tools[tool.name] = tool

    def unregister_tool(self, tool: Tool):
        if tool.name not in self.tools:
            raise ValueError(f"Tool '{tool.name}' not found.")
        del self.tools[tool.name]

    def register_tools(self, tools: list[Tool]):
        for tool in tools:
            self.register_tool(tool)

    def unregister_tools(self, tools: list[Tool]):
        for tool in tools:
            self.unregister_tool(tool)
