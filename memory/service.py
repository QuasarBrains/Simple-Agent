"""Public contract shared by built-in and custom memory services."""

import json
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


class MemoryServiceError(RuntimeError):
    pass


class MemoryValidationError(ValueError):
    pass


class MemoryNotFoundError(MemoryServiceError):
    pass


class MemoryConflictError(MemoryServiceError):
    pass


@dataclass(frozen=True)
class MemoryDraft:
    title: str
    content: str
    type: str
    importance: str
    namespace: str = "default"
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        for name in ("title", "content", "namespace"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise MemoryValidationError(f"Memory {name} must be a nonempty string")
        if self.type not in ("semantic", "episodic"):
            raise MemoryValidationError("Memory type must be semantic or episodic")
        if self.importance not in ("low", "medium", "high", "extreme"):
            raise MemoryValidationError(
                "Memory importance must be low, medium, high or extreme"
            )
        try:
            if not isinstance(self.metadata, dict):
                raise ValueError("metadata must be an object")
            json.dumps(self.metadata, allow_nan=False)
        except (TypeError, ValueError) as error:
            raise MemoryValidationError(
                "Memory metadata must be a JSON object"
            ) from error


@dataclass(frozen=True)
class Memory:
    id: int | str
    title: str
    content: str
    type: str
    importance: str
    namespace: str = "default"
    created_at: str | None = None
    updated_at: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    removed_at: str | None = None


@dataclass(frozen=True)
class MemoryUpdate:
    """Partial correction: omitted fields retain their persisted values."""

    title: str | None = None
    content: str | None = None
    type: str | None = None
    importance: str | None = None

    def __post_init__(self):
        if all(
            value is None
            for value in (self.title, self.content, self.type, self.importance)
        ):
            raise MemoryValidationError("Provide at least one memory field to update")
        MemoryDraft(
            title=self.title if self.title is not None else "unchanged",
            content=self.content if self.content is not None else "unchanged",
            type=self.type if self.type is not None else "semantic",
            importance=self.importance if self.importance is not None else "medium",
        )

    def apply(self, memory: Memory) -> MemoryDraft:
        return MemoryDraft(
            title=self.title if self.title is not None else memory.title,
            content=self.content if self.content is not None else memory.content,
            type=self.type if self.type is not None else memory.type,
            importance=self.importance
            if self.importance is not None
            else memory.importance,
            namespace=memory.namespace,
            metadata=memory.metadata,
        )


@dataclass(frozen=True)
class MemoryQuery:
    text: str
    limit: int = 3
    namespace: str = "default"

    def __post_init__(self):
        if not isinstance(self.text, str):
            raise MemoryValidationError("Memory query text must be a string")
        if (
            isinstance(self.limit, bool)
            or not isinstance(self.limit, int)
            or not 1 <= self.limit <= 100
        ):
            raise MemoryValidationError("Memory query limit must be between 1 and 100")
        if not isinstance(self.namespace, str) or not self.namespace.strip():
            raise MemoryValidationError("Memory namespace must be nonempty")


@dataclass(frozen=True)
class SearchResult:
    memory: Memory
    distance: float | None
    metric: str


class MemoryService(Protocol):
    def startup(self) -> None: ...

    def close(self) -> None: ...

    def add(self, draft: MemoryDraft) -> Memory: ...

    def search(self, query: MemoryQuery) -> list[SearchResult]: ...


@runtime_checkable
class EditableMemoryService(MemoryService, Protocol):
    """Optional standard capability; legacy add/search adapters remain valid."""

    def get(self, memory_id: int | str, namespace: str = "default") -> Memory: ...

    def update(
        self, memory_id: int | str, changes: MemoryUpdate, namespace: str = "default"
    ) -> Memory: ...


@runtime_checkable
class RemovableMemoryService(MemoryService, Protocol):
    def remove(self, memory_id: int | str, namespace: str = "default") -> Memory: ...
