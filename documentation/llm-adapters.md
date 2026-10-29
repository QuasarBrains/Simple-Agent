# LLM adapters and cost policies

The agent selects a provider at startup and keeps tool execution in `Toolbox`.
OpenAI uses Responses, Anthropic uses Messages, and Google uses native
Interactions through `google-genai`. History is application-owned; OpenAI and
Google requests explicitly disable server-side storage. Provider SDK retries are
disabled: each dispatched request has one accounting record, and an ambiguous
failure stops the agent rather than automatically repeating potentially billed work.
Confirmed output-limit truncation has a separate, bounded recovery policy below.

## Configuration

Copy `config.example.toml` to `config.toml`. This is the general application
configuration, with `[app]`, `[llm]` and `[memory]` sections. Credentials can live
in `[llm.providers.openai]`, `[llm.providers.anthropic]` or
`[llm.providers.google]` as `api_key`; `config.toml` is ignored by Git. **No `.env`
file is required.** Select another file with `--config path/to/config.toml` or
`CONFIG_FILE`. CLI `--llm`, `--verbose` and `--silence-actions` override file settings.

Setting precedence is explicit process environment > TOML > legacy `.env` >
defaults. In particular, a key/model already configured in TOML is not replaced
by an old `.env`. Provider generation options override individual settings from
`[llm.generation]`. Missing explicitly selected files are errors; if there is no
configuration file, defaults and legacy settings still work. Secrets are masked
in configuration representations and excluded from configuration error inputs.

Environment credentials are optional. Optional endpoint overrides are
`OPENAI_BASE_URL`, `ANTHROPIC_BASE_URL`, and `GEMINI_BASE_URL`, ahead of TOML
`base_url`. Custom endpoints must implement the selected native API.

Legacy `llm-config.toml`, `LLM_CONFIG` and `--llm-config` are accepted when moving
from the previous layout. Add the `llm.` prefix to its section/table names and
move `display_max_chars` into `[llm]` to adopt `config.toml`.

`MAX_TOKENS` only fills an absent `llm.generation.max_output_tokens`.
`MAX_MESSAGE_LENGTH` only fills an absent `llm.display_max_chars`. Display limits
never modify stored or replayed responses. The CLI shows one compact migration
hint instead of Python warnings. To move the previous limits into the new file:

```toml
[llm]
provider = "openai"
display_max_chars = 10000

[llm.generation]
max_output_tokens = 1024
```

Use your existing values, then remove the old variables from `.env`. Move other
settings and your API key into the corresponding example sections if you want
to retire `.env` entirely. Local-memory settings use `[memory]`, including the
embedding model; they share the OpenAI credential from `[llm.providers.openai]`.

## Monetary budgets

`llm.cost.request_budget`, `session_budget`, and `task_budget` are optional USD decimal
amounts. Zero means no spend is allowed, not unlimited. Unset means no cap at that
scope. Budgets are local estimates, not provider-enforced billing guarantees.

Set exact provider/model prices in `[[llm.pricing]]` tables. Rates are USD per million
tokens, with a source and effective date for auditing. There are deliberately no
embedded price assumptions: rates change, and negotiated/custom-endpoint prices
can differ. With no prices and no caps, usage is still recorded and cost is
explicitly unknown. With any cap, missing model pricing blocks dispatch.

For illustration only, a synthetic model price table looks like:

```toml
[[llm.pricing]]
provider = "openai"
model = "my-model"
input_per_million = "1.00"
output_per_million = "4.00"
cached_input_per_million = "0.25"
source = "operator-provided contract"
effective_date = "2026-10-28"
```

Use actual verified rates for your model. Snapshot-specific prices take precedence
over a configured requested-model alias price. Each record retains the pricing
snapshot used for reconciliation. This initial catalog supports flat text-token
rates; long-context tiers, priority/flex pricing, audio/image generation, hosted
provider tools, and external service charges require further accounting support.
Do not configure flat prices as if they covered those products. Local-memory
embedding calls are a separate subsystem and are **not included** in LLM budgets.

### Admission and reconciliation

Before dispatch, the full serialized provider request is estimated using UTF-8
bytes × `estimate_multiplier`, plus `estimate_overhead_tokens`. This includes
system instructions, tool schemas, calls/results, and native continuation data.
It intentionally overestimates ordinary text; opaque replay data may make it
particularly conservative. It is not an exact provider tokenizer. Optional
`generation.max_estimated_input_tokens` rejects oversized requests.

The tracker reserves estimated input cost plus the full allowed output cost,
assuming no cache savings and the highest configured input/cache-write rate.
It checks that reservation against each enabled budget. After a response it
reconciles with provider-reported usage, including cache categories and reasoning
without charging reasoning twice. The output token limit remains a per-request
generation safeguard, separate from the spend policy.

Actual spend can exceed an estimate. Subsequent requests then stop at admission.
Failed requests or missing/inconsistent usage retain their reservation with an
`unknown` status; any monetary cap prevents further requests until that uncertainty
is resolved. Unknown costs are never silently converted into zero spend. This
version does not provide a manual reconciliation interface or transport retries.

### Output-limit recovery

An output limit can cut a function call off midway through its JSON arguments,
particularly when a long answer is sent through `prompt_user`. The adapters inspect
the provider's completion status before attempting to parse those arguments.
An explicit OpenAI `incomplete_details.reason = max_output_tokens` or Anthropic
`stop_reason = max_tokens` can trigger regeneration of that inference step.

`llm.generation.max_output_retries` defaults to `1`; `0` disables recovery. Each
retry doubles the output allowance up to `max_retry_output_tokens` (default
`16384`). Every attempt is separately admitted against monetary budgets and
recorded in the ledger. The failed turn is not added to history and none of its
tool calls execute; regeneration uses the same previously completed history.
Previously executed tool turns are not re-executed. Timeouts, content filtering,
malformed calls in otherwise completed responses, and unexplained item-status
inconsistencies do not trigger these retries. Exhausted recovery reports the cap
and configuration setting instead of only saying "Incomplete function call".

## Logs and troubleshooting

`app.log_directory` defaults to `simple-agent-logs`. The CLI prints its resolved
path at startup. Logs append across launches; `--clear-logs` is the explicit opt-in
to truncate application log files. Existing flat files remain readable.

| File | Contents |
| --- | --- |
| `last_thread.md` | User/assistant conversation and perception snapshots, with session IDs. |
| `agent.log` | Conversation-history snapshots and tool results; verbose mode adds details. |
| `toolbox.log` | Executed tool arguments and successful return values. |
| `errors.log` | Persisted error messages, including why the agent stopped. |
| `general.log` | General application log events, when published. |
| `usage.jsonl` | One record per dispatched inference attempt: usage, cost, IDs, duration, outcome and completion diagnostics. |
| `events.jsonl` | Session boundaries, inference starts/completions/retries, tool starts/results, and errors. |

JSONL entries have a UTC timestamp and `session_id`. `request_group_id` groups
output-limit recovery attempts; `attempt` identifies each dispatch. The usage
record's `status` describes cost accounting (`reported` or `unknown`), while
`outcome` and `diagnostics.response_status` describe execution and provider state.

On an incomplete response, inspect `diagnostics.incomplete_details`, the output
allowance, actual output usage, and `diagnostics.output_items` (types, names, IDs,
statuses and argument lengths). Metadata diagnostics omit argument contents and
encrypted reasoning blobs. Full ordinary conversation/tool logs can contain file
contents returned by tools. Unexpected agent exceptions include a traceback in
`events.jsonl`. Correlate provider support requests with `request_id`/`response_id`.

Before this change, the generic error could hide the provider's reason and normal
startup truncated several logs. Old usage records may therefore establish that
the token limit was reached without retaining enough data to recover the lost
answer or prove the exact provider completion reason.

The terminal shows a running session total at each input prompt and while
thinking, without emitting a pricing line after each request. Tiny nonzero
amounts display as `<$0.0001` rather than rounding to zero. Without prices it
shows `Cost unavailable` with cumulative token/request counts; partial totals
are marked explicitly. The spinner and all conversation output share one Rich
console, and the transient spinner clears before assistant messages or input.

Session budgets reset when a new `LLM`/`CostTracker` is created (normally process
startup). The append-only `usage.jsonl` log includes session identity, request
records, usage, estimated/reported cost, and totals. It is an audit log, not a
persistent cross-restart budget ledger. `known_cost` excludes unknown records;
`committed_cost` includes retained reservations when estimates exist, and must be
read together with `unknown_requests`.

### Task attribution

A request is allocated to the single incomplete application task, if there is
exactly one at dispatch. With zero or multiple tasks, it belongs to `__shared__`.
Calls made through `get_text_response()` also use `__shared__`. A request can
create/complete several tasks, so this is accounting attribution rather than a
claim about each task's actual causal cost. No request is charged twice; session
totals remain authoritative. Direct integrations may pass an explicit `task_id`
to `LLM.get_response()`.

## Response and continuation contract

`Message` contains portable text, tool calls/results, finish status, usage and
identifiers, plus an ordered `native` payload. Native payloads contain provider
reasoning items/signatures and other blocks needed for faithful replay. They are
scoped to the requested provider/model; the resolved model is separate metadata.
Runtime provider/model switching is not implemented and foreign native data is
rejected. Do not trim or rewrite native history independently of its tool results.

All calls in a turn must receive results before another user/assistant turn.
The agent displays assistant text and executes calls from the same response.
Malformed/incomplete calls or blocked/incomplete responses stop before execution,
but reported usage is still accounted. Tool arguments are checked against the
registered JSON Schema, and execution failures become correlated error results.
Tools that return error text themselves retain their legacy string-result behavior.

`tool_choice = "auto"` is the default; the system prompt still directs the agent
to use tools. `required` is opt-in and rejected for known unsupported Claude models
or an explicitly disabled capability. Google does not expose a single-call
generation switch in Interactions; requesting it fails clearly. Reasoning effort
values vary by provider/model and are passed through only when configured.
OpenAI function schemas explicitly use non-strict mode to preserve existing
optional fields and open-ended dictionary arguments.

## Adding a provider

Implement the `Provider` protocol in `llms/llm.py`: build a complete request,
dispatch once, normalize usage, parse portable actions while preserving native
continuation, and close the client. Register it in `create_llm`, configuration and
CLI provider choices. Keep execution outside the SDK. Add fixtures for text-only,
mixed text/calls, multiple calls, empty/error results, continuation replay,
incomplete output, missing usage, and actual SDK request serialization.

Run offline checks with `uv run python -m unittest discover -s tests -v`.
Live provider smoke tests and pricing validation should be performed explicitly
with the intended model/account before deployment.

## Model and pricing maintenance

Before changing a model, verify its availability and supported tool/reasoning
settings against the provider's model lifecycle and API documentation. Add its
verified flat-text rates (including cache categories), source and effective date
to the local catalog. Recheck rates when the source changes; a model alias can
resolve to a newer snapshot. Use snapshot-specific catalog entries when prices
differ. Review SDK/API migration notes before updating `uv.lock`, regenerate the
pip export, run offline checks, and exercise a small text/tool continuation with
the intended account. Keep cross-restart budgets, tiered pricing, hosted-tool
charges and context compaction as explicit follow-up work rather than assuming
the current flat-text ledger covers them.
