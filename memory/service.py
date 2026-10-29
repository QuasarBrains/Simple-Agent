"""Public contract shared by built-in and custom memory services."""

import json
from dataclasses import dataclass, field
from typing import Any, Protocol


class MemoryServiceError(RuntimeError):
    pass


class MemoryValidationError(ValueError):
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
