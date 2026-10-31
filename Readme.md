# Simple Agent

> [!warning]
> Simple agent can run commands on your machine. Be aware of the potential for it to make modifications to your system.

![Aug-16-2024 11-27-09](https://github.com/user-attachments/assets/3bb43a56-0501-4759-b3b0-ac459f53f692)

> [!note]
> Simple Agent is still a work in progress! There will likely be bugs and missing features, if you encounter them, please leave an issue!

This is an attempt to make a bare-bones, very simple agent based on LLMs and other technologies. The goal is to have a simple agent for use in various purposes:

1. Experimentation and benchmarking
2. Understanding and learning myself
3. Idk but having three points sounds more solid

## How it works

So put simply, the agent works on a constant loop, involving three main steps:

1. Perception
2. Inference
3. Action

The perception stage combines environmental analysis, session-local workspace views (tasks and a notepad), and memory recall. The inference stage is the call to the model API, where the model is given the perception to reason about. The action stage is where the agent takes the output of the model, such as tool calls, and actually runs them.

## Prerequisites

To make Simple Agent work well, you'll need to meet the following prerequisites:

- [uv](https://docs.astral.sh/uv/getting-started/installation/) (follow the official installation instructions)
- Access to an LLM provider: OpenAI, Anthropic, or Google Gemini
- Google Chrome only if you want to use the Selenium browser tools

Python 3.12 is automatically downloaded as needed and managed by uv using the project's `.python-version` file; no separate Python installation or virtual environment activation is needed. The Wikipedia tool uses Wikipedia-API (`wikipedia-api==0.6.9`) directly.

## How to use it

Use uv to install dependencies and run the agent. It manages Python 3.12 and the project's virtual environment automatically.

1. Start by cloning the repository (or forking if you want to extend it a lot):

```bash
   git clone https://github.com/AidanTilgner/Simple-Agent.git
```

2. Then, navigate into the directory:

```bash
cd Simple-Agent
```

3. Install the dependencies:

```bash
uv sync
```

Use `uv sync --locked` instead to require the exact committed lockfile without updating it; this fails if the lockfile is out of date.

4. Copy `config.example.toml` to `config.toml` and configure your chosen provider.

(on MacOS or Linux):

```bash
cp config.example.toml config.toml
```

Set `provider` in `[llm]` to `openai`, `anthropic`, or `google`, then fill in
`api_key` and `model` in its `[llm.providers.<provider>]` section.

`config.toml` holds application settings, provider credentials, generation options,
budgets/pricing, and memory settings. It is ignored by Git. **You do not need a
`.env` file.** Existing `.env` setups still work as fallbacks; explicit process
environment variables can override the configuration for deployments.

A vector store is optional; leave `[memory] backend = "none"` to run without one. Chrome is needed only for Selenium browser tools, not for running the agent itself.

Configure generation settings, per-request/task/session USD budgets, and your
model pricing catalog under `[llm]` in the same file. Monetary
caps require configured prices; without them the agent records token usage and
reports cost as unknown. See [LLM adapters and cost policies](documentation/llm-adapters.md)
for accounting behavior and migration from `MAX_TOKENS` / `MAX_MESSAGE_LENGTH`.

5. Run the program (no environment activation needed):

```bash
uv run python simple-agent.py
```

6. To exit the program, you can use `Ctrl+C`, or type "exit".

That's it! You should see the agent start up, and you can ask it to do things using it's tools.

Select a different file with `--config path/to/config.toml`. After syncing
dependencies, `uv run --no-sync python simple-agent.py` skips uv's environment
reconciliation on subsequent launches. This also avoids repeated reinstall noise
from the current `sqlite-vss` wheel metadata mismatch.

### Managing dependencies with uv

Add a runtime dependency with `uv add <package>`, or a development dependency with `uv add --dev <package>`.

Dependency upgrades are intentional, not automatic: run `uv lock --upgrade` to upgrade within the constraints in `pyproject.toml`, then `uv sync` to install them. Provider SDKs use compatible-major version ranges; other direct dependencies may use exact pins. Use `uv add 'package==new-version'` to change a pin. Review the lockfile changes before committing them.

`pyproject.toml` and `uv.lock` are the source of truth. `requirements.txt` is a generated compatibility export for pip users; regenerate it after dependency changes with:

```bash
uv export --locked --no-dev --no-hashes --no-emit-project --output-file requirements.txt
```

Run the automated checks without API credentials or network access:

```bash
uv run python -m unittest discover -s tests -v
```

## Advanced Usage

### Logs

The CLI prints the logging directory at startup (default `simple-agent-logs/`).
`last_thread.md` contains the conversation, `toolbox.log` records tool arguments
and results, `agent.log` contains history snapshots, and `errors.log` records
failures. `usage.jsonl` records every inference attempt and `events.jsonl` traces
requests, output-limit retries, tools, and errors using session/request IDs.
Logs append across launches; use `--clear-logs` only when you want to clear them.
See [logging and troubleshooting](documentation/llm-adapters.md#logs-and-troubleshooting)
for completion diagnostics and bounded output-limit recovery settings.

You might want to extend or enhance the functionality of the tool, and if you do I'd love to hear how it goes! Or even submit a PR if you think it should be a default.

**Modifying Prompts**
You can modify prompts in `agent/agent.py`, `agent/memory.py`, `agent/environment.py`, and the workspace modules under `agent/workspaces/`. See the [workspace interface](agent/workspaces/workspaces.md) for session-local tools and views. These files are where you'll find the actual programmatic generation logic for several aspects of the prompt. Things might change over time, so I'm not going to go into specifics here. But you might find that you can gain further behavior by modifying these files.

The `system_prompt.md` file is the source of the agent's system prompt, which can be modified as well.

**Using Different Models**
The provider adapters in `llms/` support OpenAI, Anthropic and Google Gemini.
Set `[llm] provider` and the matching `[llm.providers.<provider>]` key/model in
`config.toml`; `--llm` overrides provider selection for one run. Provider choice
currently applies at startup.

**Adding Tools**
Tools are discrete functions composed into capability libraries under `tools/libraries/`: `fs`, `search`, `web`, `python`, and `shell`. Canonical names such as `fs.read` are mapped to provider-safe names at the adapter boundary. Tools return structured success, error, denial, or timeout results. See the [tooling inventory and execution policies](documentation/tooling.md) and [Adding a tool](documentation/adding-a-tool.md).

Host shell commands require an **Approve once / Deny** selection for every invocation; approval is not sandboxing. Stateless Python uses a deny-default macOS OS sandbox and fails closed on unsupported hosts. The default web tools retrieve readable content without Chrome or JavaScript; browser automation is deferred.

The shared interaction tools distinguish progress (`interaction.notify`), a question requiring a reply (`interaction.ask`), and a completed turn (`interaction.finish`). Finished turns return to the `You` prompt without requiring an answer; questions show `Reply`. Text-only answers also finish automatically. Waiting pauses unfinished tasks until the appropriate new stimulus arrives. See [interaction and waiting](documentation/tooling.md#interaction-and-waiting).

## Roles

Roles are identities which can be adopted by the agent. They are are context-dependent, and each have their own set of tools which are provided to the agent. The agent can switch between roles at any time. `ROLES_INCLUDED` are defined in the `roles/config.py` file. You can learn more about roles in the [roles tutorial](/documentation/adding-a-role.md).

I'm still working on the roles system, bare with me. But you can see the beginnings of it in the `roles/` directory. Currently these roles are supported:

- `Helpful Assistant`: Conversational assistance with filesystem, search, web retrieval, and isolated Python tools.
- `Developer`: Project inspection, precise editing, verification, and approval-gated host shell execution, plus the shared capability libraries.
- `Researcher`: Source discovery, retrieval, comparison, citations, artifact creation, and isolated calculations.

Roles focus working practices rather than enforcing permissions, and the agent can switch freely. The system prompt includes each role's tool inventory; the current role is supplied on every iteration. Shared task, messaging, role-switching, and configured memory tools remain available across modes.

> [!note]
> To switch between roles, just ask the agent to do it. For example, you can say "I'd like some help with research...", or more specifically "I'd like to switch to the researcher role." You'll see a "Role [ROLE]" message to confirm.

## Adding Memory

Check out [the tutorial](/documentation/adding-memory.md) to learn how to add memory to Simple Agent. This isn't necessary for the agent to work, however allows its memory to persist between sessions.

Built-in memory runs in-process using the shared application SQLite database and OpenAI embeddings. Set `MEMORY_BACKEND=local` and `OPENAI_API_KEY` in `.env` to enable it. Embedding providers are independent of chat models, and custom memory services implement the same interface as the built-in service. Existing Simple Vector Store configurations remain supported.

## Roadmap

I'm looking to polish this project into a really solid framework for building agents. But it's going to need to stay as a core, rather than a full-fledged agent. To make a full-fledged agent, this should be forked. In it's current state, it's usable and functional, and extensible.

## Features

**Existing Features**

- [x] Implement memory and learning through [Simple Vector Store](https://github.com/AidanTilgner/Simple-Vector-Store)
- [x] Built-in SQLite memory with independent embedding adapters and a standard memory service interface
- [x] Allow selection of additional models
- [x] Get better editing
- [x] "Modes" that the agent can switch into for specialized operations, with different tool layouts

**WIP (kinda) Features**
These are things that I currently plan on doing or hope to do. If you have ideas for features or feadback, don't hesitate to open an issue so we can discuss it.

- [ ] Memory import/export and embedding-model migration utilities ([plan](discussions/built-in-memory.md))
- [ ] A more robust benchmarking system through [Benchy](https://github.com/AidanTilgner/Benchy)
- [ ] A type of procedural memory
- [ ] A sort of plugin system
