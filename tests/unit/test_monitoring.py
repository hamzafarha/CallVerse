"""The AI monitoring page's numbers, checked on small made-up data (no real trace or chat needed)."""

import pytest

from callverse.evaluation.monitoring import build_report, provider_of

SETTINGS = {
    "reference_price": {"name": "test price", "input_per_million_usd": 1.0, "output_per_million_usd": 2.0},
    "thresholds": {
        "llm_p95_latency_seconds": {"warn": 10, "alert": 20, "better": "lower"},
        "llm_error_rate": {"warn": 0.05, "alert": 0.15, "better": "lower"},
        "fallback_rate": {"warn": 0.2, "alert": 0.4, "better": "lower"},
        "tool_success_rate": {"warn": 0.95, "alert": 0.85, "better": "higher"},
        "quality_overall": {"warn": 3.5, "alert": 3.0, "better": "higher"},
        "routing_accuracy": {"warn": 0.85, "alert": 0.7, "better": "higher"},
    },
}
DAY = 1_700_000_000.0  # a fixed moment (seconds)


def call(
    agent="advisor",
    latency=1000.0,
    prompt=1000,
    completion=500,
    cached=False,
    error=None,
    provider="openrouter",
):
    """One traced LLM call."""
    return {
        "_t": DAY,
        "agent": agent,
        "model": "m",
        "provider": provider,
        "latency_ms": latency,
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "cached": cached,
        "error": error,
        "cost_eur": 0.0,
    }


def chat(
    mode="llm",
    overall=4.0,
    csat=4,
    resolved=True,
    intent=("track_order", "track_order"),
    conf=0.95,
    caller="llm",
):
    """One saved chat: a customer message, an advisor answer with one tool call, routing and a scorecard."""
    true_intent, predicted = intent
    tools = [{"name": "lookup_order", "ok": True, "caller": caller, "via": "mcp", "latency_ms": 20.0}]
    return {
        "_t": DAY,
        "_source": "live",
        "profile": {"intent": true_intent, "intent_group": "wismo"},
        "routing": {"predicted_intent": predicted, "predicted_group": "wismo", "confidence": conf},
        "messages": [
            {"speaker": "customer", "text": "Where is my parcel?", "meta": {}},
            {
                "speaker": "advisor",
                "text": "It is on its way.",
                "meta": {
                    "mode": mode,
                    "model": "m",
                    "tokens": 1000,
                    "latency_ms": 2000.0,
                    "sources": ["faq__s1"],
                    "tools": tools,
                },
            },
        ],
        "scorecard": {
            "overall": overall,
            "scores": {"relevance": overall},
            "resolved": resolved,
            "correct": True,
            "judge": "rules",
        },
        "kpis": {
            "fcr": resolved,
            "intent_correct": true_intent == predicted,
            "action_correct": True,
            "drafts_rejected": 0,
        },
        "csat": csat,
    }


def test_llm_latency_cost_and_alerts():
    """Latency ignores cached calls and errors; the estimate uses the reference price; the alerts colour."""
    traces = [
        call(latency=1000),
        call(latency=3000),
        call(cached=True, latency=0),
        call(error="busy", latency=50),
    ]
    report = build_report(traces, [], {}, SETTINGS)
    llm = report["llm"]
    assert llm["calls"] == 4 and llm["error_rate"] == 0.25 and llm["cache_rate"] == 0.25
    assert llm["p50_ms"] == 2000.0  # only the two real answers count
    cost = report["cost"]
    assert cost["prompt_tokens"] == 4000 and cost["completion_tokens"] == 2000
    assert cost["estimate_usd"] == pytest.approx(4000 / 1e6 * 1.0 + 2000 / 1e6 * 2.0)
    levels = {a["metric"]: a["level"] for a in report["alerts"]}
    assert levels["llm_error_rate"] == "alert" and levels["llm_p95_latency_seconds"] == "ok"
    assert levels["quality_overall"] == "none"  # no chat: nothing to judge


def test_chats_fallback_tools_routing_and_business():
    """The fallback rate, who chose the tools, routing accuracy and calibration, judge vs customer."""
    chats = [
        chat(overall=5.0, csat=5),
        chat(overall=4.0, csat=4, caller="code"),
        chat(
            mode="template_fallback",
            overall=3.0,
            csat=2,
            resolved=False,
            intent=("track_order", "track_delivery"),
            conf=0.6,
        ),
    ]
    report = build_report([call()], chats, {}, SETTINGS)
    assert report["advisor"]["fallback_rate"] == pytest.approx(1 / 3, abs=1e-3)
    tools = report["tools"]
    assert tools["calls"] == 3 and tools["success_rate"] == 1.0
    assert tools["callers"] == {"AI": 2, "pipeline": 1} and tools["rows"][0]["mcp_share"] == 1.0
    routing = report["routing"]
    assert routing["accuracy"] == pytest.approx(2 / 3, abs=1e-3)
    assert routing["mistakes"] == [{"true": "track_order", "predicted": "track_delivery", "chats": 1}]
    assert (
        routing["matrix"][0][0] == 3
    )  # all three are "where is my order" problems, routed in the same group
    high = next(b for b in routing["confidence"] if b["from"] == 0.9)
    assert high["chats"] == 2 and high["accuracy"] == 1.0
    assert report["judge_vs_customer"]["chats"] == 3 and report["judge_vs_customer"]["pearson"] > 0.9
    assert report["quality"]["overall"] == pytest.approx(4.0) and report["quality"]["fcr"] == pytest.approx(
        2 / 3, abs=1e-3
    )
    business = report["business"]
    assert business["resolved_chats"] == 2 and business["tokens_per_resolved"] == 1000
    assert business["ai_seconds_per_resolved"] == 2.0
    assert report["rag"]["live"]["cited_share"] == 1.0


def test_old_trace_lines_get_their_provider_from_the_model():
    """The oldest trace lines have no provider: the model's name tells."""
    assert provider_of({"model": "nvidia/nemotron-3.5-super-vl:free"}) == "openrouter"
    assert provider_of({"model": "unsloth/SmolLM3-3B-bnb-4bit"}) == "local"
    assert provider_of({"provider": "openrouter", "model": "x"}) == "openrouter"
