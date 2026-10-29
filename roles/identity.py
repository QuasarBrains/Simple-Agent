from typing import Any, Dict, List, Optional
from llms.llm import LLM
from roles.index import Role
from utils.pubsub import PubSub
from tools.index import Tool, Toolbox
from utils.terminal import console
from rich.text import Text
from roles.config import ROLES_INCLUDED, DEFAULT_ROLE


class IdentityManager:
    current_role: Optional[Role] = None
    available_roles: Dict[str, Role] = {}
    pubsub: PubSub
    toolbox: Toolbox

    def __init__(self, pubsub: PubSub, toolbox: Toolbox) -> None:
        self.pubsub = pubsub
        self.toolbox = toolbox

        self.register_roles(ROLES_INCLUDED)
        self.set_role(DEFAULT_ROLE.name)

    def register_role(self, role: Role) -> None:
        self.available_roles[role.name] = role

    def unregister_role(self, role_name: str) -> None:
        if role_name in self.available_roles:
            del self.available_roles[role_name]
        else:
            raise Exception(f"Role {role_name} not found.")

    def register_roles(self, roles: List[Role]) -> None:
        for role in roles:
            self.register_role(role)

    def unregister_roles(self, role_names: List[str]) -> None:
        for role_name in role_names:
            self.unregister_role(role_name)

    def get_roles_listed(self) -> List[Role]:
        return list(self.available_roles.values())

    def get_roles_described(self) -> str:
        description = ""
        for role in self.available_roles.values():
            description += f"## {role.name}\n**Identity**:{role.identity}\n\n"
        return description

    def set_role(self, role_name: str) -> None:
        console.print(Text.assemble(("Role  ", "dim"), (role_name, "cyan")))
        if self.current_role is not None:
            self.toolbox.unregister_tools(self.current_role.get_tools_listed())
        gotten_role = self.available_roles.get(role_name)
        if gotten_role:
            self.current_role = gotten_role
            self.toolbox.register_tools(self.current_role.get_tools_listed())
        else:
            raise Exception(f"Role {role_name} not found.")

    def set_role_tool(self) -> Tool:
        def run(args: Any, pubsub: PubSub):
            try:
                name = args.get("name")
                if not name:
                    return "No name provided."
                if name not in self.available_roles:
                    return f"Role {name} not found."
                self.set_role(name)
                return f"Role set to {name}."
            except Exception as e:
                return f"Error setting role: {e}"

        return Tool(
            name="set_role",
            description="Set the current role.",
            function=run,
            parameters={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "The name of the role to set.",
                    },
                },
                "required": ["name"],
            },
        )

    def add_roles_to_system_prompt(self, llm: LLM):
        prompt = f"""
        # Available Roles
        {self.get_roles_described()}
        """
        llm.append_to_system_prompt(prompt)
