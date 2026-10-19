"""Ollama chat client shared by the Client, Advisor and Quality agents.

One client, three roles. Each role has a pinned model (``configs/agents.yaml``)
and a fallback chain. Calls are cached on disk and traced. When Ollama is not
running (``mode: auto``), ``available()`` is False and every agent switches to its
offline backup, so the whole twin still runs.
"""

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from callverse.config import TRACE_DIR, load_yaml
from callverse.llm.cache import LLMCache, cache_key
from callverse.llm.tracing import Tracer, timer


class LLMUnavailableError(RuntimeError):
    """Raised when a model is needed but Ollama (or the model) is not reachable."""


@dataclass(frozen=True)
class LLMSettings:
    """LLM settings from ``configs/agents.yaml`` (section ``llm``)."""

    base_url: str
    mode: str
    temperature: float
    seed: int
    timeout_seconds: float
    cache: bool
    models: dict[str, str]
    fallbacks: dict[str, list[str]] = field(default_factory=dict)
    profile: str = "full"


def load_llm_settings() -> LLMSettings:
    """Read the LLM section; ``CALLVERSE_LLM_MODE`` / ``OLLAMA_HOST`` override it."""
    import os

    raw = load_yaml("agents")["llm"]
    profile = os.environ.get("CALLVERSE_LLM_PROFILE", raw.get("profile", "full"))
    models = raw["profiles"][profile] if "profiles" in raw else raw["models"]
    return LLMSettings(
        base_url=os.environ.get("OLLAMA_HOST", raw["base_url"]).rstrip("/"),
        mode=os.environ.get("CALLVERSE_LLM_MODE", raw["mode"]),
        temperature=float(raw["temperature"]),
        seed=int(raw["seed"]),
        timeout_seconds=float(raw["timeout_seconds"]),
        cache=bool(raw["cache"]),
        models={k: str(v) for k, v in models.items()},
        profile=profile,
        fallbacks={k: list(v) for k, v in raw.get("fallbacks", {}).items()},
    )


@dataclass
class LLMResponse:
    """Answer of one chat call."""

    content: str
    tool_calls: list[dict[str, Any]]
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: float = 0.0
    cached: bool = False

    def json(self) -> dict[str, Any]:
        """Content parsed as JSON (tolerates text around the JSON object)."""
        text = self.content.strip()
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end < start:
            raise ValueError(f"No JSON object in model output: {text[:200]!r}")
        return json.loads(text[start : end + 1])


class LLMClient:
    """Thin wrapper over Ollama's ``/api/chat`` with pinning, cache and tracing."""

    def __init__(
        self,
        settings: LLMSettings | None = None,
        trace_dir: str | Path = TRACE_DIR,
    ) -> None:
        self.settings = settings or load_llm_settings()
        trace_dir = Path(trace_dir)
        self.cache = LLMCache(trace_dir / "llm_cache.sqlite") if self.settings.cache else None
        self.tracer = Tracer(trace_dir / "llm_calls.jsonl")
        self._installed: list[str] | None = None
        self._checked_at = 0.0

    # ------------------------------------------------------------------ discovery
    def installed_models(self, refresh: bool = False) -> list[str]:
        """Models pulled in Ollama (empty when the server is down). Cached 30 s."""
        if self.settings.mode == "off":
            return []
        if not refresh and self._installed is not None and time.time() - self._checked_at < 30:
            return self._installed
        try:
            response = httpx.get(f"{self.settings.base_url}/api/tags", timeout=3)
            response.raise_for_status()
            self._installed = [m["name"] for m in response.json().get("models", [])]
        except (httpx.HTTPError, ValueError):
            self._installed = []
        self._checked_at = time.time()
        return self._installed

    def available(self) -> bool:
        """True when Ollama answers and LLM mode is not ``off``."""
        return bool(self.installed_models())

    def resolve_model(self, role: str) -> str | None:
        """Pinned model of a role, or its first installed fallback."""
        installed = set(self.installed_models())
        candidates = [self.settings.models[role], *self.settings.fallbacks.get(role, [])]
        for name in candidates:
            if name in installed or f"{name}:latest" in installed:
                return name
        return None

    def model_digests(self) -> dict[str, Any]:
        """Digest of each pinned model, for ``llm_models.lock.json``."""
        try:
            response = httpx.get(f"{self.settings.base_url}/api/tags", timeout=3)
            response.raise_for_status()
            models = {m["name"]: m for m in response.json().get("models", [])}
        except (httpx.HTTPError, ValueError):
            models = {}
        lock = {}
        for role in self.settings.models:
            name = self.resolve_model(role)
            info = models.get(name or "", {})
            lock[role] = {
                "pinned": self.settings.models[role],
                "resolved": name,
                "digest": info.get("digest"),
                "size_bytes": info.get("size"),
                "family": (info.get("details") or {}).get("family"),
                "parameters": (info.get("details") or {}).get("parameter_size"),
                "quantization": (info.get("details") or {}).get("quantization_level"),
            }
        return lock

    # ----------------------------------------------------------------------- chat
    def chat(
        self,
        role: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        json_mode: bool = False,
        agent: str | None = None,
        temperature: float | None = None,
    ) -> LLMResponse:
        """One chat completion for an agent role (``client``, ``advisor``, ``judge``)."""
        model = self.resolve_model(role)
        if model is None:
            raise LLMUnavailableError(
                f"No model available for role '{role}' "
                f"(pinned {self.settings.models[role]}; is Ollama running?)."
            )
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": self.settings.temperature if temperature is None else temperature,
                "seed": self.settings.seed,
            },
        }
        if tools:
            payload["tools"] = tools
        if json_mode:
            payload["format"] = "json"

        key = cache_key(payload)
        if self.cache is not None:
            hit = self.cache.get(key)
            if hit is not None:
                result = LLMResponse(**{**hit, "cached": True, "latency_ms": 0.0})
                self._trace(agent or role, result, messages)
                return result

        with timer() as elapsed:
            try:
                response = httpx.post(
                    f"{self.settings.base_url}/api/chat",
                    json=payload,
                    timeout=self.settings.timeout_seconds,
                )
                response.raise_for_status()
                body = response.json()
            except httpx.HTTPError as error:
                self.tracer.record({"agent": agent or role, "model": model, "error": str(error)})
                raise LLMUnavailableError(f"Ollama call failed: {error}") from error
        message = body.get("message", {})
        tool_calls = [
            {
                "name": call["function"]["name"],
                "arguments": call["function"].get("arguments") or {},
            }
            for call in message.get("tool_calls") or []
        ]
        result = LLMResponse(
            content=message.get("content", ""),
            tool_calls=tool_calls,
            model=model,
            prompt_tokens=int(body.get("prompt_eval_count", 0)),
            completion_tokens=int(body.get("eval_count", 0)),
            latency_ms=elapsed["ms"],
        )
        if self.cache is not None:
            self.cache.put(
                key,
                {
                    "content": result.content,
                    "tool_calls": result.tool_calls,
                    "model": result.model,
                    "prompt_tokens": result.prompt_tokens,
                    "completion_tokens": result.completion_tokens,
                },
            )
        self._trace(agent or role, result, messages)
        return result

    def _trace(self, agent: str, result: LLMResponse, messages: list[dict[str, Any]]) -> None:
        last = str(messages[-1].get("content", "")) if messages else ""
        self.tracer.record(
            {
                "agent": agent,
                "model": result.model,
                "prompt_tokens": result.prompt_tokens,
                "completion_tokens": result.completion_tokens,
                "latency_ms": round(result.latency_ms, 1),
                "cached": result.cached,
                "tool_calls": [c["name"] for c in result.tool_calls],
                "cost_eur": 0.0,  # local model: no per-token cost
                "input_preview": last[:300],
                "output_preview": result.content[:300],
            }
        )


_client: LLMClient | None = None


def get_llm() -> LLMClient:
    """Process-wide LLM client."""
    global _client
    if _client is None:
        _client = LLMClient()
    return _client


def set_llm(client: LLMClient | None) -> None:
    """Replace the shared client (tests, or after changing settings)."""
    global _client
    _client = client
