"""Compatibility bridge for existing callable-based VectorStore adapters."""

from memory.service import (
    Memory,
    MemoryDraft,
    MemoryQuery,
    MemoryServiceError,
    MemoryValidationError,
    SearchResult,
)
from memory.vector_store import Record, VectorStore


class VectorStoreMemoryService:
    def __init__(self, store: VectorStore):
        self.store = store
        self._ready = False

    def startup(self):
        if not self._ready:
            try:
                self.store.startup()
            except Exception as error:
                raise MemoryServiceError(
                    f"Legacy memory startup failed: {error}"
                ) from error
            self._ready = True

    def close(self):
        self._ready = False

    def _check(self, namespace):
        if namespace != "default":
            raise MemoryValidationError(
                "Legacy memory supports only the default namespace"
            )
        if not self._ready:
            raise MemoryServiceError("Memory service has not been started")

    def add(self, draft: MemoryDraft) -> Memory:
        self._check(draft.namespace)
        record = Record(
            None, draft.title, draft.content, draft.type, None, draft.importance
        )
        try:
            self.store.add(record)
        except Exception as error:
            raise MemoryServiceError(f"Legacy memory write failed: {error}") from error
        # Old adapters do not return persisted IDs; expose an opaque legacy ID.
        return Memory(
            id=record.id if record.id is not None else draft.title,
            title=draft.title,
            content=draft.content,
            type=draft.type,
            importance=draft.importance,
            metadata=draft.metadata,
        )

    def search(self, query: MemoryQuery) -> list[SearchResult]:
        self._check(query.namespace)
        if not query.text.strip():
            return []
        try:
            records = self.store.query(query.text)
        except Exception as error:
            raise MemoryServiceError(f"Legacy memory recall failed: {error}") from error
        return [
            SearchResult(
                Memory(
                    id=r.id if r.id is not None else r.title,
                    title=r.title,
                    content=r.content,
                    type=r.type,
                    importance=r.importance,
                ),
                r.similarity,
                "legacy_distance",
            )
            for r in records[: query.limit]
        ]
