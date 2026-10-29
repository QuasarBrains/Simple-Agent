"""Application-wide SQLite lifecycle and transactional, module-owned migrations."""

import sqlite3
from collections.abc import Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser().resolve()

    @classmethod
    def from_config(cls, config: Mapping[str, str]) -> "Database":
        path = Path(
            config.get("DATABASE_PATH") or "datastore/simple-agent.sqlite3"
        ).expanduser()
        if not path.is_absolute():
            path = Path(__file__).resolve().parent.parent / path
        return cls(path)

    @contextmanager
    def connect(self, *, vectors: bool = False) -> Iterator[sqlite3.Connection]:
        # Connections are operation-local, including when called by the agent thread.
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA journal_mode = WAL")
            if vectors:
                import sqlite_vss

                connection.enable_load_extension(True)
                try:
                    sqlite_vss.load(connection)
                finally:
                    connection.enable_load_extension(False)
            with connection:
                yield connection
        finally:
            connection.close()

    @staticmethod
    def migrate(
        connection: sqlite3.Connection, version: str, statements: tuple[str, ...]
    ):
        """Apply a named migration inside the caller's transaction."""
        if not connection.in_transaction:
            connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations "
            "(version TEXT PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
        )
        if connection.execute(
            "SELECT 1 FROM schema_migrations WHERE version = ?", (version,)
        ).fetchone():
            return
        for statement in statements:
            connection.execute(statement)
        connection.execute(
            "INSERT INTO schema_migrations(version) VALUES (?)", (version,)
        )
