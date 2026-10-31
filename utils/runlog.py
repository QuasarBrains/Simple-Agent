"""Append-only human and structured logs, correlated by session identity."""

from datetime import datetime, timezone
import json
from pathlib import Path
from threading import Lock


class SessionLogger:
    FILES = (
        "agent.log",
        "toolbox.log",
        "general.log",
        "errors.log",
        "last_thread.md",
        "usage.jsonl",
        "events.jsonl",
    )

    def __init__(self, directory: str | Path, session_id: str, *, clear: bool = False):
        self.directory = Path(directory).expanduser()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.session_id = session_id
        self._lock = Lock()
        if clear:
            for name in self.FILES:
                path = self.directory / name
                if path.exists():
                    path.write_text("")

    def text(self, name: str, message: str):
        timestamp = datetime.now(timezone.utc).isoformat()
        with self._lock:
            with (self.directory / name).open("a") as handle:
                handle.write(f"**{timestamp}** [{self.session_id[:8]}]: {message}\n")

    def json(self, name: str, data: dict):
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session_id": self.session_id,
            **data,
        }
        with self._lock:
            with (self.directory / name).open("a") as handle:
                handle.write(json.dumps(entry, default=str) + "\n")

    def event(self, name: str, data: dict):
        self.json("events.jsonl", {"event": name, "data": data})
