#!/usr/bin/env python3

import argparse
import os
import signal
import threading
import time
from typing import Optional

from dotenv import load_dotenv
from rich.console import Console
from rich.markdown import Markdown

from agent.agent import Agent
from llms.google import GoogleLLM
from llms.openai import OpenAILLM
from llms.anthropic import AnthropicLLM
from memory.simple_vector_store import SVSVectorStore
from memory.vector_store import VectorStore
from tools.index import Toolbox
from utils.pubsub import PubSub

load_dotenv()

console = Console()

llm_choice = os.environ.get(
    "MODEL_CHOICE", "openai"
)  # This will be modifiable in the future
vector_store_choice = os.environ.get("VECTOR_STORE_CHOICE", "none")
verbose = False
silence_actions = False
log_directory = os.environ.get("LOG_DIRECTORY", "simple-agent-logs")
os.makedirs(log_directory, exist_ok=True)  # Ensure the log directory exists

# Get the directory of the current script
script_dir = os.path.dirname(os.path.abspath(__file__))

# Construct the absolute path to system_prompt.md
system_prompt_path = os.path.join(script_dir, "system_prompt.md")

SYSTEM_PROMPT = open(system_prompt_path).read()

if not SYSTEM_PROMPT:
    console.print(
        "[red]Error:[/red] Could not find system prompt. Please ensure system_prompt.md exists."
    )
    exit(1)

LLM_CHOICE_MAP = {
    "openai": OpenAILLM,
    "anthropic": AnthropicLLM,
    "google": GoogleLLM,
}
LLM = LLM_CHOICE_MAP.get(llm_choice, OpenAILLM)

VECTOR_STORE_CHOICE_MAP: dict[str, Optional[VectorStore]] = {
    "simple_vector_store": SVSVectorStore,
    "none": None,
}
VECTOR_STORE: Optional[VectorStore] = VECTOR_STORE_CHOICE_MAP.get(
    vector_store_choice, None
)


PUBSUB = PubSub()
TOOLBOX = Toolbox(pubsub=PUBSUB)

log_lock = threading.Lock()  # For thread-safe log file operations


def clear_logs():
    with open(os.path.join(log_directory, "agent.log"), "w") as f:
        f.write("")
    with open(os.path.join(log_directory, "toolbox.log"), "w") as f:
        f.write("")


def clear_threads():
    with open(os.path.join(log_directory, "last_thread.md"), "w") as f:
        f.write("")


def handle_errors():
    PUBSUB.subscribe("error", lambda error: console.print(f"[red]Error:[/red] {error}"))
    PUBSUB.subscribe(
        "agent_error", lambda error: console.print(f"[red]Agent Error:[/red] {error}")
    )


def write_to_file(file_path, log: str):
    with log_lock:  # Ensure only one thread writes to a file at a time
        with open(file_path, "a") as f:
            current_timestring = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            f.write(f"**{current_timestring}**: {log}\n")


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


prompting_user = False


def prompt_user():
    user_input = console.input("[cyan bold]You:[/cyan bold] ")
    if user_input.lower() == "exit":
        console.print("[blue bold]Simmy:[/blue bold] Goodbye!")
        PUBSUB.publish("exit_signal", "User exit")
    write_to_file(os.path.join(log_directory, "last_thread.md"), f"User: {user_input}")
    PUBSUB.publish("new_user_message", user_input)


def on_new_agent_message(message: str):
    console.print("[blue bold]Simmy:[/blue bold]")
    console.print(Markdown(message))
    write_to_file(os.path.join(log_directory, "last_thread.md"), f"Agent: {message}")


def on_new_agent_message_with_prompt(message: str):
    console.print("[blue bold]Simmy:[/blue bold]")
    console.print(Markdown(message))
    write_to_file(os.path.join(log_directory, "last_thread.md"), f"Agent: {message}")
    prompt_user()


def on_new_agent_perception(perception: str):
    write_to_file(
        os.path.join(log_directory, "last_thread.md"), f"Perception:\n{perception}\n"
    )


def handle_exit(m: str):
    console.print("Shutting down agent...")
    agent.stop()
    console.print("Agent stopped. Exiting now.")
    exit(0)


def signal_handler(sig, frame):
    console.print("\nReceived exit signal, shutting down...")
    PUBSUB.publish("exit_signal", "Signal exit")


PUBSUB.subscribe("new_agent_message", on_new_agent_message)
PUBSUB.subscribe("new_agent_prompt", on_new_agent_message_with_prompt)
PUBSUB.subscribe("new_agent_perception", on_new_agent_perception)
PUBSUB.subscribe("exit_signal", handle_exit)

if __name__ == "__main__":
    if not LLM:
        console.print("[red]Error:[/red] Invalid LLM choice.")
        exit(1)
    LLM.startup(SYSTEM_PROMPT)

    if VECTOR_STORE is not None:
        VECTOR_STORE.startup()

    parser = argparse.ArgumentParser(description="Run the Simmy chatbot.")
    parser.add_argument("--llm", type=str, default="openai", help="The LLM to use.")
    parser.add_argument(
        "--verbose", action="store_true", help="Enable verbose logging."
    )
    parser.add_argument(
        "--silence-actions",
        action="store_true",
        help="Silence actions like function calls and task messages.",
    )
    parser.add_argument("--clear-logs", action="store_true", help="Clear the logs.")
    args = parser.parse_args()

    llm_choice = args.llm
    verbose = args.verbose
    silence_actions = args.silence_actions

    clear_logs()

    clear_threads()

    console.print("[blue bold]Simmy:[/blue bold] Hello and welcome! My name is Simmy!")

    # Start handling errors and logs in separate threads
    error_thread = threading.Thread(target=handle_errors)
    error_thread.start()

    log_thread = threading.Thread(target=handle_logs)
    log_thread.start()

    # Create and start the agent
    agent = Agent(
        pubsub=PUBSUB,
        llm=LLM,
        toolbox=TOOLBOX,
        vector_store=VECTOR_STORE,
        verbose=verbose,
        silence_actions=silence_actions,
    )
    agent.start()

    # Set up the signal handler for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)

    # Start the interaction loop
    prompt_user()

    # Wait for the agent thread to finish before exiting
    agent.thread.join()
    console.print("Shutting down...")
