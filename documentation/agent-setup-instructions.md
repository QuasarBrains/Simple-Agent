# Agent setup instructions

Give these instructions to a coding agent with terminal and repository access to configure a fresh Simple Agent instance. The agent can install dependencies, prepare configuration, and run offline checks. A human supplies secrets and authorizes any live API test.

## Goal and boundaries

Prepare an instance that a human can start with:

```sh
uv run python simple-agent.py
```

- Never request, generate, display, or commit API keys. Do not ask a human to paste secrets into the conversation.
- Preserve existing work, virtual environments, and configuration. Do not overwrite an existing `.env` or revert unrelated changes.
- Do not read files marked private by the editor or bypass restrictions with another tool. If `.env.example` or `.env` is inaccessible, ask the human to perform the configuration steps below locally.
- Do not launch the agent, contact an LLM, or exercise its tools without explicit human authorization. Live requests can incur charges, and the application can execute commands and modify files.
- Do not commit or push changes unless asked.

## 1. Locate or clone the repository

If the repository is already available, use it rather than cloning another copy. Inspect the working tree before making changes:

```sh
git --no-optional-locks status --short
```

For a new checkout, clone into the human's chosen workspace:

```sh
git clone https://github.com/AidanTilgner/Simple-Agent.git
cd Simple-Agent
```

Run the remaining commands from the repository root. When using an agent terminal tool with a working-directory argument, set that argument instead of embedding `cd` in a command.

## 2. Install or locate uv

```sh
uv --version
```

If uv is missing, follow the official installation instructions:

https://docs.astral.sh/uv/getting-started/installation/

Use the installation method appropriate to the host and its permissions. Do not silently use administrative privileges or install globally. Request approval for any necessary network or filesystem access. After installation, locate the executable; a new shell or an explicit executable path may be needed.

No separate Python installation is required in the normal uv workflow. `.python-version` selects Python 3.12, and uv can download it automatically.

## 3. Install the locked environment

```sh
uv sync --locked
```

This creates `.venv` and installs the committed dependency resolution, including development tools. No virtual environment activation is needed.

- `pyproject.toml` declares dependencies; `uv.lock` records the resolution.
- Do not upgrade packages or regenerate the lockfile just to set up an instance.
- `requirements.txt` is a generated pip compatibility export, not the source of truth for this workflow.
- An existing `venv/` belongs to the older workflow. Leave it alone. If uv warns about a mismatched active environment, deactivate it or use a fresh shell; do not add `--active` to target the old environment.
- If `--locked` reports that the lockfile is stale, report the mismatch rather than silently resolving new versions.

Installation needs access to Python package indexes and may need Python download hosts. In a sandbox, request the relevant permissions rather than disabling security controls globally. If the sandbox blocks uv's cache or managed-Python directories, use tool-approved writable locations or request narrowly scoped access; do not commit machine-specific paths.

## 4. Prepare the application configuration

Check whether `config.toml` already exists without printing its contents (it can
contain API keys). Preserve existing configuration. For a new setup:

```sh
cp -n config.example.toml config.toml
```

If private-file restrictions block this operation, ask the human to run it locally. Do not bypass those restrictions.

Ask which provider and model the human wants. Set `[llm] provider` and the matching
`[llm.providers.<provider>] model`. The human fills in `api_key` in that section.
Application, memory, generation, budgets and pricing all live in this same file.
No `.env` file is required. Legacy environment-variable names remain available:

| Provider | `MODEL_CHOICE` | Model variable | Secret for the human to fill in |
| --- | --- | --- | --- |
| OpenAI | `openai` | `OPENAI_MODEL` | `OPENAI_API_KEY` |
| Anthropic | `anthropic` | `ANTHROPIC_MODEL` | `ANTHROPIC_API_KEY` |
| Google Gemini | `google` | `GEMINI_MODEL` | `GEMINI_API_KEY` |

Use a model identifier the human supplies or verifies is available to their account. Model availability changes; do not assume the application's historical defaults still exist. Only the chosen provider needs credentials.

For a minimal instance:

```toml
[llm]
provider = "openai"

[llm.providers.openai]
model = "YOUR_CHOSEN_MODEL"
api_key = "" # Human fills this in locally

[memory]
backend = "none"
```

This block illustrates settings to edit in the example, not a replacement for an
existing file. Replace `YOUR_CHOSEN_MODEL` before use. Preserve unrelated settings.

Configure verified model prices in `[[llm.pricing]]` before enabling monetary caps. See
[LLM cost policies](llm-adapters.md) for budgets, usage accounting, and model options.

Do not set up a vector store for the basic smoke test. Persistent memory requires a separately configured service; see [Adding memory](adding-memory.md). Chrome is needed only for Selenium browser tools, not basic conversation.

## 5. Run checks without credentials or LLM calls

```sh
uv run --locked python simple-agent.py --help
uv run --locked python -m unittest discover -s tests -v
uv pip check --python .venv/bin/python
```

These checks do not intentionally contact an LLM or require API keys. The application help path does load local configuration and may create the configured log directory, but it does not initialize a provider client or start the agent loop. Initial dependency synchronization may require network access.

Expected results:

- Help lists the supported provider choices and CLI options.
- Automated tests pass.
- The installed environment has no incompatible requirements.

Do not treat these checks as proof that credentials, model access, or live tool calls work.

## 6. Hand off secrets to the human

Tell the human to open `config.toml` locally and fill in the selected provider's
`api_key`. Do not inspect or echo the result. Ensure the file is ignored by Git:

```sh
git check-ignore config.toml
```

Report what was configured, which checks passed, and what remains for the human. Do not include secret values or dump the configuration file.

The instance can now be started with:

```sh
uv run python simple-agent.py
```

For an explicit provider override:

```sh
uv run python simple-agent.py --llm openai
```

`--llm` overrides `MODEL_CHOICE`; it does not replace the corresponding API key or model settings.

## 7. Optional authorized live smoke test

Only proceed after the human confirms that credentials are configured and authorizes a real API request. Explain that requests may incur charges and send the test prompt and application context to the selected provider.

1. Start the agent in an interactive terminal, or use a bounded subprocess with controlled input and a timeout.
2. Send a harmless prompt such as: “Hello! Please confirm you can read this message. Do not use filesystem, shell, browser, or research tools.”
3. Confirm that a model-generated reply appears. The initial welcome banner alone is not evidence of a successful API call.
4. Send `exit` when the agent requests input, or use `Ctrl+C` if needed.
5. Confirm shutdown and report the result. Do not leave an agent running in the background.

Do not run an indefinite interactive session through a terminal tool that requires commands to terminate. Apply an explicit timeout and clean up the child process if it stalls.

### Known OpenAI compatibility behavior

The current adapter uses Chat Completions and passes `MAX_TOKENS` as `max_completion_tokens`. For the exact model identifier `gpt-6-luna`, it additionally sends `reasoning_effort="none"` because its tool calls require that setting on this endpoint. This does not guarantee that identifier is available to every account. Other model or endpoint incompatibilities should be reported with a sanitized error, not worked around by silently selecting another model or upgrading dependencies.

## Completion report

A useful final handoff includes:

- Repository location and selected Python version.
- Whether locked dependency installation succeeded.
- Chosen provider and model, without credentials.
- Whether `.env` was created, preserved, or left for the human due to access restrictions.
- Offline validation results and any blockers.
- Whether a live test was authorized and completed.
- The exact command to start the instance.
