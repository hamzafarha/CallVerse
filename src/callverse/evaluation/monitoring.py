"""AI monitoring: how the LLMs, the RAG, the tools and the agents behave, from data CallVerse already records.

Three sources, nothing new is measured:

- the LLM trace (artifacts/traces/llm_calls.jsonl): one line per LLM call (agent, model, provider, tokens,
  latency, cache hit, error);
- the saved chats: the live chats of the apps (artifacts/traces/live_sessions) and the evaluation runs
  (artifacts/traces/conversations), each with its messages, tool calls, routing and the Quality agent's
  scorecard;
- the offline results of the evaluation (artifacts/evaluations/*.csv): RAG retrieval and faithfulness, the
  advisor variants, and the judge's calibration against human labels.

monitoring_report() turns them into the numbers of the back office's AI monitoring page (GET /api/monitoring),
with the alert colours of configs/monitoring.yaml. build_report() does the counting itself, on data passed in,
so the tests can check it on small made-up data.
"""

# Words used below: p50 = the median (half the calls are faster); p95 = 95% of the calls are faster (the slow
# case); FCR = first contact resolution (solved in this chat, no handover); CSAT = the customer's rating
# (1-5); fallback = the LLM failed and a template answered instead.
import json
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from callverse.config import EVALUATION_DIR, TRACE_DIR, load_yaml
from callverse.orchestration.live import live_chats_dir

GROUPS = ["wismo", "cancel_refund", "post_delivery", "order_admin"]
CONFIDENCE_BINS = [(0.0, 0.5), (0.5, 0.7), (0.7, 0.9), (0.9, 1.01)]
CALLER = {"llm": "AI", "code": "pipeline", "safety_net": "safety net"}


# ----------------------------------------------------------------------------- small helpers
def _avg(values: Any) -> float | None:
    known = [float(v) for v in values if v is not None]
    return round(sum(known) / len(known), 4) if known else None


def _share(flags: Any) -> float | None:
    known = [bool(f) for f in flags if f is not None]
    return round(sum(known) / len(known), 4) if known else None


def _pct(values: list[float], q: float) -> float | None:
    return round(float(np.percentile(values, q)), 1) if values else None


def _day(seconds: float) -> str:
    return datetime.fromtimestamp(seconds).strftime("%Y-%m-%d")


def provider_of(row: dict[str, Any]) -> str:
    """OpenRouter or the local GPU. The oldest trace lines do not say: the model's name tells."""
    if row.get("provider"):
        return str(row["provider"])
    model = str(row.get("model") or "")
    if ":free" in model or "openrouter" in str(row.get("error") or "").lower():
        return "openrouter"
    return "local" if model else "unknown"


# ------------------------------------------------------------------------------- reading
def read_trace(path: Path | None = None) -> list[dict[str, Any]]:
    """Every traced LLM call, with its time in seconds (`_t`) and its provider."""
    path = path or TRACE_DIR / "llm_calls.jsonl"
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
            row["_t"] = datetime.fromisoformat(row["ts"]).timestamp()
        except (ValueError, KeyError, TypeError):
            continue
        row["provider"] = provider_of(row)
        if row.get("agent") == "judge":  # the oldest lines named the Quality agent "judge"
            row["agent"] = "quality"
        rows.append(row)
    return rows


def read_chats(source: str = "all") -> list[dict[str, Any]]:
    """The saved chats: "live" (the apps), "eval" (the evaluation runs) or "all", with their end time."""
    folders = []
    if source in ("live", "all"):
        folders.append(("live", live_chats_dir()))
    if source in ("eval", "all"):
        folders.append(("eval", TRACE_DIR / "conversations"))
    chats = []
    for kind, folder in folders:
        for path in folder.glob("*.json"):
            try:
                state = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue  # a file being written
            state["_t"] = state.get("ended_at") or path.stat().st_mtime
            state["_source"] = kind
            chats.append(state)
    return chats


def offline_results(folder: Path | None = None) -> dict[str, list[dict[str, Any]]]:
    """The evaluation's result tables used by the page (empty when a table was not produced)."""
    folder = folder or EVALUATION_DIR

    def table(name: str) -> list[dict[str, Any]]:
        path = folder / f"{name}.csv"
        if not path.exists():
            return []
        frame = pd.read_csv(path)
        return frame.astype(object).where(frame.notna(), None).to_dict("records")

    return {
        "retrieval": table("dso2_rag_retrieval"),
        "variants": table("dso2_agents_summary"),
        "calibration": table("dso2_judge_calibration_agreement"),
        "components": [
            r for r in table("component_metrics") if r.get("component") in ("RAG advisor", "LLM judge")
        ],
    }


# ------------------------------------------------------------------------------- the report
def monitoring_report(
    period_hours: float | None = None, source: str = "all", now: float | None = None
) -> dict[str, Any]:
    """The AI monitoring page: the last `period_hours` (None = everything), chats of one `source`."""
    now = now or time.time()
    since = now - period_hours * 3600 if period_hours else None
    traces = [r for r in read_trace() if since is None or r["_t"] >= since]
    chats = [c for c in read_chats(source) if since is None or c["_t"] >= since]
    report = build_report(traces, chats, offline_results(), load_yaml("monitoring"))
    report["filters"] = {"period_hours": period_hours, "source": source, "generated_at": now}
    return report


def build_report(
    traces: list[dict[str, Any]],
    chats: list[dict[str, Any]],
    offline: dict[str, list[dict[str, Any]]],
    settings: dict[str, Any],
) -> dict[str, Any]:
    """Every number of the page, from the LLM calls, the chats, and the offline results."""
    llm = _llm_section(traces)
    cost = _cost_section(traces, settings["reference_price"])
    facts = [_chat_facts(chat) for chat in chats]
    advisor = _advisor_section(chats)
    tools = _tools_section(chats, facts)
    quality = _quality_section(facts, offline)
    routing = _routing_section(facts)
    engines = _engines_section(facts)
    pairs = _judge_vs_customer(facts)
    business = _business_section(facts, cost["usd_per_token"])
    alerts = _alerts(
        {
            "llm_p95_latency_seconds": None if llm["p95_ms"] is None else llm["p95_ms"] / 1000,
            "llm_error_rate": llm["error_rate"],
            "fallback_rate": advisor["fallback_rate"],
            "tool_success_rate": tools["success_rate"],
            "quality_overall": quality["overall"],
            "routing_accuracy": routing["accuracy"],
        },
        settings["thresholds"],
    )
    return {
        "headline": {
            "llm_calls": llm["calls"],
            "chats": len(chats),
            "p50_ms": llm["p50_ms"],
            "fallback_rate": advisor["fallback_rate"],
            "tokens": cost["prompt_tokens"] + cost["completion_tokens"],
            "real_cost_eur": cost["real_eur"],
            "estimate_usd": cost["estimate_usd"],
            "tool_success_rate": tools["success_rate"],
            "quality": quality["overall"],
            "routing_accuracy": routing["accuracy"],
        },
        "llm": llm,
        "cost": cost,
        "advisor": advisor,
        "rag": {
            "offline": offline.get("retrieval", []),
            "components": offline.get("components", []),
            "live": advisor["rag"],
        },
        "tools": tools,
        "quality": quality,
        "routing": routing,
        "grounding": _grounding_section(facts, tools),
        "engines": engines,
        "variants": offline.get("variants", []),
        "judge_vs_customer": pairs,
        "business": business,
        "alerts": alerts,
        "reference_price": settings["reference_price"],
    }


# -------------------------------------------------------------------------------- the LLMs
def _llm_section(traces: list[dict[str, Any]]) -> dict[str, Any]:
    """Calls, errors, cache hits and latency, per agent x model x provider, and the calls per day."""
    # Latency only of real answers: a cached call takes no time, an error has no answer.
    fresh = [
        r for r in traces if not r.get("error") and not r.get("cached") and r.get("latency_ms") is not None
    ]
    groups: dict[tuple, list[dict[str, Any]]] = defaultdict(list)
    for row in traces:
        groups[(row.get("agent") or "?", row.get("model") or "none", row["provider"])].append(row)
    by_model = []
    for (agent, model, provider), rows in groups.items():
        times = [float(r["latency_ms"]) for r in rows if r in fresh]
        speeds = [r.get("tokens_per_second") for r in rows if r.get("tokens_per_second")]
        by_model.append(
            {
                "agent": agent,
                "model": model,
                "provider": provider,
                "calls": len(rows),
                "error_rate": _share(bool(r.get("error")) for r in rows),
                "cache_rate": _share(bool(r.get("cached")) for r in rows),
                "p50_ms": _pct(times, 50),
                "p95_ms": _pct(times, 95),
                "tokens_per_second": _avg(speeds),
                "prompt_tokens": sum(int(r.get("prompt_tokens") or 0) for r in rows),
                "completion_tokens": sum(int(r.get("completion_tokens") or 0) for r in rows),
            }
        )
    by_model.sort(key=lambda r: -r["calls"])
    by_agent = []
    for agent in sorted({r.get("agent") or "?" for r in traces}):
        times = [float(r["latency_ms"]) for r in fresh if (r.get("agent") or "?") == agent]
        by_agent.append(
            {
                "agent": agent,
                "calls": sum((r.get("agent") or "?") == agent for r in traces),
                "p50_ms": _pct(times, 50),
                "p95_ms": _pct(times, 95),
            }
        )
    per_day: dict[str, Counter] = defaultdict(Counter)
    for row in traces:
        per_day[_day(row["_t"])][row["provider"]] += 1
    errors = [
        {"ts": r.get("ts"), "agent": r.get("agent"), "model": r.get("model"), "error": str(r["error"])[:180]}
        for r in sorted(traces, key=lambda r: r["_t"])
        if r.get("error")
    ][-5:][::-1]
    all_times = [float(r["latency_ms"]) for r in fresh]
    return {
        "calls": len(traces),
        "error_rate": _share(bool(r.get("error")) for r in traces),
        "cache_rate": _share(bool(r.get("cached")) for r in traces),
        "p50_ms": _pct(all_times, 50),
        "p95_ms": _pct(all_times, 95),
        "by_model": by_model,
        "by_agent": by_agent,
        "per_day": [{"day": day, **counts} for day, counts in sorted(per_day.items())],
        "providers": sorted({r["provider"] for r in traces}),
        "errors": errors,
    }


def _cost_section(traces: list[dict[str, Any]], price: dict[str, Any]) -> dict[str, Any]:
    """Tokens per agent and per day; the real cost (free tier and local GPU) and the "if we paid" estimate."""

    def estimate(prompt: int, completion: int) -> float:
        return prompt / 1e6 * float(price["input_per_million_usd"]) + completion / 1e6 * float(
            price["output_per_million_usd"]
        )

    prompt = sum(int(r.get("prompt_tokens") or 0) for r in traces)
    completion = sum(int(r.get("completion_tokens") or 0) for r in traces)
    by_agent = []
    for agent in sorted({r.get("agent") or "?" for r in traces}):
        rows = [r for r in traces if (r.get("agent") or "?") == agent]
        p = sum(int(r.get("prompt_tokens") or 0) for r in rows)
        c = sum(int(r.get("completion_tokens") or 0) for r in rows)
        by_agent.append(
            {
                "agent": agent,
                "prompt_tokens": p,
                "completion_tokens": c,
                "estimate_usd": round(estimate(p, c), 4),
            }
        )
    per_day: dict[str, Counter] = defaultdict(Counter)
    for row in traces:
        per_day[_day(row["_t"])][row.get("agent") or "?"] += int(row.get("prompt_tokens") or 0) + int(
            row.get("completion_tokens") or 0
        )
    total = prompt + completion
    usd = estimate(prompt, completion)
    blended = (float(price["input_per_million_usd"]) + float(price["output_per_million_usd"])) / 2 / 1e6
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "real_eur": round(sum(float(r.get("cost_eur") or 0) for r in traces), 4),
        "estimate_usd": round(usd, 4),
        # The average price of one token of this traffic (a mix of prompt and generated tokens).
        "usd_per_token": usd / total if total else blended,
        "by_agent": by_agent,
        "per_day": [{"day": day, **counts} for day, counts in sorted(per_day.items())],
    }


# ------------------------------------------------------------------------------ per chat
def _chat_facts(chat: dict[str, Any]) -> dict[str, Any]:
    """What one saved chat tells: its scores, routing, engine, tokens and times."""
    card = chat.get("scorecard") or {}
    kpis = chat.get("kpis") or {}
    routing = chat.get("routing") or {}
    profile = chat.get("profile") or {}
    advisor = [m.get("meta") or {} for m in chat.get("messages", []) if m.get("speaker") == "advisor"]
    models = Counter(m.get("model") for m in advisor if m.get("mode") == "llm" and m.get("model"))
    if models:
        engine = "LLM · " + str(models.most_common(1)[0][0]).split("/")[-1].replace(":free", "")
    elif any(m.get("mode") == "human" for m in advisor):
        engine = "A person at the desk"
    else:
        engine = "Templates (offline backup)"
    csat = chat.get("csat") if chat.get("csat") is not None else kpis.get("csat")
    true_intent = profile.get("intent") or kpis.get("true_intent")
    predicted = routing.get("predicted_intent") or kpis.get("predicted_intent")
    return {
        "t": chat["_t"],
        "source": chat.get("_source"),
        "engine": engine,
        "overall": card.get("overall"),
        "scores": card.get("scores") or {},
        "judge": card.get("judge"),
        "judge_ms": card.get("latency_ms"),
        "resolved": card.get("resolved"),
        "csat": csat,
        "fcr": kpis.get("fcr"),
        "compliant": kpis.get("compliant"),
        "action_correct": kpis.get("action_correct"),
        "judge_correct": kpis.get("judge_correct", card.get("correct")),
        "drafts_rejected": kpis.get("drafts_rejected"),
        "mismatches": kpis.get("customer_mismatches"),
        "true_intent": true_intent,
        "predicted_intent": predicted,
        "true_group": profile.get("intent_group"),
        "predicted_group": routing.get("predicted_group"),
        "confidence": routing.get("confidence"),
        "intent_correct": kpis.get(
            "intent_correct", (predicted == true_intent) if predicted and true_intent else None
        ),
        "replies": len(advisor),
        "tokens": sum(int(m.get("tokens") or 0) for m in advisor),
        "ai_ms": sum(float(m.get("latency_ms") or 0) for m in advisor if m.get("mode") != "human"),
        "reply_ms": [
            float(m["latency_ms"])
            for m in advisor
            if m.get("mode") == "llm" and m.get("latency_ms") is not None
        ],
    }


def _advisor_section(chats: list[dict[str, Any]]) -> dict[str, Any]:
    """Who wrote the advisor's answers (LLM, backup template, offline template, a person), reply times, and
    the live side of the RAG (answers citing a policy section)."""
    modes: Counter = Counter()
    llm_ms: list[float] = []
    template_ms: list[float] = []
    sections: Counter = Counter()
    answers = cited = 0
    for chat in chats:
        for message in chat.get("messages", []):
            if message.get("speaker") != "advisor":
                continue
            meta = message.get("meta") or {}
            mode = meta.get("mode") or "unknown"
            modes[mode] += 1
            if meta.get("latency_ms") is not None and mode in ("llm", "template", "template_fallback"):
                (llm_ms if mode == "llm" else template_ms).append(float(meta["latency_ms"]))
            if mode != "human":
                answers += 1
                sources = meta.get("sources") or []
                cited += bool(sources)
                sections.update({str(s).split("__")[0].replace("_", " ") for s in sources})
    tried = modes["llm"] + modes["template_fallback"]  # replies where the LLM was asked to answer
    return {
        "modes": dict(modes),
        "fallback_rate": round(modes["template_fallback"] / tried, 4) if tried else None,
        "reply_llm_p50_ms": _pct(llm_ms, 50),
        "reply_llm_p95_ms": _pct(llm_ms, 95),
        "reply_template_p50_ms": _pct(template_ms, 50),
        "rag": {
            "answers": answers,
            "cited_share": round(cited / answers, 4) if answers else None,
            "top_sections": [{"section": s, "answers": n} for s, n in sections.most_common(6)],
        },
    }


def _tools_section(chats: list[dict[str, Any]], facts: list[dict[str, Any]]) -> dict[str, Any]:
    """Per tool: calls, success, time, who chose it (the AI, a pipeline step, a safety net) and MCP use."""
    stats: dict[tuple, dict[str, Any]] = {}
    callers: Counter = Counter()
    via: Counter = Counter()
    for chat in chats:
        for message in chat.get("messages", []):
            who = "customer" if message.get("speaker") == "customer" else "advisor"
            for call in (message.get("meta") or {}).get("tools") or []:
                key = (who, str(call.get("name")))
                entry = stats.setdefault(
                    key,
                    {
                        "agent": who,
                        "tool": key[1],
                        "calls": 0,
                        "ok": 0,
                        "ms": [],
                        "callers": Counter(),
                        "mcp": 0,
                        "via_known": 0,
                    },
                )
                entry["calls"] += 1
                entry["ok"] += call.get("ok") is not False
                if call.get("latency_ms") is not None:
                    entry["ms"].append(float(call["latency_ms"]))
                caller = CALLER.get(call.get("caller"), "not recorded")
                entry["callers"][caller] += 1
                if who == "advisor":
                    callers[caller] += 1
                if call.get("via"):
                    entry["via_known"] += 1
                    entry["mcp"] += call["via"] == "mcp"
                    via[call["via"]] += 1
    rows = [
        {
            "agent": e["agent"],
            "tool": e["tool"],
            "calls": e["calls"],
            "success_rate": round(e["ok"] / e["calls"], 4),
            "mean_ms": _avg(e["ms"]),
            "callers": dict(e["callers"]),
            "mcp_share": round(e["mcp"] / e["via_known"], 4) if e["via_known"] else None,
        }
        for e in stats.values()
    ]
    rows.sort(key=lambda r: (r["agent"] != "advisor", -r["calls"]))
    total = sum(r["calls"] for r in rows)
    ok = sum(round(r["success_rate"] * r["calls"]) for r in rows)
    return {
        "rows": rows,
        "calls": total,
        "success_rate": round(ok / total, 4) if total else None,
        "callers": dict(callers),
        "via": dict(via),
        "per_chat": round(total / len(facts), 2) if facts else None,
    }


def _quality_section(facts: list[dict[str, Any]], offline: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """The Quality agent's scores, resolved / FCR / CSAT, policy-correct by code and by the judge, and how far
    the judge can be trusted (its agreement with human labels, offline)."""
    graded = [f for f in facts if f["overall"] is not None]
    criteria = sorted({c for f in graded for c in f["scores"]})
    per_day: dict[str, list[float]] = defaultdict(list)
    for f in graded:
        per_day[_day(f["t"])].append(float(f["overall"]))
    both = [f for f in facts if f["action_correct"] is not None and f["judge_correct"] is not None]
    return {
        "chats": len(graded),
        "overall": _avg(f["overall"] for f in graded),
        "criteria": {c: _avg(f["scores"].get(c) for f in graded) for c in criteria},
        "resolved": _share(f["resolved"] for f in facts),
        "fcr": _share(f["fcr"] for f in facts),
        "csat": _avg(f["csat"] for f in facts),
        "compliant": _share(f["compliant"] for f in facts),
        "correct_by_code": _share(f["action_correct"] for f in facts),
        "correct_by_judge": _share(f["judge_correct"] for f in facts),
        # How often the judge and the code (the rules engine's reference) say the same thing.
        "code_judge_agreement": _share(f["action_correct"] == f["judge_correct"] for f in both)
        if both
        else None,
        "judges": dict(Counter(f["judge"] or "unknown" for f in graded)),
        "judge_p50_ms": _pct([float(f["judge_ms"]) for f in graded if f["judge_ms"]], 50),
        "per_day": [
            {"day": day, "overall": round(sum(v) / len(v), 3), "chats": len(v)}
            for day, v in sorted(per_day.items())
        ],
        "calibration": offline.get("calibration", []),
    }


def _routing_section(facts: list[dict[str, Any]]) -> dict[str, Any]:
    """The Workforce agent's routing: accuracy, the problem families it mixes up (confusion matrix), its most
    frequent mistakes, and whether it is right more often when it is more sure (calibration)."""
    routed = [f for f in facts if f["intent_correct"] is not None]
    matrix = [[0 for _ in GROUPS] for _ in GROUPS]
    for f in routed:
        if f["true_group"] in GROUPS and f["predicted_group"] in GROUPS:
            matrix[GROUPS.index(f["true_group"])][GROUPS.index(f["predicted_group"])] += 1
    mistakes = Counter((f["true_intent"], f["predicted_intent"]) for f in routed if not f["intent_correct"])
    bins = []
    for low, high in CONFIDENCE_BINS:
        inside = [f for f in routed if f["confidence"] is not None and low <= float(f["confidence"]) < high]
        bins.append(
            {
                "from": low,
                "to": min(high, 1.0),
                "chats": len(inside),
                "accuracy": _share(f["intent_correct"] for f in inside),
            }
        )
    return {
        "chats": len(routed),
        "accuracy": _share(f["intent_correct"] for f in routed),
        "groups": GROUPS,
        "matrix": matrix,
        "mistakes": [{"true": t, "predicted": p, "chats": n} for (t, p), n in mistakes.most_common(5)],
        "confidence": bins,
    }


def _grounding_section(facts: list[dict[str, Any]], tools: dict[str, Any]) -> dict[str, Any]:
    """Does the advisor invent things? The fact check's rejections, the wrong answers the customer caught, and
    how often the advisor's action matches the rules engine's reference."""
    checks = next(
        (r for r in tools["rows"] if r["agent"] == "advisor" and r["tool"] == "check_draft_reply"), None
    )
    rejected = [int(f["drafts_rejected"]) for f in facts if f["drafts_rejected"] is not None]
    caught = [int(f["mismatches"]) for f in facts if f["mismatches"] is not None]
    return {
        "fact_checks": checks["calls"] if checks else 0,
        "drafts_rejected": sum(rejected),
        "chats_with_rejection": _share(n > 0 for n in rejected),
        "customer_caught": sum(caught),
        "chats_with_catch": _share(n > 0 for n in caught),
        "action_correct": _share(f["action_correct"] for f in facts),
    }


def _engines_section(facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The engines side by side on the same chats' metrics (which LLM, the templates, or a person)."""
    rows = []
    for engine in sorted({f["engine"] for f in facts}):
        own = [f for f in facts if f["engine"] == engine]
        times = [ms for f in own for ms in f["reply_ms"]]
        rows.append(
            {
                "engine": engine,
                "chats": len(own),
                "quality": _avg(f["overall"] for f in own),
                "correct_by_code": _share(f["action_correct"] for f in own),
                "fcr": _share(f["fcr"] for f in own),
                "csat": _avg(f["csat"] for f in own),
                "reply_p50_ms": _pct(times, 50),
                "tokens_per_chat": _avg(f["tokens"] for f in own),
            }
        )
    rows.sort(key=lambda r: -r["chats"])
    return rows


def _judge_vs_customer(facts: list[dict[str, Any]]) -> dict[str, Any]:
    """Two independent views of quality: the judge's score and the customer's rating. Do they agree?"""
    pairs = [
        (float(f["overall"]), float(f["csat"]))
        for f in facts
        if f["overall"] is not None and f["csat"] is not None
    ]
    result: dict[str, Any] = {
        "chats": len(pairs),
        "pearson": None,
        "spearman": None,
        "points": [list(p) for p in pairs],
    }
    if len(pairs) >= 3:
        judge = pd.Series([p[0] for p in pairs])
        customer = pd.Series([p[1] for p in pairs])
        if judge.nunique() > 1 and customer.nunique() > 1:
            result["pearson"] = round(float(judge.corr(customer)), 3)
            result["spearman"] = round(float(judge.corr(customer, method="spearman")), 3)
    return result


def _business_section(facts: list[dict[str, Any]], usd_per_token: float) -> dict[str, Any]:
    """The numbers a manager reads: per resolved chat, the AI's tokens, the estimated cost, the replies and
    the AI's processing time."""
    resolved = [f for f in facts if f["resolved"]]
    tokens = _avg(f["tokens"] for f in resolved)
    return {
        "resolved_chats": len(resolved),
        "resolved_share": _share(f["resolved"] for f in facts),
        "tokens_per_resolved": tokens,
        "estimate_usd_per_resolved": round(tokens * usd_per_token, 6) if tokens is not None else None,
        "replies_per_resolved": _avg(f["replies"] for f in resolved),
        "ai_seconds_per_resolved": round(_avg(f["ai_ms"] for f in resolved) / 1000, 2) if resolved else None,
    }


def _alerts(values: dict[str, float | None], thresholds: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Each watched metric with its colour: ok, warn (orange) or alert (red), from configs/monitoring.yaml."""
    alerts = []
    for metric, rule in thresholds.items():
        value = values.get(metric)
        level = "none"
        if value is not None:
            higher = rule.get("better") == "higher"
            if (value <= rule["alert"]) if higher else (value >= rule["alert"]):
                level = "alert"
            elif (value <= rule["warn"]) if higher else (value >= rule["warn"]):
                level = "warn"
            else:
                level = "ok"
        alerts.append(
            {
                "metric": metric,
                "value": value,
                "level": level,
                "warn": rule["warn"],
                "alert": rule["alert"],
                "better": rule.get("better", "lower"),
            }
        )
    return alerts
