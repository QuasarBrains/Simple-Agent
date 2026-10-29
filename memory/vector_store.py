from typing import Callable, List, Literal, Optional
from dataclasses import dataclass


@dataclass
class Record:
    id: Optional[int]
    title: str
    content: str
    type: str
    similarity: Optional[float]
    importance: Literal["low", "medium", "high", "extreme"]


class VectorStore:
    on_startup: Optional[Callable[[], None]] = None
    name: str
    query_store: Callable[[str], List[Record]]
    add_record: Callable[[Record], None]

    def __init__(
        self,
        name: str,
        query_store: Callable[[str], List[Record]],
        add_record: Callable[[Record], None],
        on_startup: Optional[Callable[[], None]] = None,
    ) -> None:
        self.name = name
        self.query_store = query_store
        self.add_record = add_record
        if on_startup:
            self.on_startup = on_startup

    def startup(self):
        if self.on_startup:
            self.on_startup()

    def query(self, query: str) -> List[Record]:
        return self.query_store(query)

    def add(self, record: Record) -> None:
        self.add_record(record)
