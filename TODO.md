# LLM Adapter Modernization

## Implementation status

Implemented the native adapters, instance-owned factory, lossless continuation,
mixed text/tool execution, TOML policy, and session-local USD budget accounting.
Configuration and limitations: [LLM adapters and cost policies](documentation/llm-adapters.md).
Pricing is operator-configured; no live rates are assumed. Budgets reset with a
new tracker/process, and embedding/external-service costs are outside this scope.
Temporary regression tests are used during implementation and removed afterward
at the user's request.

Verification completed: 25 temporary LLM regression tests passed, covering all
three real SDK serializers through mocked HTTP transports, native replay, mixed
responses, usage/cache/reasoning accounting, concurrent admission, missing pricing
and usage, malformed/incomplete calls, and agent budget-stop behavior. The
temporary test file was then removed. No paid/live inference requests were made.
Lint and `git diff --check` passed. `uv pip check` reported that the installed
`sqlite-vss` package was built for a different platform (memory dependency).

## General configuration and terminal cleanup

- [x] Replace the LLM-only example with `config.example.toml`, covering `[app]`, `[llm]` and `[memory]`.
- [x] Allow provider credentials in the ignored local `config.toml`, so `.env` is optional rather than required.
- [x] Keep explicit process environment overrides and legacy `.env` fallbacks; retain old policy-file compatibility.
- [x] Replace legacy-limit Python warnings with one concise CLI migration hint, preserving existing values.
- [x] Share a Rich console across conversation, roles, tools and loading status.
- [x] Show a running session total at prompts/while thinking, and show tokens instead of a misleading zero-dollar figure when pricing is missing.
- [x] Hide routine communication-tool labels and simplify role/message spacing.
- [x] Verify configuration precedence, credential handling, one-file CLI startup without `.env`, and real-terminal spinner animation with 12 temporary tests; all passed, then the test file was removed.

## Incomplete function-call investigation and logging

- [x] Inspect the actual failing session: the last request produced exactly 1,024 output tokens against a 1,024-token allowance, with zero reasoning tokens. The prior logger lost the provider's completion reason, so output truncation is strongly indicated rather than independently confirmed from saved status metadata.
- [x] Check provider completion status before parsing possibly truncated tool arguments; retain actionable failure details.
- [x] Add bounded output-limit regeneration (default one retry, doubling the allowance up to a ceiling), with separate budget admission/accounting per attempt and no partial tool execution.
- [x] Keep transport errors, content-filter interruptions and unexplained incomplete items out of automatic recovery.
- [x] Persist session/request/retry/tool/error events and completion metadata, with request groups, attempt numbers, UTC timestamps and durations.
- [x] Preserve logs across normal launches; make `--clear-logs` the explicit opt-in to clearing application log files.
- [x] Remove duplicated tool-result bodies from perception prompts while retaining structured tool history and memory's peek context.
- [x] Verify recovery, budget rejection, non-retryable failures, log preservation and error persistence with 11 temporary tests; all passed, then the test file was removed.

## Direction

- Preserve the small, provider-independent adapter interface and application-owned tool execution.
- Keep provider selection at startup for now; runtime provider/model switching is deferred.
- Support text and tool calls in the same assistant turn.
- Retain provider-native continuation data losslessly, scoped to its originating provider/model.
- Use configurable cost policies rather than treating output-token and message-character limits as cost control.

## Shared adapter contract

- [x] Define canonical request, response, message, tool-call, and tool-result contracts.
- [x] Preserve ordered content and native continuation payloads required for multi-turn reasoning and tool use.
- [x] Return normalized finish status, original provider status, resolved model, response/request IDs where exposed by the SDK, and usage metadata.
- [x] Distinguish tool-call correlation IDs from provider response/item IDs.
- [ ] Expand the initial tool-choice/multiple-call capability flags into a model-specific reasoning/schema support matrix.
- [x] Separate agent tool-use policy from text-only requests; never require tools when none are supplied.
- [x] Replace module-global clients/models and singleton configuration with instance-owned configuration and provider factories.
- [x] Define client initialization, cleanup, timeouts, retries, and normalized errors. SDK/transport retries are disabled; confirmed output-limit truncation has separately budgeted, bounded recovery.
- [x] Ensure the reported model matches the configured/resolved model.

## Agent integration

- [x] Process assistant text and tool calls in the same turn without skipping tool execution.
- [x] Preserve empty tool results and correlate every result with its call.
- [x] Represent thrown tool execution failures and validation errors explicitly. Legacy tools returning error strings retain their existing behavior.
- [x] Prevent execution of incomplete or invalid tool calls.
- [x] Separate allowing multiple generated calls from executing tools concurrently; retain sequential execution initially.
- [x] Keep display truncation separate from stored/replayed conversation history.
- [ ] Review context growth and compaction while preserving complete tool-call/result exchanges and native continuation requirements.

## Configurable cost control

### Policy and configuration

- [x] Design typed TOML application/cost configuration with documented defaults and precedence; support credentials in the ignored local file and optional environment overrides.
- [x] Define configurable monetary budgets per request, task, and session, with explicit currency and budget scope. Allow scopes to be disabled when not needed.
- [x] Define task attribution for requests: one active task receives the allocation; zero/multiple tasks use `__shared__`. Session accounting remains authoritative without double-counting.
- [x] Define budget-exhaustion behavior: stop before another unaffordable request and report the reason plus recorded usage/spend.
- [x] Define behavior when pricing or usage is unavailable; never silently treat unknown cost as zero.
- [x] Retain model-specific output/reasoning settings as request safeguards, independently of monetary budgets.
- [x] Separate presentation limits, estimated-input rejection and provider generation limits; document replacements for `MAX_TOKENS` and `MAX_MESSAGE_LENGTH`.
- [ ] Add configurable tool-result shaping and context compaction without corrupting replay history.

### Pricing and accounting

- [x] Introduce an operator-maintained provider/model pricing catalog with USD currency, source, effective date, units, and explicit rates for custom endpoints or negotiated pricing.
- [x] Account for flat text input/output, cached-input/cache-write and reasoning without double-counting usage categories.
- [ ] Extend accounting to tiered/service-class pricing, provider-hosted tools, embeddings and external service charges before including them in monetary budgets.
- [x] Define a clear initial accounting scope for flat text-model API costs; identify embeddings and external tool/service charges separately.
- [x] Normalize actual usage across Anthropic, Google, and OpenAI while retaining raw provider usage for reconciliation.
- [x] Track estimated versus reported usage and estimated monetary cost separately; distinguish local accounting from provider billing totals.
- [x] Record spend per dispatched attempt and aggregate it into task/session totals, retaining reservations on ambiguous failures. Output-limit retries are separately admitted and billed.
- [x] Use process/tracker-local budgets with unique session IDs and append-only JSONL audit logs.
- [x] Expose concise usage/budget summaries through the existing logging/event system.

### Request admission and context management

- [x] Estimate full request cost before dispatch, including system instructions, history, tool schemas/results, native replay data, and the allowed output/reasoning budget.
- [x] Reserve conservatively estimated spend before dispatch and reconcile after the response; assume no cache savings and retain reservations for unreported usage.
- [x] Disable SDK-internal retries, including Google's Interactions-specific retry configuration, to avoid hidden additional requests.
- [x] Document the limits of local budget enforcement: estimates, tokenization differences, and delayed usage can prevent exact billing guarantees.
- [x] Replace universal `tiktoken` admission counting with clearly labeled conservative full-request byte estimates.
- [ ] Define configurable context budgeting/compaction triggers and account for the cost of summarization itself.
- [x] Validate cost controls with temporary fixtures covering cached usage, reasoning tokens, missing pricing, missing usage, retries, budget boundaries, and reconciliation; remove those tests afterward as requested.

## Anthropic

- [x] Replace the retired Claude 3.5 Sonnet default with Claude Sonnet 5.5. Live model evaluation remains below.
- [x] Upgrade the SDK and review the current API-version migration together, including `MessageParam` construction changes.
- [x] Parse content by block type; preserve mixed text, tool-use, and thinking/continuation blocks.
- [x] Preserve tool-result adjacency and block ordering; support explicit tool errors.
- [x] Make forced-tool behavior model/setting-aware rather than unconditionally sending `any`.

## Google

- [x] Fix the erroneous `gpt-4o-mini` default in the Gemini adapter; use Gemini 3.8 Flash.
- [x] Replace the duplicated OpenAI-compatible implementation with a native `google-genai` Interactions adapter.
- [x] Verify Interactions request/response shapes, storage settings, manual replay and retry behavior against the installed SDK and mocked transports.
- [ ] Confirm endpoint availability, model/account access and schema constraints against hosted Google documentation and a live smoke test; hosted docs timed out during research.
- [x] Parse typed steps and preserve thought signatures/native continuation data.
- [x] Reapply interaction-scoped configuration on each turn as required.
- [x] Keep tool execution under `Toolbox`, rather than SDK automatic function execution.

## OpenAI

- [x] Upgrade the SDK and migrate the native adapter from Chat Completions to Responses.
- [x] Serialize canonical history into input items and preserve all required output/continuation items.
- [x] Correlate function outputs with `call_id`, separately from item IDs.
- [x] Map output budgets and configured reasoning options to the selected model/API.
- [x] Choose non-strict schemas explicitly to preserve optional/default arguments and open dictionaries.
- [ ] Review tools with open-ended dictionaries before enabling strict schemas.
- [x] Start with application-owned history replay and explicit storage settings.

## Verification and maintenance

- [ ] Resolve the installed `sqlite-vss` platform mismatch independently of the LLM adapter changes.
- [x] Retain no newly added tests after implementation, per the user's request; record temporary verification results here.
- [ ] Verify multi-turn reasoning continuation and dynamic role/tool changes for each provider.
- [ ] Cover output limits, refusals/blocked responses, initialization, and configuration validation.
- [ ] Run small live smoke tests for each provider after fixture-based checks pass.
- [x] Align dependency declarations, lockfile, environment examples, and documentation after each adapter migration.
- [x] Document the adapter contract and checklist for adding future providers.
- [x] Document pricing/model lifecycle review and update procedures so defaults and accounting do not drift silently.

## Deferred: runtime provider/model switching

- [ ] Define switching at completed tool-call/result boundaries.
- [ ] Rebuild target-provider history from portable conversation semantics.
- [ ] Never forward another provider/model's native reasoning or signature payload.
- [ ] Define capability differences, context adaptation, and continuity expectations when switching.
- [ ] Preserve accumulated spend accounting across switches.

## Research references

Initial architecture/provider review: October 28, 2026. Recheck model availability, SDK versions, API behavior, and pricing when implementing.

- Anthropic: [tool definitions](https://platform.claude.com/docs/en/agents-and-tools/tool-use/define-tools), [tool-call handling](https://platform.claude.com/docs/en/agents-and-tools/tool-use/handle-tool-calls), [model deprecations](https://platform.claude.com/docs/en/about-claude/model-deprecations), [API migration](https://platform.claude.com/docs/en/api/migration-2026-10-21).
- OpenAI: [Responses migration](https://developers.openai.com/api/docs/guides/migrate-to-responses), [function calling](https://developers.openai.com/api/docs/guides/function-calling).
- Google: [Python SDK](https://github.com/googleapis/python-genai), [official integration guidance](https://github.com/google-gemini/gemini-skills/blob/main/skills/gemini-api-dev/SKILL.md), [migration reference](https://github.com/google-gemini/gemini-skills/blob/main/skills/gemini-api-dev/references/migration.md). Hosted Google documentation was unavailable during the initial review; endpoint details need verification.
