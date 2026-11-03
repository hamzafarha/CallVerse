"""Chat client shared by the Client, Advisor and Quality agents.

One client, three roles, two providers. With ``provider: openrouter`` each role
first uses its hosted model on OpenRouter (see ``openrouter``); when the key is
missing, the free daily quota is used up or the API fails, the same call goes to
the role's local Hugging Face model, run with ``transformers`` (see ``hf_local``).
Calls are cached on disk and traced. When no model can run, ``available()`` is
False and every agent switches to its offline backup, so the whole twin still runs.
"""

import json
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from callverse.config import TRACE_DIR, load_yaml
from callverse.llm.cache import LLMCache, cache_key
from callverse.llm.hf_local import (
    ModelOptions,
    ModelPool,
    StreamGate,
    gpu_info,
    parse_tool_calls,
    strip_thinking,
)
from callverse.llm.openrouter import OpenRouterClient, OpenRouterSettings, OpenRouterUnavailable
from callverse.llm.tracing import Tracer, timer

LOCK_FILE = TRACE_DIR / "llm_models.lock.json"


class LLMUnavailableError(RuntimeError):
    """Raised when a model is needed but cannot run (no GPU, not downloaded, mode off)."""


@dataclass(frozen=True)
class LLMSettings:
    """LLM settings from ``configs/agents.yaml`` (section ``llm``)."""

    mode: str
    temperature: float
    seed: int
    cache: bool
    models: dict[str, str]
    fallbacks: dict[str, list[str]] = field(default_factory=dict)
    profile: str = "gpu4gb"
    provider: str = "transformers"
    device: str = "auto"
    max_new_tokens: dict[str, int] = field(default_factory=dict)
    catalog: dict[str, dict[str, Any]] = field(default_factory=dict)
    openrouter: dict[str, Any] = field(default_factory=dict)


def load_llm_settings() -> LLMSettings:
    """Read the LLM section; ``CALLVERSE_LLM_MODE`` / ``_PROFILE`` / ``_DEVICE`` /
    ``_PROVIDER`` override it."""
    raw = load_yaml("agents")["llm"]
    profile = os.environ.get("CALLVERSE_LLM_PROFILE", raw.get("profile", "gpu4gb"))
    return LLMSettings(
        mode=os.environ.get("CALLVERSE_LLM_MODE", raw["mode"]),
        temperature=float(raw["temperature"]),
        seed=int(raw["seed"]),
        cache=bool(raw["cache"]),
        models={k: str(v) for k, v in raw["profiles"][profile].items()},
        fallbacks={k: list(v) for k, v in raw.get("fallbacks", {}).items()},
        profile=profile,
        provider=os.environ.get("CALLVERSE_LLM_PROVIDER", str(raw.get("provider", "transformers"))),
        device=os.environ.get("CALLVERSE_LLM_DEVICE", str(raw.get("device", "auto"))),
        max_new_tokens={k: int(v) for k, v in raw.get("max_new_tokens", {}).items()},
        catalog={k: dict(v) for k, v in raw.get("catalog", {}).items()},
        openrouter=dict(raw.get("openrouter", {})),
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
        """Content parsed as JSON (tolerates text around it and a truncated tail)."""
        text = self.content.strip()
        start = text.find("{")
        if start < 0:
            raise ValueError(f"No JSON object in model output: {text[:200]!r}")
        end = text.rfind("}")
        if end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                pass
        repaired = repair_json(text[start:])
        if repaired is None:
            raise ValueError(f"No JSON object in model output: {text[:200]!r}")
        return repaired


def repair_json(text: str) -> dict[str, Any] | None:
    """Close a JSON object that a small model stopped writing too early."""
    in_string, escaped, depth = False, False, 0
    for char in text:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char in "{[":
            depth += 1
        elif char in "}]":
            depth -= 1
    tail = text.rstrip().rstrip(",")
    closing = ('"' if in_string else "") + "}" * max(depth, 1)
    for candidate in (tail + closing, tail.rsplit(",", 1)[0] + "}" * max(depth, 1)):
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return None


def _is_downloaded(repo: str, revision: str | None = None) -> bool:
    """True when the repository's config and weights are in the local HF cache."""
    from huggingface_hub import try_to_load_from_cache

    config = try_to_load_from_cache(repo, "config.json", revision=revision)
    return isinstance(config, str) and any(Path(config).parent.glob("*.safetensors"))


class LLMClient:
    """OpenRouter models first, local Hugging Face models as backup; cache, tracing, streaming."""

    def __init__(
        self,
        settings: LLMSettings | None = None,
        trace_dir: str | Path = TRACE_DIR,
        remote: OpenRouterClient | None = None,
    ) -> None:
        self.settings = settings or load_llm_settings()
        trace_dir = Path(trace_dir)
        self.cache = LLMCache(trace_dir / "llm_cache.sqlite") if self.settings.cache else None
        self.tracer = Tracer(trace_dir / "llm_calls.jsonl")
        self.pool = ModelPool()
        self._downloaded: dict[str, bool] = {}
        self._checked_at = 0.0
        if remote is None and self.settings.provider == "openrouter":
            remote = OpenRouterClient(OpenRouterSettings.from_config(self.settings.openrouter))
        self.remote = remote

    # ------------------------------------------------------------------ provider
    def remote_active(self, role: str = "advisor") -> bool:
        """True when this role is answered by OpenRouter right now."""
        return (
            self.settings.mode != "off"
            and self.remote is not None
            and self.remote.usable()
            and bool(self.remote.model_for(role))
            and not self.remote.cooling(role)
        )

    def backend(self) -> str:
        """``openrouter``, ``local`` or ``off`` (offline backups), for the UI."""
        if self.remote_active():
            return "openrouter"
        return "local" if self.local_available() else "off"

    # ------------------------------------------------------------------ discovery
    def revision(self, repo: str) -> str | None:
        """Commit pinned by ``callverse llm-pull`` (None: latest cached snapshot)."""
        if not LOCK_FILE.exists():
            return None
        lock = json.loads(LOCK_FILE.read_text(encoding="utf-8"))
        for entry in lock.get("roles", {}).values():
            if entry.get("repo") == repo and entry.get("revision"):
                return str(entry["revision"])
        return None

    def downloaded(self, repo: str) -> bool:
        """Cached 30 s, so status calls stay cheap."""
        if time.time() - self._checked_at > 30:
            self._downloaded, self._checked_at = {}, time.time()
        if repo not in self._downloaded:
            try:
                self._downloaded[repo] = _is_downloaded(repo, self.revision(repo))
            except Exception:
                self._downloaded[repo] = False
        return self._downloaded[repo]

    def can_run(self) -> tuple[bool, str]:
        """(ok, reason) for the hardware: 4-bit weights need a CUDA GPU."""
        if self.settings.mode == "off":
            return False, "LLM mode is off (offline backups only)"
        gpu = gpu_info()
        if gpu is None and self.settings.device != "cpu":
            return False, "no CUDA GPU visible to PyTorch (offline backups are used)"
        return True, "ok"

    def resolve_model(self, role: str) -> str | None:
        """Model that answers a role now: its OpenRouter model, else the local one."""
        if self.remote_active(role):
            return self.remote.model_for(role)  # type: ignore[union-attr]
        return self.resolve_local_model(role)

    def resolve_local_model(self, role: str) -> str | None:
        """Pinned local model of a role, or its first downloaded fallback."""
        for repo in [self.settings.models[role], *self.settings.fallbacks.get(role, [])]:
            if self.downloaded(repo):
                return repo
        return None

    def local_available(self) -> bool:
        """True when the local advisor model can run here (the backup)."""
        ok, _ = self.can_run()
        return ok and self.resolve_local_model("advisor") is not None

    def available(self) -> bool:
        """True when the advisor can use an LLM: OpenRouter or the local model."""
        return self.remote_active() or self.local_available()

    def unavailable_reason(self) -> str | None:
        if self.available():
            return None
        ok, reason = self.can_run()
        notes = [f"OpenRouter: {self.remote.unusable_reason()}"] if self.remote is not None else []
        if not ok:
            notes.append(reason)
        else:
            missing = [r for r in self.settings.models if self.resolve_local_model(r) is None]
            if missing:
                missing_text = ", ".join(missing)
                notes.append(f"local weights not downloaded for {missing_text}: run `callverse llm-pull`")
        return "; ".join(notes) or None

    def _options(self, repo: str) -> ModelOptions:
        entry = self.settings.catalog.get(repo, {})
        return ModelOptions(
            chat_template_kwargs=dict(entry.get("chat_template_kwargs", {})),
            tools_kwarg=str(entry.get("tools_kwarg", "tools")),
            tool_call_opener=str(entry.get("tool_call_opener", ModelOptions.tool_call_opener)),
        )

    def load(self, role: str):
        """Load (once) the local model of a role."""
        repo = self.resolve_local_model(role)
        if repo is None:
            raise LLMUnavailableError(
                f"No model downloaded for role '{role}' (pinned {self.settings.models[role]}); "
                "run `callverse llm-pull`."
            )
        return self.pool.get(repo, self.revision(repo), self.settings.device, self._options(repo))

    def warmup(self) -> dict[str, Any]:
        """Load every role's local model now (first chat is then fast); nothing to load
        when OpenRouter answers."""
        for role in self.settings.models:
            if not self.remote_active(role):
                self.load(role)
        return self.status()

    def status(self) -> dict[str, Any]:
        """Provider, hardware and per-role model details (for the API and the CLI)."""
        remote = None
        if self.remote is not None:
            remote = {
                "configured": bool(self.remote.key),
                "usable": self.remote.usable(),
                "reason": self.remote.unusable_reason(),
                "models": {r: self.remote.settings.models_for(r) for r in self.remote.settings.models},
                "resting": [role for role in self.remote.settings.models if self.remote.cooling(role)],
                "quota": self.remote.quota(),
                "last_error": self.remote.last_error,
            }
        if self.remote_active():
            roles = {}
            for role in self.remote.settings.models:  # type: ignore[union-attr]
                model, *fallbacks = self.remote.settings.models_for(role)  # type: ignore[union-attr]
                info = self.settings.catalog.get(model, {})
                roles[role] = {
                    "pinned": model,
                    "repo": model,
                    "fallbacks": fallbacks,
                    "downloaded": True,
                    "loaded": True,
                    "revision": None,
                    "base_model": model,
                    "family": info.get("family"),
                    "parameters": info.get("parameters"),
                    "license": info.get("license"),
                    "footprint_mb": None,
                    "quantization": info.get("hosting", "hosted"),
                    "device": "OpenRouter",
                    "local_backup": self.settings.models.get(role),
                }
            return {
                "provider": "OpenRouter (hosted open models, free tier)",
                "backend": "openrouter",
                "profile": self.settings.profile,
                "mode": self.settings.mode,
                "available": True,
                "reason": None,
                "gpu": gpu_info(),
                "roles": roles,
                "openrouter": remote,
            }
        loaded = self.pool.loaded()
        roles = {}
        for role, pinned in self.settings.models.items():
            repo = self.resolve_local_model(role)
            info = self.settings.catalog.get(repo or pinned, {})
            model = loaded.get(repo or "")
            roles[role] = {
                "pinned": pinned,
                "repo": repo,
                "downloaded": repo is not None,
                "loaded": model is not None,
                "revision": self.revision(repo) if repo else None,
                "base_model": info.get("base_model", pinned),
                "family": info.get("family"),
                "parameters": info.get("parameters"),
                "license": info.get("license"),
                "footprint_mb": model.footprint_mb if model else None,
                "quantization": model.quantization if model else info.get("quantization"),
                "device": model.device if model else None,
            }
        return {
            "provider": "Hugging Face transformers (local)",
            "backend": self.backend(),
            "profile": self.settings.profile,
            "mode": self.settings.mode,
            "available": self.available(),
            "reason": self.unavailable_reason(),
            "gpu": gpu_info(),
            "roles": roles,
            "openrouter": remote,
        }

    def model_digests(self) -> dict[str, Any]:
        """Commit of each pinned model, for ``llm_models.lock.json``."""
        from huggingface_hub import scan_cache_dir

        cached = {repo.repo_id: repo for repo in scan_cache_dir().repos}
        roles = {}
        for role, pinned in self.settings.models.items():
            repo = self.resolve_local_model(role) or pinned
            info = self.settings.catalog.get(repo, {})
            entry = cached.get(repo)
            revision = max(entry.revisions, key=lambda r: r.last_modified) if entry else None
            roles[role] = {
                "repo": repo,
                "revision": revision.commit_hash if revision else None,
                "size_bytes": revision.size_on_disk if revision else None,
                "base_model": info.get("base_model"),
                "family": info.get("family"),
                "license": info.get("license"),
            }
        return {"provider": "huggingface/transformers", "profile": self.settings.profile, "roles": roles}

    # ----------------------------------------------------------------------- chat
    def chat(
        self,
        role: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        json_mode: bool = False,
        agent: str | None = None,
        temperature: float | None = None,
        on_token: Callable[[str], None] | None = None,
        tool_choice: str | None = None,
    ) -> LLMResponse:
        """One chat completion for an agent role (``client``, ``advisor``, ``judge``).

        ``on_token`` receives the visible text as it is generated (tool-call
        markup is hidden), for live streaming to the UI. ``tool_choice``: ``None`` or
        ``"auto"`` (the model may answer or call a tool) or ``"required"`` (it must call
        one of ``tools``, and still chooses which one).
        """
        if tool_choice not in (None, "auto", "required"):
            raise ValueError(f"tool_choice must be 'auto' or 'required', not {tool_choice!r}")
        if self.settings.mode == "off":
            raise LLMUnavailableError("LLM mode is off (offline backups only)")
        if self.remote_active(role):
            try:
                return self._chat_remote(
                    role, messages, tools, json_mode, agent, temperature, on_token, tool_choice
                )
            except OpenRouterUnavailable as error:
                # Backup: the same call on the local model (or the agents' templates).
                failure = {"agent": agent or role, "provider": "openrouter", "error": str(error)[:300]}
                self.tracer.record(failure)
                if not self.local_available():
                    raise LLMUnavailableError(f"OpenRouter: {error}; no local model can run") from error
        ok, reason = self.can_run()
        if not ok:
            raise LLMUnavailableError(reason)
        repo = self.resolve_local_model(role)
        if repo is None:
            raise LLMUnavailableError(self.unavailable_reason() or f"no model for role '{role}'")
        temperature = self.settings.temperature if temperature is None else temperature
        max_new_tokens = self.settings.max_new_tokens.get(role, 256)
        payload: dict[str, Any] = {
            "model": repo,
            "revision": self.revision(repo),
            "messages": messages,
            "tools": tools or None,
            "json_mode": json_mode,
            "temperature": temperature,
            "seed": self.settings.seed,
            "max_new_tokens": max_new_tokens,
        }
        if tool_choice == "required":  # only then, so earlier cached answers keep their keys
            payload["tool_choice"] = tool_choice
        key = cache_key(payload)
        if self.cache is not None:
            hit = self.cache.get(key)
            if hit is not None:
                result = LLMResponse(**{**hit, "cached": True, "latency_ms": 0.0})
                if on_token and result.content:
                    on_token(result.content)
                self._trace(agent or role, result, messages)
                return result

        gate = StreamGate(on_token) if on_token else None
        with timer() as elapsed:
            try:
                model = self.load(role)
                with self.pool.generate_lock:
                    raw, prompt_tokens, completion_tokens = model.generate(
                        messages,
                        tools,
                        json_mode,
                        temperature,
                        self.settings.seed,
                        max_new_tokens,
                        gate,
                        tool_choice=tool_choice,
                    )
            except LLMUnavailableError:
                raise
            except Exception as error:
                self.tracer.record({"agent": agent or role, "model": repo, "error": str(error)[:500]})
                raise LLMUnavailableError(f"Local model call failed: {error}") from error
        if gate is not None:
            gate.finish()
        if tools:
            content, calls = parse_tool_calls(raw, {t["function"]["name"] for t in tools})
        else:
            content, calls = strip_thinking(raw), []
        result = LLMResponse(
            content=content,
            tool_calls=calls,
            model=repo,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
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

    def _chat_remote(
        self,
        role: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        json_mode: bool,
        agent: str | None,
        temperature: float | None,
        on_token: Callable[[str], None] | None,
        tool_choice: str | None,
    ) -> LLMResponse:
        """One call on OpenRouter: same cache, streaming and trace as the local path."""
        assert self.remote is not None
        temperature = self.settings.temperature if temperature is None else temperature
        max_new_tokens = self.settings.max_new_tokens.get(role, 256)
        payload: dict[str, Any] = {
            "provider": "openrouter",
            "model": self.remote.settings.models_for(role),
            "reasoning": self.remote.settings.reasoning,
            "messages": messages,
            "tools": tools or None,
            "json_mode": json_mode,
            "temperature": temperature,
            "seed": self.settings.seed,
            "max_new_tokens": max_new_tokens,
        }
        if tool_choice == "required":
            payload["tool_choice"] = tool_choice
        key = cache_key(payload)  # the API key is never part of it
        if self.cache is not None:
            hit = self.cache.get(key)
            if hit is not None:
                result = LLMResponse(**{**hit, "cached": True, "latency_ms": 0.0})
                if on_token and result.content:
                    on_token(result.content)
                self._trace(agent or role, result, messages, provider="openrouter")
                return result
        gate = StreamGate(on_token) if on_token else None
        with timer() as elapsed:
            completion = self.remote.chat(
                role,
                messages,
                tools,
                json_mode,
                temperature,
                self.settings.seed,
                max_new_tokens,
                tool_choice,
                gate,
            )
        if gate is not None:
            gate.finish()
        names = {t["function"]["name"] for t in tools or []}
        calls = [c for c in completion.tool_calls if c["name"] in names]
        if tools and not calls:  # some models write the call as text instead of a native call
            content, calls = parse_tool_calls(completion.content, names)
        else:
            content = strip_thinking(completion.content)
        result = LLMResponse(
            content=content,
            tool_calls=calls,
            model=completion.model,  # the model that answered (a fallback when the first was busy)
            prompt_tokens=completion.prompt_tokens,
            completion_tokens=completion.completion_tokens,
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
        self._trace(agent or role, result, messages, provider="openrouter")
        return result

    def _trace(
        self, agent: str, result: LLMResponse, messages: list[dict[str, Any]], provider: str = "local"
    ) -> None:
        last = str(messages[-1].get("content", "")) if messages else ""
        self.tracer.record(
            {
                "agent": agent,
                "provider": provider,
                "model": result.model,
                "prompt_tokens": result.prompt_tokens,
                "completion_tokens": result.completion_tokens,
                "latency_ms": round(result.latency_ms, 1),
                "tokens_per_second": round(result.completion_tokens / (result.latency_ms / 1000), 1)
                if result.latency_ms
                else None,
                "cached": result.cached,
                "tool_calls": [c["name"] for c in result.tool_calls],
                "cost_eur": 0.0,  # local model or OpenRouter free tier: no per-token cost
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
