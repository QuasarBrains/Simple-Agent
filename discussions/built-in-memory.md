# Built-in, extensible memory

Status: the initial built-in add/search implementation is available. Shared SQLite storage, standalone OpenAI embedding adapters, and the standard memory service interface are implemented. Model migration and import/export utilities remain follow-up work. See the [memory tutorial](../documentation/adding-memory.md) for current setup and extension instructions; the design below records the architecture and future direction.

## Motivation

Simple Vector Store (SVS) works well for memory, but running and configuring two projects adds setup and maintenance time. Simple Agent should own a dedicated memory module that runs in-process, while retaining small, explicit interfaces for extensions.

The goal is a single Simple Agent setup with persistent, useful recall. Preserve what works about current memory before introducing more sophisticated memory behavior.

## Current integration

- `agent/memory.py` owns recall, prompt formatting, and the `add_memory` tool. The agent recalls memories before inference using current environment text.
- `memory/vector_store.py` defines a `Record` and a callable-based `VectorStore` wrapper. This is already an extension boundary, but only covers adding and searching.
- `memory/simple_vector_store.py` calls the SVS HTTP API to search, build, and sync a store. It also reads and writes Markdown files directly in the configured source directory.
- Adding a memory writes a title-named file and triggers synchronization. Search requests up to three records with a distance threshold of `0.4`.
- `simple-agent.py` selects and starts the backend through `VECTOR_STORE_CHOICE_MAP`. Memory currently defaults to disabled.
- The sibling SVS project has replaceable embedding providers and SQLite-based vector storage using native SQLite extensions. Its returned distance is lower-is-better; the agent currently puts that distance in a field named `similarity`.

The dependency is both an HTTP service and a shared-filesystem convention. Replacing just the HTTP calls would leave much of the operational coupling in place.

## Recommended first release

1. Persistent memory inside Simple Agent, with no SVS checkout, server, or shared directory required.
2. A shared application SQLite database, with a memory table and corresponding vector virtual table using the `sqlite-vss` pattern. Memory is one consumer of application storage, not the owner of a memory-only database.
3. A standalone `embeddings/` adapter module, patterned after `llms/`. Start with OpenAI using the existing SDK; providers remain independent of chat-model selection and memory storage.
4. Existing semantic/episodic memory types, importance levels, explicit `add_memory` tool, and recall before inference.
5. Persist embedding provenance and compatibility metadata from the start, so compatible vectors remain searchable and a model migration utility can be added later.
6. A documented service contract implemented by built-in memory and available to custom adapters. Keep the existing SVS option during transition.

Built-in storage removes the second service. The initial hosted embedding provider still needs network access and credentials; fully offline embeddings are a separate provider option to prioritize if required.

## Architecture

```text
Agent + memory tools
        |
   MemoryEngine                   validation, recall policy, prompt budget
        |
   MemoryService                  standard memory operations and search
        |
   SQLiteMemoryService            built-in implementation of the same contract
        +-- application storage   shared connections/migrations, module tables
        +-- embeddings/           provider adapters and model metadata
        +-- vss_memory_*          vector search indexes for compatible profiles

   Custom memory adapter          same contract, arbitrary local/remote source
```

Use a small typed service interface, constructor injection, and simple service/provider factories. The built-in module must implement the public contract itself, with no special access path from the agent. A custom service should be selectable through a factory entry without changing the agent loop, tools, or prompt formatting. It may call a remote API or another memory system; it does not have to use SQLite or the built-in embedding module. A general plugin discovery framework or HTTP server is unnecessary for this first release.

Proposed module layout:

```text
storage/                  application database lifecycle and schema migrations
embeddings/embedding.py   shared adapter interface and metadata/result types
embeddings/openai.py      initial provider implementation
memory/service.py         Memory, SearchResult, MemoryService contract
memory/sqlite.py          built-in memory service
agent/memory.py           agent-facing recall and tools
```

Other modules can add their own tables and consume `embeddings/` without depending on the memory module. Share storage infrastructure and embedding metadata conventions, not a generic table that forces all application data into the memory schema.

### Domain model

Introduce a `Memory` model rather than expanding the generic `Record` indefinitely:

- Stable ID independent of title; an integer primary key fits SQLite/vector row IDs. Custom services may expose opaque string IDs; duplicate titles must not overwrite memories.
- Title, content, type (`semantic` or `episodic`), and validated importance (`low`, `medium`, `high`, `extreme`).
- UTC creation/modification timestamps.
- Namespace, initially with one default, so projects or agents can share storage without mixing recall.
- Optional provenance and extensible metadata, including import path and legacy ID when available.

Keep retrieval information in `SearchResult(memory, distance, metric)` rather than in stored memory. The initial VSS implementation uses squared L2 distance, lower-is-better; make that explicit rather than calling it similarity. Custom services must declare their score semantics, and thresholds must not be transferred between metrics or embedding profiles. The agent consumes ordered results without depending on storage-specific SQL or scores.

### Standard memory service contract

The first contract is deliberately small:

```python
class MemoryService:
    def startup(self) -> None: ...
    def close(self) -> None: ...
    def add(self, draft: MemoryDraft) -> Memory: ...
    def search(self, query: MemoryQuery) -> list[SearchResult]: ...
```

`MemoryDraft` carries title, content, type, importance, namespace (defaulting to `default`), and optional metadata. `MemoryQuery` carries text, limit, and namespace; relevance filtering is configured in the service using its declared score semantics. Initially the built-in service accepts only the default namespace and rejects unsupported namespaces explicitly. Add returns the persisted memory, including its ID. Search returns relevant results in rank order, or an empty list. Define shared validation and operational errors, including the rule that failed writes cannot return success. Initialization and cleanup are explicit and safe to repeat.

Maintenance CRUD can be introduced when needed, without making it a requirement for the initial custom adapter. Do not assume the existing SVS API provides per-memory CRUD. Document lifecycle, input/output models, ordering, namespace behavior, and errors as the adapter specification; an adapter should be verifiable against the same contract checks as built-in memory.

### Standalone embedding adapters

Follow the small adapter pattern in `llms/`: a shared `EmbeddingModel` interface/wrapper, a provider implementation, and explicit selection during application composition. Expose document/query embedding and model metadata; batching can use the same contract where supported. OpenAI is the first implementation. For memory, initially embed one documented combination of title and content, not separate title and content vectors.

Record provider, model, provider model revision when available, dimensions, embedding options, document/query task configuration, input-format version, and normalization policy in a compatibility profile. Keep adapter implementation version as provenance; only changes that affect output compatibility require a new profile. Do not invent a provider model revision if the API does not expose one; retain the requested model identifier and generation time with that limitation documented.

Validate dimensions, finite values, and nonzero vectors. A query is embedded using the selected profile's matching query configuration and searches only that profile's compatible vectors. Equal dimensions alone do not imply compatibility. Metadata preserves this distinction; it does not make different embedding spaces comparable.

Start with one active profile. Changing settings creates/selects a different profile and must not silently mix old vectors into its searches. Initially report that re-embedding is required when existing memories are not covered; do not silently activate an incomplete index. Store enough metadata now to support resumable re-embedding and an atomic active-profile switch later, while retaining the old index until the new one is complete.

### MemoryEngine responsibilities

- Validate tool input and delegate persistence to the backend.
- Build a bounded recall query from environment context, keeping initial behavior close to today's recall. Evaluate task/history additions separately.
- Clear recalled state on empty context or failed recall so previous results do not remain current accidentally.
- Select relevant results and format a distinct memory section within a configurable token budget, retaining IDs and attribution.
- Start with relevance ranking and deterministic tie-breaking. Preserve importance as metadata; evaluate importance weighting and recency decay before adding them.
- Keep state on each instance, replacing the current class-level memory lists. Separate clearing working recall from deleting persistent records.

Persistence/search should work without a chat LLM instance. Tools may be exposed to an LLM, but the backend should not depend on one.

## Persistence and operational behavior

SQLite is the application source of truth under an ignored data directory, for example `datastore/simple-agent.sqlite3`. A shared storage module owns connection policy and schema migrations; memory owns its tables and queries. Other modules can add tables through the same migration mechanism. Markdown will be an editable, synchronized view of memory, preserving the directory-based inspection and editing workflow of SVS.

### Planned Markdown synchronization

Preserving directory-based memory editing is an agreed requirement; the current built-in service does not implement synchronization yet.

- Store stable memory IDs, type, and importance in frontmatter, with readable title/content in the body. File renames retain record identity.
- Write Markdown files for agent-created memories. Import new files and apply file edits to the corresponding SQLite records, re-embedding only when embedded text changes.
- Initially synchronize at startup and through an explicit sync command. Automatic directory watching can follow later.
- Track the last synchronized file/database versions. Detect concurrent edits and preserve both versions instead of silently overwriting either.
- Distinguish deliberate file deletion from an unavailable directory before deleting persistent memory. Finalize deletion semantics before implementation.
- Keep synchronization inside the built-in implementation; custom memory services still follow the same small public service contract.

This is a supported editing interface, not merely one-way export. SQLite remains the operational authority for records, embeddings, and synchronization state.

### Initial schema sketch

This is a logical schema proposal, not an executable migration. Keep ordinary relational data in ordinary tables; `vss0` virtual tables contain vectors and link back by integer row ID.

| Table | Main fields / purpose |
| --- | --- |
| `schema_migrations` | Applied application migration versions and timestamps. |
| `memories` | `id INTEGER PRIMARY KEY`, `namespace`, `title`, `content`, `type`, `importance`, `created_at`, `updated_at`, optional `metadata_json`. Validate type/importance using constraints as well as service input validation. |
| `embedding_profiles` | `id`, unique compatibility fingerprint, provider/model/revision, dimensions, options/task configuration, input-format version, normalization policy, adapter version, creation time. Shared metadata convention available to other modules. |
| `memory_embedding_indexes` | `id INTEGER PRIMARY KEY`, `profile_id` (unique foreign key), internally generated unique virtual-table name, index implementation/version, distance metric. Each index belongs to exactly one compatibility profile. |
| `memory_embeddings` | `id INTEGER PRIMARY KEY`, `memory_id` foreign key, `profile_id` foreign key, hash of embedded input, generation timestamp, generation adapter version. Unique `(memory_id, profile_id)` for the initial one-vector-per-memory design. |
| `memory_settings` | Singleton active embedding profile reference for the initial module. |
| `vss_memory_<profile_id>` | `vss0(embedding(<dimensions>))`; vector row ID equals `memory_embeddings.id`. |

For a first OpenAI profile using 1536 dimensions, the vector DDL has this shape:

```sql
CREATE VIRTUAL TABLE vss_memory_1 USING vss0(
    embedding(1536)
);
```

`sqlite-vss` fixes dimensions at virtual-table creation and its columns are vector columns, so provider/version/content metadata belongs in normal tables. A separate virtual table per compatibility profile avoids comparing incompatible models even when dimensions happen to match. With one active model initially, this is only one memory vector table. Use internally generated identifiers and validated dimensions for DDL, not provider-supplied names.

For the simplest single-profile design, `memories.id` could map directly to the vector row ID. The small `memory_embeddings` mapping is recommended instead: it permits the same memory to have an old and new embedding later without duplicating the memory itself. This is still a memory-specific mapping; another module can define its own embedding relationship.

Search joins vector results through `memory_embeddings` to `memories`. Profile, input hash, and namespace eligibility must be respected before final top-k selection; filtering only the first global k results can underfill or miss relevant namespace results. Initially support the default namespace; do not promise multi-namespace recall until the query strategy is verified against VSS filtering constraints.

Virtual tables do not automatically track ordinary-table edits or enforce their foreign keys. The service explicitly inserts/deletes vectors and mapping rows with memory changes in the same transaction. A later content update must replace affected vectors (delete plus insert for VSS), while deletion removes all associated profile vectors. Foreign-key cascades on ordinary tables alone are insufficient. Input hashes provide a way to detect stale embeddings for future repair/migration tooling.

Use transactions, versioned schema migrations, parameterized queries, and bounded lock waits. Generate embeddings before opening write transactions; persist the record and vector atomically. Embedding failure must not report success or leave partial writes. Metadata-only updates should not re-embed content.

Initialize/close resources explicitly. Account for the agent worker thread: do not pass a default thread-bound SQLite connection from startup into that thread. Use operation-local connections or a clearly owned storage worker. Imports and ordinary writes follow the same rules.

Use the default exhaustive VSS index initially; avoid index-training/tuning options. Verify extension loading and transaction/search behavior on the supported Python/SQLite environment before committing the first migration. Keep that implementation detail inside application storage and the built-in service. See the [sqlite-vss API reference](https://alexgarcia.xyz/sqlite-vss/api-reference.html) for vector-only columns, fixed dimensions, explicit row-ID joins, and SQLite-version-specific search syntax.

An explicitly selected but misconfigured service should produce an actionable startup error. Transient recall failure should publish an error and let the turn proceed without recalled memory. Failed writes must be reported as failures. Disabled memory initializes neither memory indexes nor an embedding client; the application database may still be needed by other modules. Lazy-load optional adapters/providers.

## Configuration and compatibility

Proposed names, not implemented yet:

```dotenv
MEMORY_BACKEND=local                 # local | simple_vector_store | none
DATABASE_PATH=datastore/simple-agent.sqlite3
MEMORY_NAMESPACE=default
EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-3-small
MEMORY_RECALL_LIMIT=3
MEMORY_CONTEXT_TOKEN_BUDGET=1000
```

Resolve relative paths against a documented stable base such as the project root. Add a relevance setting only with documented backend-specific semantics and an evaluated default.

During transition, `MEMORY_BACKEND` takes precedence; if absent, honor `VECTOR_STORE_CHOICE` and existing SVS settings. Reject unknown explicit choices rather than silently disabling memory. Initially retain disabled memory when neither setting is present. Whether new installations should enable local memory automatically remains a product decision, especially when embeddings need a separate credential.

Provide a compatibility adapter for current `VectorStore` integrations and document its retirement window. Keep current memory tool arguments compatible while changing internal types.

## Future migration utilities

Persist profile metadata and content hashes in the first release; build model-switching utilities later. Such a utility embeds existing content into a new profile/index, resumes by checking hashes, verifies complete coverage, and only then switches the active profile. Keep old vectors available until cutover succeeds. Do not merge rankings from different profiles as if their distances were interchangeable.

Existing SVS Markdown import is follow-up work alongside the planned editable-directory synchronization:

1. Read the existing configured SVS memory directory directly. Import should not require the SVS server or its native database extensions.
2. Parse frontmatter safely, preserving importance, memory type, title, and body. Handle the heading generated by the current writer without duplicating it. Report missing/invalid metadata rather than silently inventing semantics.
3. Offer a dry run with counts and per-file issues. Import only the chosen memory directory, not an arbitrary SVS knowledge collection.
4. Retain an import key based on source identity/path and a content hash. Repeated imports skip unchanged files; changed files update their original imported memory under an explicit policy.
5. Generate destination IDs and recompute embeddings using the destination provider. Copy vectors only if their full compatibility fingerprint can be verified.
6. Commit each memory atomically, report progress/failures, and resume interrupted imports without duplicates.
7. Compare counts, metadata, bodies, and representative queries before switching backends. Keep source files intact for rollback.

Switching back to SVS does not automatically include memories created locally after cutover; document export/re-import for that case. Export uses IDs for filenames and proper frontmatter serialization so titles cannot become filesystem paths.

## Delivery phases

### 1. Contracts and baseline

- Define the public memory service and standalone embedding adapter contracts.
- Confirm shared application storage ownership and the memory/profile/vector schema.
- Capture representative recall queries and expected useful memories from the current setup. Compare relevance rather than assuming identical ordering across configurations.
- Establish configuration precedence and the compatibility wrapper.

Done when backend/provider choices are independent of the agent loop and the quality baseline is recorded.

### 2. Local backend

- Implement shared SQLite lifecycle/migrations, memory add/search, VSS indexing, and the initial OpenAI adapter in `embeddings/`.
- Add lifecycle, threading behavior, and embedding fingerprint checks.
- Verify restart persistence, duplicate-title isolation, profile isolation (including same-dimension incompatible models), failed-write atomicity, row-ID joins, and distance ordering with deterministic test vectors.

Done when storage operates independently of the agent and SVS, with no live embedding API required for automated tests.

### 3. Agent integration

- Wire the factory into startup, shutdown, `Agent`, and `MemoryEngine`.
- Preserve the add tool and recall timing; add bounded formatting and instance-owned state.
- Verify disabled startup, empty/failed recall clearing, configuration/provider failures, and use from the actual agent thread.

Done when a fresh Simple Agent setup can add a memory, restart, and recall it without SVS running.

### 4. Document and establish the pattern

- Document the standard service interface with an example custom adapter and shared contract checks.
- Run the recall baseline and measure latency across representative collection sizes.
- Update `.env.example`, the memory tutorial, and README with shared database setup, provider selection, and extension instructions.

Done when built-in memory and a custom service follow the same pattern, with clear extension instructions. Import/export and embedding migration tooling follow separately.

## Agreed direction and remaining details

Agreed: shared application SQLite as source of truth; ordinary memory data plus a corresponding vector virtual table; a standalone embedding adapter module with OpenAI first; persisted embedding provenance/compatibility; and one standard memory service contract for built-in and custom implementations. Keep the initial implementation small and add migration utilities later.

Remaining implementation details: validate the vector-extension installation/runtime, finalize the schema sketch and public method signatures, and choose memory activation defaults. Retain the existing SVS option while establishing the new pattern; determine its longer-term support window separately.

## Later extensions

The boundaries permit local embeddings, additional storage backends, optimized indexes, and different retrieval policies. Defer automatic extraction/consolidation, semantic deduplication, forgetting/decay, procedural memory, hybrid search, and background file synchronization until the baseline is reliable. The first release keeps explicit memory creation and avoids adding an LLM call on every turn.
