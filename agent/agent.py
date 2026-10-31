import json
import threading
import time
import traceback
from typing import List, Optional

from agent.environment import Environment
from agent.memory import MemoryEngine
from agent.workspaces.notepad import Notepad
from agent.workspaces.tasks import Tasks
from agent.workspaces.workspace import Workspace
from llms.costs import BudgetExceeded, PricingUnavailable
from llms.llm import LLM, LLMError, Message
from memory.service import MemoryService
from memory.vector_store import VectorStore
from roles.identity import IdentityManager
from tools.index import Toolbox, ToolResult
from tools.libraries.interaction import TOOLS as INTERACTION_TOOLS
from tools.libraries.interaction import WAIT_MODES
from utils.pubsub import PubSub
from utils.terminal import console, terminal
from utils.tokens import get_current_num_tokens


class Agent:
    pubsub: PubSub
    messages: List[Message] = []
    toolbox: Toolbox
    llm: LLM
    environment: Environment
    memory: MemoryEngine
    identity: IdentityManager
    vector_store: Optional[VectorStore]
    workspaces: list[Workspace]
    running: bool = False
    awake: bool = False
    thread: threading.Thread
    verbose: bool
    silence_actions: bool
    iteration: int = 0

    def __init__(
        self,
        pubsub: PubSub,
        llm: LLM,
        vector_store: Optional[VectorStore],
        toolbox: Toolbox,
        verbose: bool,
        silence_actions: bool,
        memory_service: Optional[MemoryService] = None,
        memory_recall_limit: int = 3,
        memory_token_budget: int = 1000,
    ) -> None:
        self.pubsub = pubsub
        self.messages = []
        self.waiting_for: str | None = None
        self._stop_requested = threading.Event()
        self.llm = llm
        self.toolbox = toolbox
        self.verbose = verbose
        self.silence_actions = silence_actions
        self.environment = Environment(pubsub=pubsub)
        self.memory = MemoryEngine(
            pubsub=pubsub,
            vector_store=vector_store,
            llm=llm,
            service=memory_service,
            recall_limit=memory_recall_limit,
            token_budget=memory_token_budget,
        )
        self.workspaces = [
            Tasks(pubsub=pubsub, silence_actions=silence_actions),
            Notepad(),
        ]
        self.vector_store = vector_store
        self.thread = threading.Thread(target=self.run)
        self.identity = IdentityManager(pubsub=pubsub, toolbox=self.toolbox)

        self.initialize_default_tools()

    def initialize_default_tools(self):
        self.toolbox.register_tools(INTERACTION_TOOLS)

        for workspace in self.workspaces:
            self.toolbox.register_tools(workspace.get_tools())
        self.toolbox.register_tool(self.identity.set_role_tool())

        self.toolbox.register_tools(self.memory.get_tools())

        self.identity.add_roles_to_system_prompt(llm=self.llm)

    def start(self):
        self._stop_requested.clear()
        self.running = True
        self.thread.start()

    def stop(self):
        self._stop_requested.set()
        self.running = False

    def error(self, message: str):
        self.pubsub.publish("agent_error", message)

    def log(self, message: str):
        self.pubsub.publish("agent_log", message)

    def log_messages(self):
        json_messages = json.dumps([message.to_json() for message in self.messages])
        self.pubsub.publish("agent_log", json_messages)

    def run(self):
        while self.running:
            try:
                self.memory.sync_messages(self.messages)
                if self.check_waking_state():
                    self.log_messages()
                    self.iteration += 1
                    if self.verbose:
                        self.log(f"Iteration {self.iteration}")
                    self.act(self.reason())
                else:
                    time.sleep(1)
            except (BudgetExceeded, PricingUnavailable, LLMError) as error:
                self.error(f"Agent stopped: {error}")
                self.running = False
            except Exception as error:
                self.pubsub.publish(
                    "agent_exception",
                    {
                        "type": type(error).__name__,
                        "message": str(error),
                        "traceback": traceback.format_exc(),
                    },
                )
                self.error(f"Agent stopped: {type(error).__name__}: {error}")
                self.running = False

    def check_waking_state(self):
        if self.waiting_for is not None:
            ready = (
                self.environment.has_user_messages()
                if self.waiting_for == "user"
                else self.environment.has_external_stimuli()
            )
            if not ready:
                self.awake = False
                return False
            previous = self.waiting_for
            self.waiting_for = None
            self.pubsub.publish("agent.resumed", {"mode": previous})
        self.awake = (
            any(workspace.has_pending_work() for workspace in self.workspaces)
            or self.environment.new_stimuli()
        )
        return self.awake

    def wait_for(self, mode: str):
        self.waiting_for = mode
        self.awake = False
        self.pubsub.publish("agent.waiting", {"mode": mode})

    def send_message(self, message: str):
        self.pubsub.publish("new_agent_message", message)

    def reason(self):
        """
        This is where the agent will reason about the environment.
        """
        self.memory.evaluate_memory(self.environment.peek_environment())

        prompt = self.build_prompt()

        self.messages.append(
            Message(
                id=None,
                role="user",
                content=prompt,
                tool_calls=None,
            )
        )

        with terminal.thinking():
            task_ids = [
                task_id
                for workspace in self.workspaces
                for task_id in workspace.active_task_ids()
            ]
            task_id = task_ids[0] if len(task_ids) == 1 else "__shared__"
            response_message = self.llm.get_response(
                self.messages, self.toolbox.get_tools_listed(), task_id=task_id
            )

        self.messages.append(response_message)

        if self.verbose:
            self.log(f"Response message: {response_message}\n")

        return response_message

    def act(self, message: Message):
        """
        This is where the agent will act based on the message.
        """

        if message.content and not self._stop_requested.is_set():
            content = message.content
            limit = self.llm.config.display_max_chars
            if limit and len(content) > limit:
                content = content[:limit] + "...[TRUNCATED FOR DISPLAY]"
            self.send_message(content)

        if not message.tool_calls:
            if self._stop_requested.is_set():
                return False
            if message.content:
                self.wait_for("stimulus")
                return True
            return self.error("No tool calls or message provided.")

        wait_mode = None
        for tool_call in message.tool_calls:
            if self.verbose:
                self.log(
                    f"Running {tool_call.name} with arguments: {tool_call.arguments}"
                )
            if not self.silence_actions and (
                self.verbose or not tool_call.name.startswith("interaction.")
            ):
                console.print(f"  ↳ {tool_call.name}", style="dim", markup=False)

            self.pubsub.publish(
                "tool.started", {"call_id": tool_call.id, "name": tool_call.name}
            )
            started = time.monotonic()
            if wait_mode is not None or self._stop_requested.is_set():
                result = ToolResult(
                    status="denied",
                    content=(
                        "Not executed: the agent is shutting down."
                        if self._stop_requested.is_set()
                        else "Not executed: an earlier interaction call ended this tool batch. Request this operation again after resuming if still needed."
                    ),
                    metadata={"skipped": True},
                )
                self.toolbox.tool_log(
                    tool_call.name, result.render(), tool_call.arguments
                )
            else:
                result = self.toolbox.execute_result(tool_call)
                if not result.is_error and tool_call.name in WAIT_MODES:
                    wait_mode = WAIT_MODES[tool_call.name]
            returned_message, is_error = result.render(), result.is_error
            self.pubsub.publish(
                "tool.finished",
                {
                    "call_id": tool_call.id,
                    "name": tool_call.name,
                    "is_error": is_error,
                    "status": result.status,
                    "result_chars": len(returned_message),
                    "duration_ms": round((time.monotonic() - started) * 1000),
                },
            )
            self.pubsub.publish("new_tool_message", returned_message)
            self.messages.append(
                Message(
                    id=None,
                    content=returned_message,
                    role="tool",
                    tool_call_id=tool_call.id,
                    tool_name=tool_call.name,
                    is_error=is_error,
                    tool_calls=None,
                )
            )
            self.log(returned_message)
        if wait_mode is not None and not self._stop_requested.is_set():
            self.wait_for(wait_mode)
        return True

    def percieve(self):
        """
        This is where the perception of the environment will be generated.
        """
        sections = [self.environment.get_environment()]
        for workspace in self.workspaces:
            view = workspace.build_view()
            if view:
                sections.append(f"## Workspace: {workspace.name}\n{view}")
        return "\n\n".join(section for section in sections if section)

    def remember(self):
        """
        This is where the memory of the agent will be queried.
        """
        return self.memory.get_memory()

    def build_prompt(self):
        perception = self.percieve()
        memory = self.remember()

        role = self.identity.current_role
        prompt = f"# Current Role:\n{role.name}\n{role.identity}\n" if role else ""

        if perception:
            prompt += f"# Environment:\n{perception}\n"

        if memory:
            prompt += f"# Memory:\n{memory}\n"

        self.pubsub.publish("new_agent_perception", prompt)

        return prompt

    def check_token_length(self):
        try:
            tokens = get_current_num_tokens(self.messages, self.llm.model_name)
            return tokens
        except Exception as e:
            self.error(f"Error getting token length: {e}")
            return 0
