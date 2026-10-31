from abc import ABC, abstractmethod
from dataclasses import dataclass

from tools.index import Tool


@dataclass
class WorkspaceState:
    open: bool = True


class Workspace(ABC):
    name: str

    def __init__(self) -> None:
        self.state = WorkspaceState()

    def open(self) -> None:
        self.state.open = True

    def close(self) -> None:
        self.state.open = False

    def is_open(self) -> bool:
        return self.state.open

    def disclosure_tool(self) -> Tool:
        def run(args, pubsub):
            self.open() if args["open"] else self.close()
            return f"{self.name} workspace is {'open' if self.is_open() else 'closed'}."

        return Tool(
            name=f"workspace.{self.name}.set_open",
            description="Show the workspace's working view or minimize it without deleting state or pausing work.",
            function=run,
            parameters={
                "type": "object",
                "properties": {"open": {"type": "boolean"}},
                "required": ["open"],
                "additionalProperties": False,
            },
        )

    @abstractmethod
    def build_view(self) -> str: ...

    @abstractmethod
    def get_tools(self) -> list[Tool]: ...

    def has_pending_work(self) -> bool:
        return False

    def active_task_ids(self) -> list[str]:
        return []
