"""Tracing of every agent call: model, tokens, latency, cache hits, errors.

Traces are appended to ``artifacts/traces/llm_calls.jsonl`` (always on). When the
``LANGFUSE_PUBLIC_KEY`` / ``LANGFUSE_SECRET_KEY`` environment variables are set and
the ``langfuse`` package is installed, each call is also sent to Langfuse.
"""

import json
import os
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

_lock = threading.Lock()


class Tracer:
    """Writes one JSON line per LLM call, and optionally forwards to Langfuse."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._langfuse = self._init_langfuse()

    @staticmethod
    def _init_langfuse() -> Any:
        if not (os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY")):
            return None
        try:
            from langfuse import Langfuse  # optional dependency
        except ImportError:
            return None
        return Langfuse()

    def record(self, event: dict[str, Any]) -> None:
        """Append one trace event."""
        event = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), **event}
        with _lock, open(self.path, "a", encoding="utf-8") as trace_file:
            trace_file.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
        if self._langfuse is not None:
            try:
                self._langfuse.generation(
                    name=event.get("agent", "llm"),
                    model=event.get("model"),
                    input=event.get("input_preview"),
                    output=event.get("output_preview"),
                    usage={
                        "input": event.get("prompt_tokens", 0),
                        "output": event.get("completion_tokens", 0),
                    },
                    metadata={"latency_ms": event.get("latency_ms")},
                )
            except Exception:  # tracing must never break an agent
                pass

    def read(self, limit: int = 500) -> list[dict[str, Any]]:
        """Last ``limit`` trace events (most recent last)."""
        if not self.path.exists():
            return []
        with open(self.path, encoding="utf-8") as trace_file:
            lines = trace_file.readlines()[-limit:]
        return [json.loads(line) for line in lines if line.strip()]


@contextmanager
def timer() -> Iterator[dict[str, float]]:
    """Measures elapsed milliseconds into ``result['ms']``."""
    result = {"ms": 0.0}
    start = time.perf_counter()
    try:
        yield result
    finally:
        result["ms"] = (time.perf_counter() - start) * 1000
