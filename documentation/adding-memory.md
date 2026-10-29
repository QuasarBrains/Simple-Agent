# Memory

Simple Agent has an optional built-in memory service. It stores memories in the shared application SQLite database and searches embeddings in-process with `sqlite-vss`. No Simple Vector Store checkout or server is needed for built-in memory.

## Enable built-in memory

Install the project dependencies with `uv sync`, then configure `config.toml`:

```toml
[llm.providers.openai]
api_key = "your-key"

[memory]
backend = "local"
database_path = "datastore/simple-agent.sqlite3"
embedding_provider = "openai"
embedding_model = "text-embedding-3-small"
recall_limit = 3
context_token_budget = 1000
```

Run `uv run simple-agent.py`. Ask the agent to remember something using its `add_memory` tool. Memories survive restarts and are recalled before inference. The chat provider can be OpenAI, Anthropic, or Google independently of the embedding provider.

Relative database paths resolve against the Simple Agent project root. The database and parent directories are created on first startup. `datastore/` is ignored by Git. This database is application storage: future modules can add their own tables through `storage.database.Database` and named transactional migrations.

Other modules can use `Database.from_config(config)` to resolve the same application database, then apply their own named migrations within `with database.connect() as connection:`. Plain database connections do not load vector extensions; vector consumers opt in with `connect(vectors=True)`.

The SQLite runtime must allow loading extensions and support the `sqlite-vss` binary for your platform. An extension loading failure is reported at memory startup. The built-in service currently accepts only the `default` namespace.

### Configuration

The fields in `[memory]` use the lowercase names shown in `config.example.toml`.
For example, `MEMORY_RECALL_LIMIT` maps to `memory.recall_limit`; embedding fields
use `embedding_provider`, `embedding_model`, and `embedding_dimensions`. Provider
keys and base URLs come from `[llm.providers.openai]`. The legacy variables below
are still accepted as environment overrides or `.env` fallbacks.

| Variable | Default / behavior |
| --- | --- |
| `MEMORY_BACKEND` | `local`, `simple_vector_store`, or `none`. Blank/unset falls back to `VECTOR_STORE_CHOICE`, then `none`. |
| `DATABASE_PATH` | `datastore/simple-agent.sqlite3`; shared application database path. |
| `EMBEDDING_PROVIDER` | `openai`; independent adapter selection. |
| `EMBEDDING_MODEL` | `text-embedding-3-small`. |
| `EMBEDDING_DIMENSIONS` | Optional. Known OpenAI model defaults are inferred; custom model names require an explicit dimension count. |
| `OPENAI_API_KEY` | Required for OpenAI embeddings, even if a different provider handles chat. |
| `OPENAI_BASE_URL` | Optional OpenAI-compatible endpoint, included in embedding compatibility metadata. |
| `MEMORY_RECALL_LIMIT` | `3`; accepts 1–100. Built-in recall returns the nearest memories in squared-L2 distance order, without a distance cutoff by default. |
| `MEMORY_CONTEXT_TOKEN_BUDGET` | `1000`; positive memory-text budget using `cl100k_base` tokenization. |

Set `MEMORY_BACKEND=none` to disable memory explicitly. Disabled memory does not construct an embedding provider or initialize memory tables. Unknown backend/provider names produce configuration errors.

## Storage and embedding compatibility

Memory data lives in `memories`. Embedding provenance lives in `embedding_profiles` and `memory_embeddings`; `memory_embedding_indexes` identifies each profile's vector virtual table. The active profile is recorded in `memory_settings`. Applied module migrations are tracked in `schema_migrations`.

Each memory gets a stable integer ID; titles are not identifiers and do not become filesystem paths. Content, type (`semantic`/`episodic`), importance (`low`/`medium`/`high`/`extreme`), timestamps, and JSON metadata are stored in ordinary tables. One vector represents `# <title>\n\n<content>`. Vector row IDs map through `memory_embeddings` to the memory record.

Embedding profiles identify provider, model, dimensions, model revision when exposed, provider options, task configuration, normalization, and input-format version. Adapter version and generation timestamps provide provenance. Different embedding spaces are never compared merely because their dimensions match. Hosted providers may not expose an immutable model revision; the metadata records the requested identifier without inventing one.

Changing embedding settings on a populated database currently reports that re-embedding is required. Restore the original settings to continue using existing memory. Automated re-embedding, SVS Markdown import/export, and maintenance CRUD are follow-up work; this release establishes add/search and the adapter pattern.

Adding a memory generates its vector before opening the write transaction, then commits the memory, provenance, and vector together. Failed writes return errors. Recall failures clear recalled state, publish an agent error, and allow the turn to proceed. There is no automatic memory extraction, importance weighting, or extra chat-model call for recall.

## Custom memory services

The agent uses `memory.service.MemoryService`. Built-in SQLite memory implements this same public contract:

```python
class MemoryService:
    def startup(self) -> None: ...
    def close(self) -> None: ...
    def add(self, draft: MemoryDraft) -> Memory: ...
    def search(self, query: MemoryQuery) -> list[SearchResult]: ...
```

- `startup`/`close` must be safe to repeat. Operations require a started service; startup after close is supported.
- `MemoryDraft` validates title/content, type, importance, namespace, and JSON metadata. Add returns a persisted `Memory` with an integer or opaque string ID.
- `MemoryQuery` contains text, limit, and namespace. Empty/whitespace queries return no results. Search returns at most the requested limit in relevance order.
- `SearchResult` carries the memory, optional distance, and declared metric. A custom service that uses similarity can declare its metric accordingly; the agent uses returned order rather than comparing scores across services.
- Use `MemoryValidationError` for invalid/unsupported input and `MemoryServiceError` for operational failures. Never report a failed write as successful. Reject unsupported namespaces instead of ignoring them.
- Implementations must support calls from the agent worker thread. SQLite memory uses operation-local connections for this purpose.

For example, adapt an existing service without changing the agent:

```python
from memory.config import MEMORY_FACTORIES


class CustomMemoryService:
    # Implement startup, close, add, and search using your source's client.
    # Translate records/errors to the types in memory.service.
    ...


MEMORY_FACTORIES["custom"] = lambda config: CustomMemoryService()
```

Register the factory before `create_memory_service` is called, then set `MEMORY_BACKEND=custom`. A remote service can own embedding generation itself; it need not use our SQLite schema or `embeddings/`.

## Adding an embedding provider

`embeddings/embedding.py` defines the independent `EmbeddingModel` protocol. Follow `embeddings/openai.py`: expose an immutable `EmbeddingProfile`, implement `embed_document(text)` and `embed_query(text)` returning numeric vectors, and implement repeatable `close()` to release clients. The adapter must remain usable after close by lazily recreating clients. Return vectors matching the advertised dimensions; built-in memory validates finite, nonzero vectors before indexing.

Register a configuration factory in `embeddings.config.EMBEDDING_FACTORIES` and select it with `EMBEDDING_PROVIDER`. The profile fingerprint includes compatibility-affecting settings; bump input/adapter configuration when output semantics change. Changing only adapter implementation version does not create a new embedding space.

Memory owns its title/content input format. Another application module can use the embedding adapters and shared profile metadata without depending on the memory engine.

## Existing Simple Vector Store setups

The original adapter remains available:

```toml
[memory]
backend = "simple_vector_store"
simple_vector_store_url = "http://localhost:8000"
simple_vector_store_directory = "/absolute/path/to/memory-markdown"
simple_vector_store_name = "simple-agent-memory"
```

SVS still requires its server and shared Markdown directory. Existing `VECTOR_STORE_CHOICE=simple_vector_store` configurations continue to work when `MEMORY_BACKEND` is blank/unset. Existing custom `VectorStore` instances can be wrapped with `memory.legacy.VectorStoreMemoryService`.

Legacy adapters retain their own search limits, thresholds, and ID behavior. The old add callback returns no persisted ID, so the compatibility bridge uses the title as an opaque fallback ID; new adapters should return their actual persisted ID. Selecting built-in memory does not automatically import SVS data.

See the [architecture plan](../discussions/built-in-memory.md) for schema rationale and future migration work.
