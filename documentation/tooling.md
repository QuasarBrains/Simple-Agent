# Capability libraries and execution

General-purpose capability tools live in `tools/libraries/<capability>/`. Each library exports a list of
discrete `Tool` instances named with a capability namespace. Roles compose these
lists rather than inheriting tools or owning provider implementations.

## Default operations

| Library    | Operations                                                             | Contract                                                                |
| ---------- | ---------------------------------------------------------------------- | ----------------------------------------------------------------------- |
| Filesystem | `fs.read`, `fs.write`, `fs.replace`, `fs.list`, `fs.find`, `fs.search` | UTF-8 text and path discovery, with explicit limits and resolved paths  |
| Search     | `search.with_duckduckgo`, `search.with_wikipedia`                      | Normalized source results: title, URL, excerpt, provider, optional date |
| Web        | `web.fetch`                                                            | Bounded readable HTML/text retrieval, without a browser or JavaScript   |
| Python     | `python.run`                                                           | Stateless, OS-isolated standard-library Python                          |
| Shell      | `shell.run`                                                            | Approval-gated host `/bin/sh` commands                                  |

Helpful Assistant and Researcher expose filesystem, search, web, and Python.
Developer also exposes shell. Their identities focus working practices rather
than security permissions. All retain the shared task, user messaging, role, and
configured memory operations. The interaction library is registered by the harness
for every role, not repeated in individual role tool lists.

### Core memory operations

Memory is a core agent module, with `memory.add`, `memory.update`, and
`memory.remove` defined in `agent/memory.py`. `MemoryEngine.get_tools()` supplies
instance-bound tools using the shared `Tool`/`ToolResult` interface. The harness
registers them directly rather than through a role capability library; tools remain available across role
changes. Disabled memory yields no tools, and add/search-only services omit
`memory.update`; services without soft removal omit `memory.remove`.

`memory.add` requires title/content and defaults to semantic/medium. Updates take
an exact `memory_id` and at least one changed field; omitted fields are preserved.
Successful results include `metadata.memory_id`. Retrieval remains automatic in
the perception loop. Recall and tool handling belong to the core memory engine;
persistence and embeddings stay behind the memory service. See
[Memory](adding-memory.md) for configuration, examples, and adapter interfaces.

`memory.remove` requires an ID and a reason and uses the same per-invocation
registry approval flow as shell execution. Missing approval callbacks or denial
prevent execution. Approval retires the memory from recall and its vector indexes
while retaining its record with a removal timestamp. The CLI displays the tool's
description and arguments so the effect being approved is explicit.

### Interaction and waiting

| Operation                      | Intent                              | Runtime behavior                                                      |
| ------------------------------ | ----------------------------------- | --------------------------------------------------------------------- |
| `interaction.notify(content)`  | Nonblocking progress update         | Continues reasoning; no input requested                               |
| `interaction.ask(content)`     | Question needing an answer          | Pauses until a user message arrives; CLI displays `Reply`             |
| `interaction.finish(content?)` | Completed answer, no reply required | Goes idle until new input or an external stimulus; CLI displays `You` |

A text-only assistant answer is shorthand for finish, so omitting a tool does not
strand the CLI without an input prompt. Text accompanying tool calls remains a
nonblocking update. Avoid duplicating answer text in both ordinary output and an
interaction tool.

Ask and finish end the action batch. Subsequent calls receive skipped/denied
results without execution, preserving provider tool-result pairing. The wait is
entered only after every result is recorded. Existing tasks remain open but cannot
override a wait; the interaction tool's own result cannot immediately wake it.
Validation failures do not enter a wait.

`new_user_message` wakes either wait. Integrations can publish
`new_environment_stimulus` to wake a finished turn without user input; such events
are buffered while an explicit question is awaiting its reply. Normal tool-result
notifications do not count as external wakeups.

The CLI owns terminal input on the main thread through a queue, including shell
approvals. Interaction tool execution never blocks on stdin. Waiting/resumed
transitions are logged as `agent.waiting` / `agent.resumed`. A terminal prompt
means input is available, not that a response is obligatory after every answer.
The former `send_message_to_user` / `prompt_user` tools are no longer registered
by default; custom integrations should migrate to the explicit interaction tools
and waiting events.

### Filesystem

Paths expand `~` and resolve relative to the harness working directory.
`fs.read` supports inclusive line ranges and numbered output. `fs.write` creates
files by default; replacing existing files requires `overwrite=true`, and missing
parents require `create_parents=true`. `fs.replace` replaces a unique exact match;
multiple matches require explicit `replace_all=true`.

Text inputs are UTF-8 with a 4 MiB file limit. PDF and binary extraction are not
part of this initial library. Discovery includes hidden entries, uses glob path
matching, does not interpret `.gitignore`, and reports explicit truncation or
skipped search inputs. Search supports literal and standard Python regex matching;
regex evaluation has no separate deadline. Directory traversal does not follow
symlinks. These tools are not a filesystem sandbox; writes are not transactional.

### Search and web

Search takes `query`, optional `count` (default 5, maximum 10), `max_chars`
(default 12,000, maximum 50,000), and `timeout` (default 15 seconds, maximum 60).
Wikipedia uses the English MediaWiki search API, not exact-title page lookup.
DuckDuckGo uses the maintained `ddgs` package with the backend explicitly fixed to
`duckduckgo` (no automatic cross-provider fallback). Its optional `mode` selects
`web` (default) or `news`; `time_range` accepts `day`, `week`, `month`, or `year`,
and `region` defaults to `us-en`. For current headlines, use `mode="news"` and
`time_range="day"`, then fetch sources to verify publication dates and claims.
Recency filters are provider hints rather than calendar-date guarantees.
Wikipedia timestamps are page-edit times, not article publication or event dates.
No Google, Exa, or Firecrawl backend is bundled yet. Future providers can export
separate operations while preserving the common search result metadata.

`web.fetch` takes `url`, optional `max_bytes` (default 1 MiB, maximum 4 MiB),
`max_chars`, and `timeout`. It retains requested/final URLs, title, content type,
HTTP status, and download/output truncation. It extracts readable HTML content or
returns text/JSON/XML. It does not execute page scripts or fetch binary documents.
HTTP(S) only, up to five redirects; timeouts apply per connection/read operation,
not as a total request deadline. There is no network access policy or private-IP
filter. Requests share queries and URLs with the destination services. Read-only
GET requests can still have effects on poorly designed endpoints.

### Python isolation

`python.run` takes `code`, optional `timeout` (default 30 seconds, maximum 120),
and `max_output_chars` (default 20,000, maximum 100,000). It captures combined
stdout/stderr and prints an optional `result` variable using `repr`.

Each call starts the current interpreter with `-I -S` in a fresh temporary
directory, without inherited secrets or site packages. The macOS `sandbox-exec`
profile denies access by default, permits system and trusted interpreter runtime
reads (including Apple's dynamic-loader support rules), and allows writes only
inside that call's temporary directory. Home/project file contents, networking,
and child-process creation are denied. Ancestor metadata access permits path
resolution without granting project content access. Runtime installations must
have a dedicated prefix; a project-managed uv runtime is supported.

The tool fails closed if the backend is unavailable or rejects startup: there
is no unrestricted fallback. The current backend is **macOS only** and uses a
deprecated Apple facility; other platforms need a reviewed isolation backend.
CPU, open-file, and per-file size limits apply. There is no hard memory or
aggregate disk quota, so this is not a full hostile-code VM. Runtime files are
trusted and readable; do not put secrets in that installation. No persistent
Python session or dependency installation is provided.

### Shell approval

`shell.run` takes `command`, optional `cwd`, `timeout`, and `max_output_chars`.
The CLI shows the exact command, resolved working-directory path, timeout and
output limit before asking **Approve once / Deny**. Deny is the default. Every
invocation requires a fresh decision, even with action display silenced.
Without an approval callback, the registry denies execution.

Shell runs on the host and inherits its environment, credentials, filesystem and
network privileges. Approval is not isolation and does not freeze filesystem
state while the user decides. The command cannot supply environment overrides
through its schema, but shell syntax can of course modify its own environment.
Output capture is bounded; timeout ends the process group. Deliberately detached
descendants may escape cleanup. There is no persistent shell session.

## Results and logging

The model receives JSON with `status`, `content`, and `metadata`. Denial, timeout,
validation failures, and exceptions are explicit non-success results.
`tool.started`, `tool.finished` (including status), and `tool.approval` events are
recorded in the CLI event log. Arguments and results are logged; treat logs as
potentially sensitive. Legacy string-returning custom tools remain supported but
must migrate to `ToolResult` to represent expected failures reliably.

## Migration

Default roles no longer register the experimental flat library's file, search,
HTTP, shell, interpreter, or scraper tools. Their Python modules remain for
existing imports; they retain their original behavior and are not recommended
for new roles. In particular, legacy execution functions do not gain the new
approval or isolation policies automatically. Browser tooling is deferred.

Canonical names such as `fs.read` are encoded to `fs__read` only at provider
boundaries. The registry, role catalog, logs, and normalized history use canonical
names; native provider history retains wire names for lossless replay.

See [Adding a tool](adding-a-tool.md) and [Adding a role](adding-a-role.md).
