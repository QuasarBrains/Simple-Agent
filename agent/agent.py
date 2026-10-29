import json
import threading
import time
import traceback
from typing import List, Optional

from agent.agency import Agency
from agent.environment import Environment
from agent.memory import MemoryEngine
from llms.llm import LLM, LLMError, Message
from llms.costs import BudgetExceeded, PricingUnavailable
from memory.vector_store import VectorStore
from memory.service import MemoryService
from tools.index import Toolbox
from tools.libraries.core.send_message_to_user import send_message_to_user, prompt_user
from utils.pubsub import PubSub
from utils.tokens import get_current_num_tokens
from utils.terminal import console, terminal
from roles.identity import IdentityManager


class Agent:
    pubsub: PubSub
    messages: List[Message] = []
    toolbox: Toolbox
    llm: LLM
    environment: Environment
    memory: MemoryEngine
    identity: IdentityManager
    vector_store: Optional[VectorStore]
    agency: Agency
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
        self.agency = Agency(pubsub=pubsub, llm=llm, silence_actions=silence_actions)
        self.vector_store = vector_store
        self.thread = threading.Thread(target=self.run)
        self.identity = IdentityManager(pubsub=pubsub, toolbox=self.toolbox)

        self.initialize_default_tools()

    def initialize_default_tools(self):
        self.toolbox.register_tool(send_message_to_user)
        self.toolbox.register_tool(prompt_user)

        self.toolbox.register_tool(self.agency.create_task_tool())
        self.toolbox.register_tool(self.agency.complete_task_tool())
        self.toolbox.register_tool(self.agency.modify_task_notes_tool())
        self.toolbox.register_tool(self.agency.modify_task_requirements_tool())
        self.toolbox.register_tool(self.identity.set_role_tool())

        if self.memory.is_setup():
            self.toolbox.register_tool(self.memory.add_memory_tool())

        self.identity.add_roles_to_system_prompt(llm=self.llm)

    def start(self):
        self.running = True
        self.thread.start()

    def stop(self):
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
        if self.agency.has_incomplete_tasks():
            self.awake = True
        else:
            self.awake = False

        if self.environment.new_stimuli():
            self.awake = True

        return self.awake

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
            tasks = self.agency.get_incomplete_tasks()
            task_id = tasks[0].id if len(tasks) == 1 else "__shared__"
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

        if message.content:
            content = message.content
            limit = self.llm.config.display_max_chars
            if limit and len(content) > limit:
                content = content[:limit] + "...[TRUNCATED FOR DISPLAY]"
            self.send_message(content)

        if not message.tool_calls:
            if message.content:
                return True
            return self.error("No tool calls or message provided.")

        for tool_call in message.tool_calls:
            if self.verbose:
                self.log(
                    f"Running {tool_call.name} with arguments: {tool_call.arguments}"
                )
            if not self.silence_actions and (
                self.verbose
                or tool_call.name not in {"prompt_user", "send_message_to_user"}
            ):
                console.print(f"  ↳ {tool_call.name}", style="dim", markup=False)

            self.pubsub.publish(
                "tool.started", {"call_id": tool_call.id, "name": tool_call.name}
            )
            started = time.monotonic()
            returned_message, is_error = self.toolbox.execute(tool_call)
            self.pubsub.publish(
                "tool.finished",
                {
                    "call_id": tool_call.id,
                    "name": tool_call.name,
                    "is_error": is_error,
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
        return True

    def percieve(self):
        """
        This is where the perception of the environment will be generated.
        """
        return self.environment.get_environment()

    def remember(self):
        """
        This is where the memory of the agent will be queried.
        """
        return self.memory.get_memory()

    def get_agency(self):
        """
        This is where the goal of the agent will be formed based on user queries.
        """
        agency = self.agency.get_incomplete_tasks_described()
        return agency

    def build_prompt(self):
        perception = self.percieve()
        memory = self.remember()
        agency = self.get_agency()

        prompt = ""

        if perception:
            prompt += f"# Environment:\n{perception}\n"

        if memory:
            prompt += f"# Memory:\n{memory}\n"

        if agency:
            prompt += f"# Agency:\n{agency}\n"

        self.pubsub.publish("new_agent_perception", prompt)

        return prompt

    def check_token_length(self):
        try:
            tokens = get_current_num_tokens(self.messages, self.llm.model_name)
            return tokens
        except Exception as e:
            self.error(f"Error getting token length: {e}")
            return 0
