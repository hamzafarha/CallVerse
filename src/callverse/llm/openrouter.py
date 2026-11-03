"""OpenRouter: hosted open models through one OpenAI-compatible API (main LLM provider).

Each agent role (advisor, client, judge) gets a model from ``configs/agents.yaml``.
Free model variants (ids ending in ``:free``) cost nothing but are rate limited:
20 requests per minute, and 50 per day (1,000 per day once at least $10 of credits
were bought, all time). So this client:

- waits between requests (``min_interval_seconds``) to stay under the per-minute limit;
- retries a busy model (HTTP 429 per minute, 5xx, timeouts) with a growing pause;
- stops asking for the rest of the UTC day once the daily quota is used up, and stops
  for the session when the key is rejected; the LLM client then uses the local models.

The API key is read from ``OPENROUTER_API_KEY`` (``.env``) and only sent in the
Authorization header: never written to traces, caches or logs.
"""

# How to read this file:
# - OpenRouterSettings: the settings (models per role, timeouts, retries, pauses).
# - to_openai_messages(): converts our message list to the OpenAI chat format.
# - OpenRouterClient.chat(): sends one request (streamed), with throttling and retries.
# - _stream(): reads the answer piece by piece as it arrives (Server-Sent Events).
# - _fail(): decides what an HTTP error means: retry, pause for the day, or stop. OpenRouter is a "router" in
#   front of many AI providers: one API key, one API format, many models.
import json
import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

# httpx: a modern HTTP client for Python (like requests), with streaming support.
import httpx

# Name of the environment variable that holds the secret key (set in .env, never committed).
API_KEY_ENV = "OPENROUTER_API_KEY"


class OpenRouterUnavailable(RuntimeError):
    """OpenRouter cannot answer now (no key, quota used up, key rejected, network, busy)."""


@dataclass(frozen=True)
class OpenRouterSettings:
    """Section ``llm.openrouter`` of ``configs/agents.yaml``.

    ``models``: per role, one model id or a list (the first model, then the ones
    OpenRouter tries in the same request when it is busy or down).
    ``reasoning``: OpenRouter's reasoning option, e.g. ``{"enabled": False}``: answer
    directly, without hidden "thinking" tokens (reasoning models could otherwise spend
    the whole token budget thinking and return nothing).
    """

    models: dict[str, Any]
    # base_url: OpenRouter's address. timeout_seconds: give up on a request after this time. max_retries: how
    # many times a busy model is retried. min_interval_seconds: the minimum pause between two requests (3.1 s
    # = at most ~19 a minute, under the free limit of 20). cooldown_seconds: how long a role rests after its
    # models stayed busy.
    base_url: str = "https://openrouter.ai/api/v1"
    timeout_seconds: float = 60.0
    max_retries: int = 2
    min_interval_seconds: float = 3.1
    cooldown_seconds: float = 60.0
    reasoning: dict[str, Any] | None = None

    @classmethod
    def from_config(cls, raw: dict[str, Any]) -> "OpenRouterSettings":
        """Build the settings from the YAML dictionary (a missing value keeps its default)."""
        return cls(
            models={
                k: [str(m) for m in v] if isinstance(v, list) else str(v)
                for k, v in raw.get("models", {}).items()
            },
            base_url=str(raw.get("base_url", cls.base_url)).rstrip("/"),
            timeout_seconds=float(raw.get("timeout_seconds", cls.timeout_seconds)),
            max_retries=int(raw.get("max_retries", cls.max_retries)),
            min_interval_seconds=float(raw.get("min_interval_seconds", cls.min_interval_seconds)),
            cooldown_seconds=float(raw.get("cooldown_seconds", cls.cooldown_seconds)),
            reasoning=dict(raw["reasoning"]) if raw.get("reasoning") else None,
        )

    def models_for(self, role: str) -> list[str]:
        """The role's model ids as a list (a single id becomes a one-item list)."""
        value = self.models.get(role)
        return [value] if isinstance(value, str) else list(value or [])


def to_openai_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """CallVerse chat messages -> OpenAI format.

    All system messages are merged into one at the top (the agents add some mid-chat,
    e.g. the rules-engine decision; not every model accepts them there). Tool calls get
    ids and each tool result points to its call, as the API requires.
    """
    # 1) Merge every system message into one, placed first.
    system = [str(m.get("content", "")) for m in messages if m["role"] == "system"]
    out: list[dict[str, Any]] = [{"role": "system", "content": "\n\n".join(system)}] if system else []
    pending: list[str] = []
    count = 0
    # 2) Copy the other messages in order, converting tool calls and tool results.
    for message in messages:
        role = message["role"]
        if role == "system":
            continue
        # An assistant message that asked for tools: give each call an id (call_1, call_2, ...).
        if role == "assistant" and message.get("tool_calls"):
            calls = []
            for call in message["tool_calls"]:
                count += 1
                function = call.get("function", call)
                arguments = function.get("arguments") or {}
                calls.append(
                    {
                        "id": f"call_{count}",
                        "type": "function",
                        "function": {
                            "name": function["name"],
                            "arguments": arguments if isinstance(arguments, str) else json.dumps(arguments),
                        },
                    }
                )
                pending.append(f"call_{count}")
            out.append({"role": "assistant", "content": message.get("content") or "", "tool_calls": calls})
        # A tool result: link it to the oldest call still waiting for its result.
        elif role == "tool":
            call_id = pending.pop(0) if pending else f"call_{count}"
            out.append({"role": "tool", "tool_call_id": call_id, "content": str(message.get("content", ""))})
        else:
            out.append({"role": role, "content": str(message.get("content", ""))})
    return out


def _arguments(text: str) -> dict[str, Any]:
    """Tool-call arguments arrive as a JSON string: parse them (an invalid string gives {})."""
    try:
        value = json.loads(text) if text.strip() else {}
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


@dataclass
class Completion:
    """One OpenRouter answer."""

    content: str
    tool_calls: list[dict[str, Any]]
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0


@dataclass
class OpenRouterClient:
    """Chat completions on OpenRouter, with throttling, retries and quota tracking."""

    settings: OpenRouterSettings
    transport: httpx.BaseTransport | None = field(default=None, repr=False)  # tests: a fake server
    sleep: Callable[[float], None] = field(default=time.sleep, repr=False)
    # Private state (the underscore means "internal"): the HTTP connection, a lock, the time of the last
    # request, the day the quota ran out, why the client is disabled, the cached quota, and until when each
    # role rests.
    _http: httpx.Client | None = field(default=None, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)
    _last_request: float = field(default=0.0, init=False, repr=False)
    _quota_day: str | None = field(default=None, init=False, repr=False)  # UTC day the quota ran out
    _disabled: str | None = field(default=None, init=False, repr=False)  # e.g. key rejected
    _quota: tuple[float, dict[str, Any]] | None = field(default=None, init=False, repr=False)
    _cool_until: dict[str, float] = field(default_factory=dict, init=False, repr=False)
    last_error: str | None = field(default=None, init=False)

    # ------------------------------------------------------------------ state
    @property
    def key(self) -> str:
        """The API key, read fresh from the environment each time (never stored anywhere else)."""
        return os.environ.get(API_KEY_ENV, "").strip()

    def model_for(self, role: str) -> str | None:
        """The role's first model (the others are OpenRouter's fallbacks)."""
        models = self.settings.models_for(role)
        return models[0] if models else None

    def cooling(self, role: str) -> bool:
        """True while a role rests after its models stayed rate limited (the backup answers)."""
        return time.monotonic() < self._cool_until.get(role, 0.0)

    def unusable_reason(self) -> str | None:
        """Why OpenRouter is skipped right now (None: it can be used)."""
        # Three reasons to skip OpenRouter: no key, the key was rejected, or today's free quota is used up.
        if not self.key:
            return f"no {API_KEY_ENV} in .env"
        if self._disabled:
            return self._disabled
        if self._quota_day == _utc_day():
            return "free daily quota used up (resets at 00:00 UTC)"
        return None

    def usable(self) -> bool:
        """True when OpenRouter can be tried now."""
        return self.unusable_reason() is None

    def _client(self) -> httpx.Client:
        """One HTTP connection, created on first use and then reused (faster)."""
        if self._http is None:
            self._http = httpx.Client(timeout=self.settings.timeout_seconds, transport=self.transport)
        return self._http

    def _headers(self) -> dict[str, str]:
        """The key travels only in this Authorization header; X-Title names our app on OpenRouter."""
        return {"Authorization": f"Bearer {self.key}", "X-Title": "CallVerse"}

    # ------------------------------------------------------------------- quota
    def quota(self, max_age_seconds: float = 60.0) -> dict[str, Any] | None:
        """Free-model requests used / allowed today (GET /key), cached for a minute."""
        if not self.key:
            return None
        # Ask at most once a minute: the last answer is kept in self._quota.
        if self._quota and time.time() - self._quota[0] < max_age_seconds:
            return self._quota[1]
        try:
            response = self._client().get(f"{self.settings.base_url}/key", headers=self._headers())
            data = response.json().get("data", {}) if response.status_code == 200 else {}
        except (httpx.HTTPError, ValueError):
            return None
        # OpenRouter reports how many free-model requests were used today, and the daily limit.
        daily = data.get("free_model_daily_requests") or {}
        info = {
            "used": daily.get("used"),
            "limit": daily.get("limit"),
            "remaining": (daily["limit"] - daily["used"]) if {"used", "limit"} <= set(daily) else None,
            "is_free_tier": data.get("is_free_tier"),
        }
        self._quota = (time.time(), info)
        return info

    # -------------------------------------------------------------------- chat
    def chat(
        self,
        role: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        json_mode: bool,
        temperature: float,
        seed: int,
        max_tokens: int,
        tool_choice: str | None = None,
        on_token: Callable[[str], None] | None = None,
    ) -> Completion:
        """One streamed chat completion; raises ``OpenRouterUnavailable`` when it cannot answer."""
        # Step 1: refuse at once when OpenRouter cannot be used (the caller then uses the local model).
        reason = self.unusable_reason()
        if reason:
            raise OpenRouterUnavailable(reason)
        if self.cooling(role):
            rest = self.settings.cooldown_seconds
            raise OpenRouterUnavailable(f"{role} models rate limited, resting {rest:.0f} s")
        # Step 2: build the request body (OpenAI format).
        models = self.settings.models_for(role)
        if not models:
            raise OpenRouterUnavailable(f"no OpenRouter model configured for role '{role}'")
        # one model: "model"; several: OpenRouter tries them in order within the request
        body: dict[str, Any] = {"models": models} if len(models) > 1 else {"model": models[0]}
        body |= {
            "messages": to_openai_messages(messages),
            "temperature": temperature,
            "seed": seed,
            "max_tokens": max_tokens,
            # stream: receive the answer piece by piece (live typing in the UI); usage: get token counts.
            "stream": True,
            "usage": {"include": True},
        }
        # Tools: tool_choice "auto" lets the model answer OR call a tool; "required" forces a call.
        if tools:
            body["tools"] = tools
            body["tool_choice"] = tool_choice or "auto"
        # JSON mode: the model must answer with a JSON object (used by the Client agent and the judge).
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        if self.settings.reasoning:
            body["reasoning"] = self.settings.reasoning

        # Step 3: send, with retries. Each retry waits longer (2 s, 4 s, ...): "exponential backoff".
        for attempt in range(self.settings.max_retries + 1):
            self._throttle()
            try:
                return self._stream(body, on_token)
            except _Retry as retry:
                self.last_error = str(retry)
                if attempt == self.settings.max_retries:
                    # still busy: rest this role for a while, so the backup answers at once
                    self._cool_until[role] = time.monotonic() + self.settings.cooldown_seconds
                    raise OpenRouterUnavailable(f"OpenRouter busy: {retry}") from retry
                self.sleep(retry.wait or 2.0 * 2**attempt)
            except httpx.HTTPError as error:  # network down, timeout
                self.last_error = f"network: {error}"
                if attempt == self.settings.max_retries:
                    raise OpenRouterUnavailable(self.last_error) from error
                self.sleep(2.0 * 2**attempt)
        raise OpenRouterUnavailable("OpenRouter did not answer")  # pragma: no cover

    def _throttle(self) -> None:
        """At most one request every ``min_interval_seconds`` (free tier: 20 per minute)."""
        # The lock makes threads wait their turn, so two agents never send at the same moment.
        with self._lock:
            wait = self._last_request + self.settings.min_interval_seconds - time.monotonic()
            if wait > 0:
                self.sleep(wait)
            self._last_request = time.monotonic()

    def _stream(self, body: dict[str, Any], on_token: Callable[[str], None] | None) -> Completion:
        url = f"{self.settings.base_url}/chat/completions"
        # Open a streaming POST request. Any status other than 200 OK goes to _fail().
        with self._client().stream("POST", url, json=body, headers=self._headers()) as response:
            if response.status_code != 200:
                response.read()
                self._fail(response)
            text: list[str] = []
            calls: dict[int, dict[str, str]] = {}
            usage: dict[str, Any] = {}
            model = body.get("model") or body["models"][0]  # replaced by the model that answered
            # Server-Sent Events: the answer arrives as lines "data: {json}", and ends with "data: [DONE]".
            for line in response.iter_lines():
                if not line.startswith("data:"):
                    continue  # blank lines and ": OPENROUTER PROCESSING" keep-alives
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                chunk = json.loads(data)
                if chunk.get("error"):
                    raise _Retry(str(chunk["error"].get("message", chunk["error"])))
                usage = chunk.get("usage") or usage
                model = chunk.get("model", model)
                # Each chunk carries a small "delta": a few words of text, or a piece of a tool call.
                for choice in chunk.get("choices", []):
                    delta = choice.get("delta") or {}
                    if delta.get("content"):
                        text.append(delta["content"])
                        if on_token is not None:
                            on_token(delta["content"])
                    # Tool calls also arrive in pieces: glue together the name and the arguments of each call.
                    for part in delta.get("tool_calls") or []:
                        index = int(part.get("index", len(calls)))
                        slot = calls.setdefault(index, {"name": "", "arguments": ""})
                        function = part.get("function") or {}
                        slot["name"] += function.get("name") or ""
                        slot["arguments"] += function.get("arguments") or ""
        # Success: clear the last error and return the whole answer.
        self.last_error = None
        return Completion(
            content="".join(text),
            tool_calls=[
                {"name": c["name"], "arguments": _arguments(c["arguments"])}
                for _, c in sorted(calls.items())
                if c["name"]
            ],
            model=model,
            prompt_tokens=int(usage.get("prompt_tokens") or 0),
            completion_tokens=int(usage.get("completion_tokens") or 0),
        )

    def _fail(self, response: httpx.Response) -> None:
        """Turn an error status into a retry, a pause for the day, or a stop."""
        try:
            message = str(response.json().get("error", {}).get("message", response.text))
        except ValueError:
            message = response.text
        message = message[:300]
        status = response.status_code
        # 429 = too many requests. The daily quota is used up -> skip OpenRouter until 00:00 UTC. The per-
        # minute limit -> retry after the pause the server suggests (Retry-After header).
        if status == 429:
            if "per-day" in message or "per day" in message.lower() or "daily" in message.lower():
                self._quota_day = _utc_day()
                self.last_error = f"daily free quota used up: {message}"
                raise OpenRouterUnavailable(self.last_error)
            wait = response.headers.get("retry-after")
            raise _Retry(f"rate limited: {message}", float(wait) if wait and wait.isdigit() else None)
        # 401/403 = the key is wrong or revoked: stop using OpenRouter for this session.
        if status in (401, 403):
            self._disabled = f"API key rejected ({status}): {message}"
            self.last_error = self._disabled
            raise OpenRouterUnavailable(self._disabled)
        # 5xx (server error) or 408 (timeout): a temporary problem, worth a retry.
        if status >= 500 or status == 408:
            raise _Retry(f"server error {status}: {message}")
        # 400 bad request, 402 no credits, 404 no endpoint matching the privacy settings...
        self.last_error = f"HTTP {status}: {message}"
        raise OpenRouterUnavailable(self.last_error)


class _Retry(Exception):
    """A temporary failure worth retrying after a pause."""

    def __init__(self, message: str, wait: float | None = None) -> None:
        super().__init__(message)
        self.wait = wait


def _utc_day() -> str:
    """Today's date in UTC (the free quota resets at 00:00 UTC)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")
