import hashlib
import json
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict, replace
from datetime import datetime, timezone

from embeddings.embedding import EmbeddingModel, validate_vector
from embeddings.schema import EMBEDDING_SCHEMA
from memory.schema import MEMORY_REMOVAL_SCHEMA, MEMORY_SCHEMA
from memory.service import (
    Memory,
    MemoryConflictError,
    MemoryDraft,
    MemoryNotFoundError,
    MemoryQuery,
    MemoryServiceError,
    MemoryUpdate,
    MemoryValidationError,
    SearchResult,
)
from storage.database import Database


class SQLiteMemoryService:
    def __init__(
        self,
        database: Database,
        embeddings: EmbeddingModel,
        max_distance: float | None = None,
    ):
        self.database = database
        self.embeddings = embeddings
        self.profile = replace(
            embeddings.profile,
            input_format=f"memory-title-content-v1:{embeddings.profile.input_format}",
        )
        self.max_distance = max_distance
        self._ready = False
        self._profile_id = None
        self._table = None

    @contextmanager
    def _connect(self):
        try:
            with self.database.connect(vectors=True) as connection:
                yield connection
        except (sqlite3.Error, ImportError, OSError, AttributeError) as error:
            raise MemoryServiceError(
                f"SQLite memory failed (check sqlite-vss installation): {error}"
            ) from error

    def startup(self) -> None:
        if self._ready:
            return
        with self._connect() as connection:
            self.database.migrate(connection, "embeddings:001", EMBEDDING_SCHEMA)
            self.database.migrate(connection, "memory:001", MEMORY_SCHEMA)
            self.database.migrate(connection, "memory:002", MEMORY_REMOVAL_SCHEMA)
            connection.execute(
                "INSERT OR IGNORE INTO embedding_profiles(fingerprint,profile_json,created_at) VALUES (?,?,?)",
                (
                    self.profile.fingerprint,
                    json.dumps(asdict(self.profile)),
                    self._now(),
                ),
            )
            profile_id = connection.execute(
                "SELECT id FROM embedding_profiles WHERE fingerprint=?",
                (self.profile.fingerprint,),
            ).fetchone()[0]
            active = connection.execute(
                "SELECT active_profile_id FROM memory_settings WHERE id=1"
            ).fetchone()
            if (
                active
                and active[0] != profile_id
                and connection.execute(
                    "SELECT 1 FROM memories WHERE removed_at IS NULL LIMIT 1"
                ).fetchone()
            ):
                raise MemoryServiceError(
                    "Embedding profile changed. Existing memories require re-embedding; "
                    "restore the previous embedding settings until a migration is performed."
                )
            index = connection.execute(
                "SELECT id FROM memory_embedding_indexes WHERE profile_id=?",
                (profile_id,),
            ).fetchone()
            if index is None:
                # Profile IDs are database-generated integers, never user-supplied identifiers.
                table = f"vss_memory_{profile_id}"
                connection.execute(
                    f"CREATE VIRTUAL TABLE {table} USING vss0(embedding({self.profile.dimensions}))"
                )
                connection.execute(
                    "INSERT INTO memory_embedding_indexes(profile_id,table_name,implementation,implementation_version,metric) "
                    "VALUES (?,?,'sqlite-vss',?,'squared_l2')",
                    (
                        profile_id,
                        table,
                        connection.execute("SELECT vss_version()").fetchone()[0],
                    ),
                )
            table = f"vss_memory_{profile_id}"
            count = connection.execute(
                "SELECT count(*) FROM memories WHERE removed_at IS NULL"
            ).fetchone()[0]
            indexed = connection.execute(
                f"SELECT count(*) FROM memory_embeddings e JOIN {table} v ON v.rowid=e.id "
                "JOIN memories m ON m.id=e.memory_id WHERE e.profile_id=? AND m.removed_at IS NULL",
                (profile_id,),
            ).fetchone()[0]
            if count != indexed:
                raise MemoryServiceError(
                    "Memory index is incomplete; repair/re-embedding is required"
                )
            connection.execute(
                "INSERT INTO memory_settings(id,active_profile_id) VALUES (1,?) "
                "ON CONFLICT(id) DO UPDATE SET active_profile_id=excluded.active_profile_id",
                (profile_id,),
            )
        self._profile_id, self._table, self._ready = profile_id, table, True

    def close(self) -> None:
        self._ready = False  # No persistent connection or background worker to close.
        self.embeddings.close()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _check(self, namespace: str):
        if namespace != "default":
            raise MemoryValidationError(
                "Built-in memory currently supports only the default namespace"
            )
        if not self._ready:
            raise MemoryServiceError("Memory service has not been started")

    def _check_active(self, connection):
        active = connection.execute(
            "SELECT active_profile_id FROM memory_settings WHERE id=1"
        ).fetchone()
        if not active or active[0] != self._profile_id:
            raise MemoryServiceError(
                "Active embedding profile changed; restart memory service"
            )

    def _embed(self, text: str, *, query: bool = False) -> list[float]:
        try:
            operation = (
                self.embeddings.embed_query if query else self.embeddings.embed_document
            )
            return validate_vector(operation(text), self.profile.dimensions)
        except Exception as error:
            raise MemoryServiceError(f"Memory embedding failed: {error}") from error

    def add(self, draft: MemoryDraft) -> Memory:
        self._check(draft.namespace)
        text = f"# {draft.title}\n\n{draft.content}"
        vector = self._embed(text)  # Remote work precedes the writer transaction.
        now = self._now()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._check_active(connection)
            memory_id = connection.execute(
                "INSERT INTO memories(namespace,title,content,type,importance,created_at,updated_at,metadata_json) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (
                    draft.namespace,
                    draft.title,
                    draft.content,
                    draft.type,
                    draft.importance,
                    now,
                    now,
                    json.dumps(draft.metadata, allow_nan=False),
                ),
            ).lastrowid
            embedding_id = connection.execute(
                "INSERT INTO memory_embeddings(memory_id,profile_id,input_hash,created_at,adapter_version) VALUES (?,?,?,?,?)",
                (
                    memory_id,
                    self._profile_id,
                    hashlib.sha256(text.encode()).hexdigest(),
                    now,
                    self.profile.adapter_version,
                ),
            ).lastrowid
            connection.execute(
                f"INSERT INTO {self._table}(rowid,embedding) VALUES (?,?)",
                (embedding_id, json.dumps(vector)),
            )
        return Memory(id=memory_id, **asdict(draft), created_at=now, updated_at=now)

    @staticmethod
    def _memory(row: sqlite3.Row) -> Memory:
        return Memory(
            id=row["id"],
            title=row["title"],
            content=row["content"],
            type=row["type"],
            importance=row["importance"],
            namespace=row["namespace"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            metadata=json.loads(row["metadata_json"]),
            removed_at=row["removed_at"],
        )

    @staticmethod
    def _memory_id(memory_id: int | str) -> int:
        if isinstance(memory_id, bool) or not isinstance(memory_id, (int, str)):
            raise MemoryValidationError(
                "memory_id must be a positive integer ID from recall"
            )
        try:
            value = int(memory_id)
        except ValueError as error:
            raise MemoryValidationError(
                "memory_id must be a positive integer ID from recall"
            ) from error
        if value <= 0:
            raise MemoryValidationError(
                "memory_id must be a positive integer ID from recall"
            )
        return value

    def get(self, memory_id: int | str, namespace: str = "default") -> Memory:
        self._check(namespace)
        memory_id = self._memory_id(memory_id)
        with self._connect() as connection:
            self._check_active(connection)
            row = connection.execute(
                "SELECT * FROM memories WHERE id=? AND namespace=?",
                (memory_id, namespace),
            ).fetchone()
        if row is None:
            raise MemoryNotFoundError(
                f"Memory {memory_id} was not found; use an ID from recall"
            )
        return self._memory(row)

    def update(
        self, memory_id: int | str, changes: MemoryUpdate, namespace: str = "default"
    ) -> Memory:
        original = self.get(memory_id, namespace)
        if original.removed_at is not None:
            raise MemoryServiceError(
                f"Memory {original.id} has been removed and cannot be updated"
            )
        draft = changes.apply(original)
        text_changed = (draft.title, draft.content) != (
            original.title,
            original.content,
        )
        text = f"# {draft.title}\n\n{draft.content}"
        vector = self._embed(text) if text_changed else None
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._check_active(connection)
            row = connection.execute(
                "SELECT * FROM memories WHERE id=? AND namespace=?",
                (original.id, namespace),
            ).fetchone()
            if row is None:
                raise MemoryNotFoundError(f"Memory {original.id} was not found")
            if self._memory(row) != original:
                raise MemoryConflictError(
                    f"Memory {original.id} changed while updating; review the latest recall before retrying"
                )
            now = self._now()
            connection.execute(
                "UPDATE memories SET title=?,content=?,type=?,importance=?,updated_at=? WHERE id=?",
                (
                    draft.title,
                    draft.content,
                    draft.type,
                    draft.importance,
                    now,
                    original.id,
                ),
            )
            if vector is not None:
                embeddings = connection.execute(
                    "SELECT id,profile_id FROM memory_embeddings WHERE memory_id=?",
                    (original.id,),
                ).fetchall()
                active = next(
                    (e for e in embeddings if e["profile_id"] == self._profile_id), None
                )
                if active is None:
                    raise MemoryServiceError(
                        "Memory embedding is missing; index repair is required"
                    )
                for embedding in embeddings:
                    connection.execute(
                        f"DELETE FROM vss_memory_{embedding['profile_id']} WHERE rowid=?",
                        (embedding["id"],),
                    )
                    if embedding["profile_id"] != self._profile_id:
                        connection.execute(
                            "DELETE FROM memory_embeddings WHERE id=?",
                            (embedding["id"],),
                        )
                connection.execute(
                    "UPDATE memory_embeddings SET input_hash=?,created_at=?,adapter_version=? WHERE id=?",
                    (
                        hashlib.sha256(text.encode()).hexdigest(),
                        now,
                        self.profile.adapter_version,
                        active["id"],
                    ),
                )
                connection.execute(
                    f"INSERT INTO {self._table}(rowid,embedding) VALUES (?,?)",
                    (active["id"], json.dumps(vector)),
                )
        return Memory(
            id=original.id,
            **asdict(draft),
            created_at=original.created_at,
            updated_at=now,
        )

    def remove(self, memory_id: int | str, namespace: str = "default") -> Memory:
        self._check(namespace)
        memory_id = self._memory_id(memory_id)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._check_active(connection)
            row = connection.execute(
                "SELECT * FROM memories WHERE id=? AND namespace=?",
                (memory_id, namespace),
            ).fetchone()
            if row is None:
                raise MemoryNotFoundError(
                    f"Memory {memory_id} was not found; use an ID from recall"
                )
            original = self._memory(row)
            if original.removed_at is not None:
                return original
            embeddings = connection.execute(
                "SELECT id,profile_id FROM memory_embeddings WHERE memory_id=?",
                (memory_id,),
            ).fetchall()
            for embedding in embeddings:
                connection.execute(
                    f"DELETE FROM vss_memory_{embedding['profile_id']} WHERE rowid=?",
                    (embedding["id"],),
                )
            now = self._now()
            connection.execute(
                "UPDATE memories SET removed_at=?,updated_at=? WHERE id=?",
                (now, now, memory_id),
            )
        return replace(original, removed_at=now, updated_at=now)

    def search(self, query: MemoryQuery) -> list[SearchResult]:
        self._check(query.namespace)
        if not query.text.strip():
            return []
        with self._connect() as connection:
            self._check_active(connection)
            if not connection.execute(
                "SELECT 1 FROM memories WHERE removed_at IS NULL LIMIT 1"
            ).fetchone():
                return []
        vector = self._embed(query.text, query=True)
        with self._connect() as connection:
            connection.execute("BEGIN")
            self._check_active(connection)
            rows = connection.execute(
                f"SELECT m.*, v.distance FROM {self._table} v "
                "JOIN memory_embeddings e ON e.id=v.rowid JOIN memories m ON m.id=e.memory_id "
                "WHERE vss_search(v.embedding,vss_search_params(?,?)) AND e.profile_id=? AND m.removed_at IS NULL "
                "ORDER BY v.distance,m.id",
                (json.dumps(vector), query.limit, self._profile_id),
            ).fetchall()
        return [
            SearchResult(
                self._memory(row),
                row["distance"],
                "squared_l2",
            )
            for row in rows
            if self.max_distance is None or row["distance"] <= self.max_distance
        ]
