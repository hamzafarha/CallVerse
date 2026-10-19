"""Disk cache of LLM answers, keyed by everything that can change the answer.

With a fixed seed and temperature, Ollama is deterministic for a given model
version, so replaying a call from the cache gives the same result as calling the
model again, at no cost. This is what makes agent runs reproducible.
"""

import hashlib
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any


def cache_key(payload: dict[str, Any]) -> str:
    """SHA-256 of the canonical JSON of a request."""
    text = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class LLMCache:
    """Tiny SQLite key-value store; safe to share between threads."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS llm_cache (key TEXT PRIMARY KEY, response TEXT NOT NULL)"
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=30)

    def get(self, key: str) -> dict[str, Any] | None:
        """Cached response, or None."""
        with self._lock, self._connect() as connection:
            row = connection.execute("SELECT response FROM llm_cache WHERE key = ?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def put(self, key: str, response: dict[str, Any]) -> None:
        """Store a response (overwrites)."""
        with self._lock, self._connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO llm_cache (key, response) VALUES (?, ?)",
                (key, json.dumps(response, ensure_ascii=False)),
            )

    def size(self) -> int:
        """Number of cached calls."""
        with self._lock, self._connect() as connection:
            return int(connection.execute("SELECT COUNT(*) FROM llm_cache").fetchone()[0])
