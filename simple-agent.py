#!/usr/bin/env python3

import argparse
import os
import signal
from pathlib import Path
from threading import current_thread
from typing import Optional

from rich.text import Text

from agent.agent import Agent
from config import load_config
from llms.llm import create_llm
from memory.config import create_memory_service
from memory.service import MemoryService
from tools.index import Toolbox
from utils.cli_input import CLIInput
from utils.pubsub import PubSub
from utils.runlog import SessionLogger
from utils.terminal import console, terminal

verbose = False
silence_actions = False
log_directory = "simple-agent-logs"

# Get the directory of the current script
script_dir = os.path.dirname(os.path.abspath(__file__))

# Construct the absolute path to system_prompt.md
system_prompt_path = os.path.join(script_dir, "system_prompt.md")

SYSTEM_PROMPT = Path(system_prompt_path).read_text()

if not SYSTEM_PROMPT:
    console.print(
        "[red]Error:[/red] Could not find system prompt. Please ensure system_prompt.md exists."
    )
    exit(1)

LLM_CHOICES = ("openai", "anthropic", "google")

MEMORY_SERVICE: Optional[MemoryService] = None
RUN_LOGGER: Optional[SessionLogger] = None


agent: Optional[Agent] = None
PUBSUB = PubSub()
CLI_INPUT = CLIInput(
    waiting=lambda mode: agent is not None and agent.waiting_for == mode,
    on_close=lambda: agent.stop() if agent is not None else None,
)
TOOLBOX = Toolbox(pubsub=PUBSUB, approve=CLI_INPUT.approve)


def handle_errors():
    def report(message, kind):
        RUN_LOGGER.text("errors.log", str(message))
        RUN_LOGGER.event(kind, {"message": str(message)})
        console.print(Text.assemble(("Agent Error: ", "red"), str(message)))

    PUBSUB.subscribe("error", lambda error: report(error, "error"))
    PUBSUB.subscribe("agent_error", lambda error: report(error, "agent.error"))
    PUBSUB.subscribe(
        "agent_exception", lambda data: RUN_LOGGER.event("agent.exception", data)
    )


def write_to_file(file_path, log: str):
    RUN_LOGGER.text(Path(file_path).name, log)


def handle_logs():
    def agent_log(log: str):
        write_to_file(os.path.join(log_directory, "agent.log"), log)

    def general_log(log: str):
        write_to_file(os.path.join(log_directory, "general.log"), log)

    def toolbox_log(log: str):
        write_to_file(os.path.join(log_directory, "toolbox.log"), log)

    PUBSUB.subscribe("agent_log", agent_log)
    PUBSUB.subscribe("general_log", general_log)
    PUBSUB.subscribe("toolbox_log", toolbox_log)
    for name in (
        "tool.started",
        "tool.finished",
        "tool.approval",
        "agent.waiting",
        "agent.resumed",
    ):
        PUBSUB.subscribe(name, lambda data, event=name: RUN_LOGGER.event(event, data))


def on_user_input(user_input: str):
    if user_input.strip().lower() == "exit":
        console.print("[blue bold]Simon:[/blue bold] Goodbye!")
        PUBSUB.publish("exit_signal", "User exit")
        return
    write_to_file(os.path.join(log_directory, "last_thread.md"), f"User: {user_input}")
    PUBSUB.publish("new_user_message", user_input)


def on_new_agent_message(message: str):
    terminal.message(message)
    write_to_file(os.path.join(log_directory, "last_thread.md"), f"Agent: {message}")


def on_new_agent_message_with_prompt(message: str):
    on_new_agent_message(message)


def on_agent_waiting(data: dict):
    CLI_INPUT.submit_user(data["mode"])


def on_agent_resumed(data: dict):
    CLI_INPUT.cancel_user()


def on_new_agent_perception(perception: str):
    write_to_file(
        os.path.join(log_directory, "last_thread.md"), f"Perception:\n{perception}\n"
    )


def handle_exit(m: str):
    if agent is not None:
        agent.stop()
    CLI_INPUT.close()


def signal_handler(sig, frame):
    console.print("\nReceived exit signal, shutting down...")
    raise KeyboardInterrupt


PUBSUB.subscribe("new_agent_message", on_new_agent_message)
PUBSUB.subscribe("new_agent_prompt", on_new_agent_message_with_prompt)
PUBSUB.subscribe("new_agent_perception", on_new_agent_perception)
PUBSUB.subscribe("agent.waiting", on_agent_waiting)
PUBSUB.subscribe("agent.resumed", on_agent_resumed)
PUBSUB.subscribe("exit_signal", handle_exit)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the Simon chatbot.")
    parser.add_argument(
        "--llm", choices=LLM_CHOICES, help="Override the configured LLM provider."
    )
    parser.add_argument(
        "--verbose", action="store_true", default=None, help="Enable verbose logging."
    )
    parser.add_argument(
        "--silence-actions",
        action="store_true",
        default=None,
        help="Silence actions like function calls and task messages.",
    )
    parser.add_argument(
        "--clear-logs",
        action="store_true",
        help="Explicitly clear existing application logs before starting.",
    )
    parser.add_argument(
        "--config",
        help="Application config file (defaults to CONFIG_FILE or config.toml).",
    )
    parser.add_argument("--llm-config", help=argparse.SUPPRESS)
    args = parser.parse_args()

    try:
        config = load_config(args.config or args.llm_config)
        llm_choice = args.llm or config.llm.provider_name
        settings = config.llm.provider(llm_choice)
        if not settings.api_key or not settings.api_key.get_secret_value():
            parser.error(
                f"Set api_key in [llm.providers.{llm_choice}] in config.toml (or the provider's API-key environment variable)."
            )
        log_directory = str(Path(config.app.log_directory).expanduser())
        os.makedirs(log_directory, exist_ok=True)
        LLM = create_llm(llm_choice, config.llm)
        LLM.startup(SYSTEM_PROMPT)
        RUN_LOGGER = SessionLogger(
            log_directory, LLM.tracker.session_id, clear=args.clear_logs
        )
        RUN_LOGGER.event(
            "session.start",
            {
                "provider": llm_choice,
                "model": LLM.model_name,
                "generation": settings.generation.model_dump(),
            },
        )
    except Exception as error:
        parser.error(f"LLM configuration failed: {error}")

    def log_usage(event):
        RUN_LOGGER.json("usage.jsonl", event)
        RUN_LOGGER.event(
            "llm.response",
            {
                key: event[key]
                for key in (
                    "id",
                    "request_group_id",
                    "attempt",
                    "provider",
                    "model",
                    "outcome",
                    "response_id",
                    "request_id",
                    "duration_ms",
                    "diagnostics",
                    "error",
                )
            },
        )
        PUBSUB.publish("llm_usage", event)

    def log_llm_event(name, data):
        RUN_LOGGER.event(name, data)
        if name == "llm.retry":
            console.print(
                f"Output limit reached; retrying with {data['max_output_tokens']:,} tokens (subject to budget).",
                style="dim",
            )

    LLM.on_usage = log_usage
    LLM.on_event = log_llm_event
    handle_errors()
    handle_logs()
    terminal.tracker = LLM.tracker
    if config.legacy_settings:
        console.print(
            "Config  Legacy settings loaded; see config.example.toml to migrate to one file.",
            style="dim",
        )
    if (llm_choice, LLM.model_name) not in LLM.tracker.pricing:
        console.print(
            "Pricing  Add this model's rates in [[llm.pricing]] for dollar totals; token totals are available now.",
            style="dim",
        )

    try:
        recall_limit = config.memory.recall_limit
        memory_token_budget = config.memory.context_token_budget
        MEMORY_SERVICE = create_memory_service(config.memory_options())
        if MEMORY_SERVICE is not None:
            MEMORY_SERVICE.startup()
    except Exception as error:
        RUN_LOGGER.text("errors.log", f"Memory startup failed: {error}")
        RUN_LOGGER.event("startup.error", {"message": str(error)})
        if MEMORY_SERVICE is not None:
            MEMORY_SERVICE.close()
        LLM.close()
        parser.error(f"Memory configuration failed: {error}")

    verbose = config.app.verbose if args.verbose is None else args.verbose
    silence_actions = (
        config.app.silence_actions
        if args.silence_actions is None
        else args.silence_actions
    )

    console.print(
        Text.assemble(
            ("\nSimon  ", "bold blue"), (f"{llm_choice} / {LLM.model_name}", "dim")
        )
    )
    console.print(Text(f"Logs  {RUN_LOGGER.directory.resolve()}", style="dim"))

    agent = Agent(
        pubsub=PUBSUB,
        llm=LLM,
        toolbox=TOOLBOX,
        vector_store=None,
        verbose=verbose,
        silence_actions=silence_actions,
        memory_service=MEMORY_SERVICE,
        memory_recall_limit=recall_limit,
        memory_token_budget=memory_token_budget,
    )
    try:
        signal.signal(signal.SIGINT, signal_handler)
        agent.start()
        CLI_INPUT.submit_user("stimulus", initial=True)
        CLI_INPUT.run(lambda: agent.running, on_user_input)
    except (EOFError, KeyboardInterrupt):
        pass
    finally:
        agent.stop()
        CLI_INPUT.close()
        if agent.thread is not current_thread() and agent.thread.is_alive():
            agent.thread.join()
        if MEMORY_SERVICE is not None:
            MEMORY_SERVICE.close()
        RUN_LOGGER.event("session.end", {"summary": LLM.tracker.summary()})
        LLM.close()
    console.print("Shutting down...")
