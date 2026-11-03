"""OpenRouter connector, tested against a fake OpenRouter server (no network, no real key)."""
# Tests llm/openrouter.py and the fallback in llm/client.py. httpx.MockTransport plays the OpenRouter server:
# no network, no real key.

import json
from dataclasses import replace

import httpx
import pytest

from callverse.llm import LLMClient, LLMUnavailableError, load_llm_settings
from callverse.llm.openrouter import (
    OpenRouterClient,
    OpenRouterSettings,
    OpenRouterUnavailable,
    to_openai_messages,
)

FAKE_KEY = "test-key-not-real"
MODELS = {
    "advisor": "google/gemma-4-31b-it:free",
    "client": "google/gemma-4-26b-a4b-it:free",
    "judge": "nvidia/nemotron-3.5-super-vl:free",
}
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "lookup_order",
            "parameters": {"type": "object", "properties": {"order_id": {"type": "string"}}},
        },
    }
]
TOOL_CALL_STREAM = [
    {"model": MODELS["advisor"], "choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"name": "lookup_order", "arguments": '{"order_'}}]}}]},  # noqa: E501
    {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": 'id": "abc"}'}}]}}]},
    {"choices": [], "usage": {"prompt_tokens": 120, "completion_tokens": 9}},
]  # fmt: skip


@pytest.fixture(autouse=True)
def fake_key(monkeypatch):
    """Every test runs with a fake API key (autouse fixture), never a real one."""
    monkeypatch.setenv("OPENROUTER_API_KEY", FAKE_KEY)


def sse(chunks: list[dict]) -> bytes:
    """A streamed answer as OpenRouter sends it (with a keep-alive comment)."""
    body = ": OPENROUTER PROCESSING\n\n" + "".join(f"data: {json.dumps(c)}\n\n" for c in chunks)
    return (body + "data: [DONE]\n\n").encode()


def make_client(handler, sleeps: list | None = None) -> OpenRouterClient:
    """An OpenRouter client that talks to the fake server; pauses are recorded instead of slept."""
    return OpenRouterClient(
        OpenRouterSettings(models=MODELS, min_interval_seconds=0),
        transport=httpx.MockTransport(handler),
        sleep=(sleeps if sleeps is not None else []).append,
    )


def chat(client: OpenRouterClient, **kwargs):
    """One chat call with simple default arguments."""
    defaults = dict(
        role="advisor",
        messages=[{"role": "user", "content": "Where is my order?"}],
        tools=None,
        json_mode=False,
        temperature=0.2,
        seed=42,
        max_tokens=64,
    )
    return client.chat(**{**defaults, **kwargs})


def error(status: int, message: str) -> httpx.Response:
    """A fake OpenRouter error response."""
    return httpx.Response(status, json={"error": {"code": status, "message": message}})


# ------------------------------------------------------------------- messages
def test_messages_get_one_system_message_and_linked_tool_calls() -> None:
    """Messages are sent with one system message, and tool results are linked to their calls."""
    messages = [
        {"role": "system", "content": "rules"},
        {"role": "user", "content": "where is it?"},
        {"role": "system", "content": "POLICY DECISION"},
        {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "lookup_order", "arguments": {"order_id": "abc"}}}]},  # noqa: E501
        {"role": "tool", "content": '{"status_now": "shipped"}', "tool_name": "lookup_order"},
    ]  # fmt: skip
    out = to_openai_messages(messages)
    assert out[0] == {"role": "system", "content": "rules\n\nPOLICY DECISION"}
    assert [m["role"] for m in out] == ["system", "user", "assistant", "tool"]
    call = out[2]["tool_calls"][0]
    assert call["id"] == "call_1" and json.loads(call["function"]["arguments"]) == {"order_id": "abc"}
    assert out[3]["tool_call_id"] == "call_1"


# ----------------------------------------------------------------- streaming
def test_streamed_text_is_forwarded_and_native_tool_calls_are_assembled() -> None:
    """Streamed text is forwarded piece by piece; tool calls split across chunks are put back together."""
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        chunks = [{"choices": [{"delta": {"content": text}}]} for text in ("Let me ", "check.")]
        return httpx.Response(200, content=sse(chunks + TOOL_CALL_STREAM))

    tokens: list[str] = []
    answer = chat(make_client(handler), tools=TOOLS, tool_choice="required", on_token=tokens.append)
    assert answer.content == "Let me check." and tokens == ["Let me ", "check."]
    assert answer.tool_calls == [{"name": "lookup_order", "arguments": {"order_id": "abc"}}]
    assert (answer.prompt_tokens, answer.completion_tokens) == (120, 9)
    assert seen["auth"] == f"Bearer {FAKE_KEY}"
    body = seen["body"]
    assert body["model"] == MODELS["advisor"] and body["stream"] is True
    assert body["tools"] == TOOLS and body["tool_choice"] == "required"


def test_json_mode_asks_for_a_json_object() -> None:
    """JSON mode asks the API for a JSON object."""
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(200, content=sse([{"choices": [{"delta": {"content": '{"ok": true}'}}]}]))

    assert chat(make_client(handler), role="judge", json_mode=True).content == '{"ok": true}'
    assert seen["response_format"] == {"type": "json_object"} and seen["model"] == MODELS["judge"]


# --------------------------------------------------------- limits and errors
def test_a_busy_free_model_is_retried_after_a_pause() -> None:
    """HTTP 429 (busy free model): the call is retried after a pause."""
    answers = iter([error(429, "Rate limit exceeded: free-models-per-min."), None])
    sleeps: list = []

    def handler(request: httpx.Request) -> httpx.Response:
        ok = sse([{"choices": [{"delta": {"content": "ok"}}]}])
        return next(answers) or httpx.Response(200, content=ok)

    assert chat(make_client(handler, sleeps)).content == "ok"
    assert len(sleeps) == 1  # one pause before the retry


def test_the_daily_quota_stops_openrouter_until_tomorrow() -> None:
    """When the daily quota is used up, OpenRouter is not called again until the next day."""
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return error(429, "Rate limit exceeded: free-models-per-day. Add 10 credits to unlock 1000 requests.")

    client = make_client(handler)
    with pytest.raises(OpenRouterUnavailable, match="daily"):
        chat(client)
    assert not client.usable() and "daily" in client.unusable_reason()
    with pytest.raises(OpenRouterUnavailable):
        chat(client)
    assert len(calls) == 1  # no more requests once the quota is gone


def test_a_rejected_key_disables_openrouter() -> None:
    """A rejected key (HTTP 401) switches OpenRouter off."""
    client = make_client(lambda request: error(401, "No auth credentials found"))
    with pytest.raises(OpenRouterUnavailable, match="rejected"):
        chat(client)
    assert not client.usable()


def test_no_key_means_openrouter_is_skipped(monkeypatch) -> None:
    """Without a key, OpenRouter is skipped."""
    monkeypatch.delenv("OPENROUTER_API_KEY")
    client = make_client(lambda request: pytest.fail("no request without a key"))
    assert not client.usable() and "OPENROUTER_API_KEY" in client.unusable_reason()


def test_fallback_models_reasoning_off_and_the_model_that_answered() -> None:
    """The request lists the fallback models with reasoning off, and the reply records which model
    answered.
    """
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        chunk = {"model": "backup/model:free", "choices": [{"delta": {"content": "ok"}}]}
        return httpx.Response(200, content=sse([chunk]))

    settings = OpenRouterSettings(
        models={"advisor": ["first/model:free", "backup/model:free"]},
        min_interval_seconds=0,
        reasoning={"enabled": False},
    )
    client = OpenRouterClient(settings, transport=httpx.MockTransport(handler))
    answer = chat(client)
    assert seen["models"] == ["first/model:free", "backup/model:free"] and "model" not in seen
    assert seen["reasoning"] == {"enabled": False}
    assert answer.model == "backup/model:free" and client.model_for("advisor") == "first/model:free"


def test_a_role_rests_after_staying_rate_limited() -> None:
    """A role that stays rate limited rests for the cooldown (the local backup answers meanwhile)."""
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return error(429, "Provider returned error")

    client = make_client(handler)
    with pytest.raises(OpenRouterUnavailable, match="busy"):
        chat(client)
    assert client.cooling("advisor") and not client.cooling("judge")
    with pytest.raises(OpenRouterUnavailable, match="resting"):
        chat(client)
    assert len(requests) == 3  # 1 try + 2 retries, then no request while resting


def test_quota_reports_the_free_requests_left() -> None:
    """The quota reports how many free requests are left today."""
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/key")
        daily = {"used": 12, "limit": 50}
        return httpx.Response(200, json={"data": {"is_free_tier": True, "free_model_daily_requests": daily}})

    assert make_client(handler).quota() == {"used": 12, "limit": 50, "remaining": 38, "is_free_tier": True}


# ------------------------------------------------------------- the LLM client
def llm_client(tmp_path, handler) -> LLMClient:
    """LLMClient with OpenRouter as the provider, the fake server, and a cache in a temporary folder."""
    settings = replace(load_llm_settings(), mode="auto", provider="openrouter", cache=True)
    return LLMClient(settings, trace_dir=tmp_path, remote=make_client(handler))


def test_llm_client_answers_from_openrouter_and_caches_without_the_key(tmp_path) -> None:
    """LLMClient answers from OpenRouter and caches the answer; the key is never stored in the cache."""
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, content=sse(TOOL_CALL_STREAM))

    llm = llm_client(tmp_path, handler)
    assert llm.available() and llm.backend() == "openrouter"
    assert llm.resolve_model("advisor") == MODELS["advisor"]
    messages = [{"role": "user", "content": "Order abc please"}]
    first = llm.chat("advisor", messages, tools=TOOLS, tool_choice="required")
    again = llm.chat("advisor", messages, tools=TOOLS, tool_choice="required")
    assert first.tool_calls == [{"name": "lookup_order", "arguments": {"order_id": "abc"}}]
    assert first.model == MODELS["advisor"] and again.cached and len(requests) == 1
    for stored in tmp_path.iterdir():  # the answer cache and the trace
        assert FAKE_KEY.encode() not in stored.read_bytes()


def test_llm_client_falls_back_to_the_local_model(tmp_path, monkeypatch) -> None:
    """When OpenRouter cannot answer, LLMClient falls back to the local model."""
    def quota_gone(request: httpx.Request) -> httpx.Response:
        return error(429, "Rate limit exceeded: free-models-per-day")

    llm = llm_client(tmp_path / "a", quota_gone)
    monkeypatch.setattr(llm, "local_available", lambda: True)
    monkeypatch.setattr(llm, "can_run", lambda: (False, "no CUDA GPU (test)"))
    with pytest.raises(LLMUnavailableError, match=r"no CUDA GPU \(test\)"):  # the local path was taken
        llm.chat("advisor", [{"role": "user", "content": "hi"}])
    assert llm.backend() != "openrouter"  # skipped for the rest of the day

    no_local = llm_client(tmp_path / "b", quota_gone)
    monkeypatch.setattr(no_local, "local_available", lambda: False)
    with pytest.raises(LLMUnavailableError, match="OpenRouter"):  # the agents then use their templates
        no_local.chat("advisor", [{"role": "user", "content": "hello"}])


def test_status_shows_the_hosted_models_and_the_quota(tmp_path, monkeypatch) -> None:
    """The status shows the hosted models and the quota (for the back office)."""
    from callverse.llm import client as client_module

    monkeypatch.setattr(client_module, "gpu_info", lambda: None)
    quota = {"data": {"free_model_daily_requests": {"used": 3, "limit": 50}}}
    llm = llm_client(tmp_path, lambda request: httpx.Response(200, json=quota))
    status = llm.status()
    assert status["backend"] == "openrouter" and status["available"]
    assert status["roles"]["judge"]["repo"] == MODELS["judge"]
    assert status["roles"]["advisor"]["local_backup"] == llm.settings.models["advisor"]
    assert status["openrouter"]["quota"]["remaining"] == 47
