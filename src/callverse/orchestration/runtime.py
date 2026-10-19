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

_lock = threading.Lock()


class AgentRuntime:
    """Retriever, intent classifier and LLM client shared by every conversation."""

    def __init__(self, retriever_kind: str | None = None, llm: LLMClient | None = None) -> None:
        self.retriever_kind = retriever_kind or os.environ.get("CALLVERSE_RETRIEVER", "auto")
        self.llm = llm or get_llm()
        self._retriever: Any = None
        self._keyword: KeywordRetriever | None = None
        self._classifier: IntentClassifier | None = None
        self.retriever_name = "bge-m3 + FAISS (loads on first LLM chat)"
        self.settings = load_yaml("agents")

    @property
    def kb_config(self):
        return load_knowledge_base_config(config_path("agents"), PROJECT_ROOT)

    def keyword_retriever(self) -> KeywordRetriever:
        if self._keyword is None:
            self._keyword = KeywordRetriever.from_config(self.kb_config)
        return self._keyword

    def retriever(self) -> Any:
        with _lock:
            if self._retriever is not None:
                return self._retriever
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
            if self._classifier is None:
                self._classifier = IntentClassifier.load_or_train()
            return self._classifier

    def status(self) -> dict[str, Any]:
        llm_ok = self.llm.available()
        return {
            "llm_available": llm_ok,
            "llm_mode": self.llm.settings.mode,
            "models": {
                role: self.llm.resolve_model(role) if llm_ok else None for role in self.llm.settings.models
            },
            "pinned_models": self.llm.settings.models,
            "retriever": self.retriever_name,
            "retriever_setting": self.retriever_kind,
        }


_runtime: AgentRuntime | None = None


def get_runtime() -> AgentRuntime:
    global _runtime
    if _runtime is None:
        _runtime = AgentRuntime()
    return _runtime


def set_runtime(runtime: AgentRuntime | None) -> None:
    global _runtime
    _runtime = runtime
