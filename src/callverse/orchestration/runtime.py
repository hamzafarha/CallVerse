"""Shared, lazily loaded agent resources (one per process).

Loading bge-m3 takes ~20 s and 2 GB, so it is done once. ``CALLVERSE_RETRIEVER``
chooses ``embedding`` (bge-m3 + FAISS, main), ``keyword`` (TF-IDF baseline,
instant) or ``auto`` (embedding when the index and model load, else keyword).
"""

import os
import threading
from typing import Any

from callverse.agents.advisor import (
    KeywordRetriever,
    KnowledgeRetriever,
    load_knowledge_base_config,
)
from callverse.agents.advisor.intent_classifier import IntentClassifier
from callverse.config import PROJECT_ROOT, config_path, load_yaml
from callverse.llm import LLMClient, get_llm

# A lock, so two threads (two chats) never load the same model at the same time.
_lock = threading.Lock()


class AgentRuntime:
    """Retriever, intent classifier and LLM client shared by every conversation."""

    def __init__(self, retriever_kind: str | None = None, llm: LLMClient | None = None) -> None:
        # Each resource is loaded the first time it is needed ("lazy loading").
        self.retriever_kind = retriever_kind or os.environ.get("CALLVERSE_RETRIEVER", "auto")
        self.llm = llm or get_llm()
        self._retriever: Any = None
        self._keyword: KeywordRetriever | None = None
        self._classifier: IntentClassifier | None = None
        self.retriever_name = "bge-m3 + FAISS (loads on first LLM chat)"
        self.settings = load_yaml("agents")

    @property
    def kb_config(self):
        """Knowledge-base settings from configs/agents.yaml."""
        return load_knowledge_base_config(config_path("agents"), PROJECT_ROOT)

    def keyword_retriever(self) -> KeywordRetriever:
        """The TF-IDF retriever (instant and always available)."""
        if self._keyword is None:
            self._keyword = KeywordRetriever.from_config(self.kb_config)
        return self._keyword

    def retriever(self) -> Any:
        with _lock:
            if self._retriever is not None:
                return self._retriever
            # Try the bge-m3 + FAISS retriever; if it cannot load (no index, no model), use keyword search,
            # unless "embedding" was explicitly required.
            if self.retriever_kind in ("embedding", "auto"):
                try:
                    self._retriever = KnowledgeRetriever.from_config(self.kb_config)
                    self.retriever_name = f"{self.kb_config.embedding_model} + FAISS"
                    return self._retriever
                except Exception:
                    if self.retriever_kind == "embedding":
                        raise
            self._retriever = self.keyword_retriever()
            self.retriever_name = "TF-IDF keyword search"
            return self._retriever

    def classifier(self) -> IntentClassifier:
        with _lock:
            # Load the saved intent classifier (or train it the first time).
            if self._classifier is None:
                self._classifier = IntentClassifier.load_or_train()
            return self._classifier

    def status(self) -> dict[str, Any]:
        """What the API reports about the agents' resources."""
        llm = self.llm.status()
        return {
            "llm_available": llm["available"],
            "llm_mode": self.llm.settings.mode,
            "llm_reason": llm["reason"],
            "llm": llm,
            "models": {
                role: model["repo"] if llm["available"] else None for role, model in llm["roles"].items()
            },
            "pinned_models": self.llm.settings.models,
            "retriever": self.retriever_name,
            "retriever_setting": self.retriever_kind,
        }


_runtime: AgentRuntime | None = None


def get_runtime() -> AgentRuntime:
    """The shared runtime of this process (created on first use)."""
    global _runtime
    if _runtime is None:
        _runtime = AgentRuntime()
    return _runtime


def set_runtime(runtime: AgentRuntime | None) -> None:
    """Replace the shared runtime (used by the tests)."""
    global _runtime
    _runtime = runtime
