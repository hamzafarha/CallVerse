"""LangGraph orchestration of the four agents for one customer conversation.

    client_open -> workforce_route -> advisor <-> client_reply -> quality -> kpi -> END

- Client agent opens with the real customer message (twin input).
- Workforce agent predicts the problem type (intent classifier) and routes the
  customer to the best-skilled advisor desk; the expected wait comes from the
  queueing model of that hour (Erlang C).
- Advisor agent answers (RAG + tools, or templates); the client replies; the loop
  ends when the customer leaves or after ``max_turns``.
- Quality agent grades the conversation against the policy-correct reference.
- KPI node turns it into BO2 indicators (FCR, CSAT, compliance, correctness).
"""

import json
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from langgraph.graph import END, START, StateGraph

from callverse.agents.advisor.advisor import AdvisorAgent, AdvisorMemory
from callverse.agents.advisor.tools import AdvisorTools
from callverse.agents.client.profiles import CustomerProfile
from callverse.agents.client.simulator import ClientAgent
from callverse.agents.quality.reviewer import QualityReviewer
from callverse.config import TRACE_DIR, load_yaml
from callverse.data import loaders
from callverse.data.conversations import answer_and_summary
from callverse.data.tickets import decide_outcome
from callverse.orchestration.runtime import AgentRuntime, get_runtime
from callverse.orchestration.state import ConversationState
from callverse.simulation import (
    erlang_c_mean_wait,
    load_twin_settings,
    make_agent_pool,
    required_agents,
    workload_shares,
)


@dataclass
class ConversationSession:
    """Non-serializable objects of one conversation (agents, tools, memory)."""

    profile: CustomerProfile
    client: ClientAgent
    advisor: AdvisorAgent
    reviewer: QualityReviewer
    tools: AdvisorTools
    memory: AdvisorMemory
    max_turns: int


def make_session(
    profile: CustomerProfile,
    mode: str = "auto",
    seed: int = 0,
    runtime: AgentRuntime | None = None,
    variant: str | None = None,
) -> ConversationSession:
    """Agents for one conversation.

    ``mode``: auto, llm, or template (offline). ``variant`` of the LLM advisor:
    ``rag_policy`` (RAG + tools + rules engine, default) or ``rag`` (pure agentic RAG).
    """
    runtime = runtime or get_runtime()
    settings = runtime.settings
    llm = None if mode == "template" else runtime.llm
    retriever = runtime.retriever() if mode != "template" else runtime.keyword_retriever()
    advisor_mode = {"template": "template", "llm": "llm"}.get(mode, "auto")
    return ConversationSession(
        profile=profile,
        client=ClientAgent(llm, advisor_mode, seed, int(settings["client"]["max_turns"])),
        advisor=AdvisorAgent(
            retriever,
            runtime.classifier(),
            llm,
            advisor_mode,
            int(settings["advisor"]["retrieval_top_k"]),
            int(settings["advisor"]["max_tool_rounds"]),
            float(settings["advisor"]["knowledge_base"]["no_answer_score"]),
            seed,
            variant or settings["advisor"].get("variant", "rag_policy"),
        ),
        reviewer=QualityReviewer(llm, {"template": "rules", "llm": "llm"}.get(mode, "auto")),
        tools=AdvisorTools(as_of=profile.contact_timestamp, retriever=retriever),
        memory=AdvisorMemory(),
        max_turns=int(settings["client"]["max_turns"]),
    )


def _event(state: ConversationState, node: str, summary: str, **data: Any) -> list[dict[str, Any]]:
    return [*state.get("events", []), {"node": node, "summary": summary, **data}]


def reference_answer(session: ConversationSession) -> dict[str, Any]:
    """Policy-correct outcome for the TRUE intent (the hidden answer key)."""
    facts = session.tools.order_facts(session.profile.order_id, session.profile.intent)
    if facts is None:
        return {}
    row = pd.Series({**facts, "intent": session.profile.intent})
    outcome, chunk, handed_to = decide_outcome(row)
    row["outcome"] = outcome
    answer, _ = answer_and_summary(row)
    return {
        "outcome": outcome,
        "kb_chunk_id": chunk,
        "handed_to": handed_to,
        "answer": answer,
        "status_at_contact": facts["order_status_at_contact"],
    }


def expected_wait(profile: CustomerProfile, intent_group: str) -> dict[str, Any]:
    """Workforce view of the contact's hour: arrivals, agents planned, Erlang C wait."""
    settings = load_twin_settings()
    daily = loaders.daily_contacts_by_group()
    shares = loaders.hour_shares()
    day = profile.contact_timestamp.normalize()
    hour = profile.contact_timestamp.hour
    today = daily[daily["date"] == day]
    rate = float(today["contacts"].sum()) * settings.sim.scale_factor * shares[hour]
    work = sum(float(r.contacts) * settings.mean_handle[r.intent_group] for r in today.itertuples())
    aht = work / max(float(today["contacts"].sum()), 1.0)
    sim = settings.sim
    agents = required_agents(
        rate,
        aht,
        sim.service_level_target,
        sim.service_level_threshold_seconds,
        sim.max_occupancy,
        sim.min_agents,
    )
    pool = make_agent_pool(agents, workload_shares(daily, settings), settings, seed_offset=int(day.dayofyear))
    best = min(pool, key=lambda a: a.speed.get(intent_group, 1.0))
    open_now = sim.is_open(hour)
    return {
        "is_live": open_now,
        "arrivals_per_hour": round(rate, 1),
        "agents_on_duty": agents,
        "expected_wait_seconds": round(erlang_c_mean_wait(agents, rate, aht), 1) if open_now else None,
        "assigned_desk": f"advisor-{best.agent_id:02d}",
        "desk_specialty": best.primary_group,
        "desk_speed_on_problem": best.speed.get(intent_group, 1.0),
        "expected_handle_seconds": round(
            settings.mean_handle[intent_group] * best.speed.get(intent_group, 1.0)
        ),
    }


def build_graph(session: ConversationSession):
    """Compiled LangGraph for one conversation."""

    def client_open(state: ConversationState) -> dict[str, Any]:
        turn = session.client.opening(session.profile)
        message = {"speaker": "customer", "text": turn.text, "meta": {"mode": turn.mode}}
        return {
            "messages": [message],
            "customer_turns": 1,
            "ended": False,
            "events": _event(
                state, "client", "Customer opens the chat", text=turn.text, persona=session.profile.persona
            ),
        }

    def workforce_route(state: ConversationState) -> dict[str, Any]:
        prediction = session.advisor.classifier.predict(state["messages"][0]["text"])
        session.memory.intent = prediction.intent
        session.memory.intent_group = prediction.intent_group
        session.memory.intent_confidence = prediction.confidence
        routing = {
            "predicted_intent": prediction.intent,
            "predicted_group": prediction.intent_group,
            "confidence": round(prediction.confidence, 3),
            **expected_wait(session.profile, prediction.intent_group),
        }
        return {
            "routing": routing,
            "events": _event(
                state,
                "workforce",
                f"Predicted '{prediction.intent}' -> {routing['assigned_desk']} "
                f"({routing['desk_specialty']} specialist)",
                routing=routing,
            ),
        }

    def advisor(state: ConversationState) -> dict[str, Any]:
        messages = state["messages"]
        reply = session.advisor.reply(messages, session.memory, session.tools)
        meta = {
            "mode": reply.mode,
            "stage": reply.stage,
            "sources": reply.sources,
            "retrieval": reply.retrieval,
            "tools": reply.tool_calls,
            "model": reply.model,
            "latency_ms": round(reply.latency_ms, 1),
            "tokens": reply.tokens,
        }
        message = {"speaker": "advisor", "text": reply.text, "meta": meta}
        return {
            "messages": [*messages, message],
            "advisor": {
                "intent": session.memory.intent,
                "order_id": session.memory.order_id,
                "outcome": session.memory.outcome,
                "handed_to": session.memory.handed_to,
                "answered": session.memory.answered,
            },
            "events": _event(
                state,
                "advisor",
                f"Advisor ({reply.mode}, {reply.stage})",
                text=reply.text,
                tools=[t["name"] for t in reply.tool_calls],
                sources=reply.sources,
            ),
        }

    def client_reply(state: ConversationState) -> dict[str, Any]:
        messages = state["messages"]
        turn = session.client.respond(session.profile, messages, state["customer_turns"])
        message = {"speaker": "customer", "text": turn.text, "meta": {"mode": turn.mode}}
        return {
            "messages": [*messages, message],
            "customer_turns": state["customer_turns"] + 1,
            "ended": turn.end,
            "csat": turn.csat,
            "events": _event(
                state,
                "client",
                "Customer replies" + (" and leaves" if turn.end else ""),
                text=turn.text,
                csat=turn.csat,
            ),
        }

    def after_client(state: ConversationState) -> str:
        if state.get("ended") or state["customer_turns"] > session.max_turns:
            return "quality"
        return "advisor"

    def quality(state: ConversationState) -> dict[str, Any]:
        reference = reference_answer(session)
        advisor_messages = [m for m in state["messages"] if m["speaker"] == "advisor"]
        meta = {
            "sources": [s for m in advisor_messages for s in m["meta"].get("sources", [])],
            "tools": [t for m in advisor_messages for t in m["meta"].get("tools", [])],
            "outcome": session.memory.outcome,
            "handed_to": session.memory.handed_to,
        }
        transcript = [{"speaker": m["speaker"], "text": m["text"]} for m in state["messages"]]
        card = session.reviewer.review(transcript, reference, meta)
        return {
            "reference": reference,
            "scorecard": card.to_dict(),
            "events": _event(
                state,
                "quality",
                f"Quality ({card.judge}): overall {card.overall:.1f}/5",
                scores=card.scores,
                correct=card.correct,
            ),
        }

    def kpi(state: ConversationState) -> dict[str, Any]:
        card = state["scorecard"]
        tools = [
            t for m in state["messages"] if m["speaker"] == "advisor" for t in m["meta"].get("tools", [])
        ]
        customer_text = " ".join(m["text"] for m in state["messages"] if m["speaker"] == "customer").lower()
        handover = session.memory.handed_to or ("supervisor" if "supervisor" in customer_text else None)
        reference = state.get("reference") or {}
        action_correct = None
        if session.memory.outcome and reference.get("outcome"):
            action_correct = session.memory.outcome == reference["outcome"]
        kpis = {
            "contact_id": session.profile.contact_id,
            "true_intent": session.profile.intent,
            "predicted_intent": state["routing"]["predicted_intent"],
            "intent_correct": state["routing"]["predicted_intent"] == session.profile.intent,
            "advisor_mode": next(
                (m["meta"]["mode"] for m in reversed(state["messages"]) if m["speaker"] == "advisor"), None
            ),
            "judge": card["judge"],
            "turns": len(state["messages"]),
            "fcr": bool(card["resolved"]) and handover is None,
            "resolved_or_handed_over": bool(card["resolved"]),
            "csat": state.get("csat"),
            "compliant": card["scores"]["compliance"] >= 4,
            "correct": action_correct if action_correct is not None else card["correct"],
            "action_correct": action_correct,
            "judge_correct": card["correct"],
            "tool_calls": len(tools),
            "tool_success_rate": (sum(t["ok"] for t in tools) / len(tools)) if tools else None,
            "expected_wait_seconds": state["routing"].get("expected_wait_seconds"),
            "expected_handle_seconds": state["routing"].get("expected_handle_seconds"),
            **{f"score_{k}": v for k, v in card["scores"].items()},
        }
        return {"kpis": kpis, "events": _event(state, "kpi", "KPIs recorded", kpis=kpis)}

    graph = StateGraph(ConversationState)
    for name, node in [
        ("client_open", client_open),
        ("workforce_route", workforce_route),
        ("advisor", advisor),
        ("client_reply", client_reply),
        ("quality", quality),
        ("kpi", kpi),
    ]:
        graph.add_node(name, node)
    graph.add_edge(START, "client_open")
    graph.add_edge("client_open", "workforce_route")
    graph.add_edge("workforce_route", "advisor")
    graph.add_edge("advisor", "client_reply")
    graph.add_conditional_edges("client_reply", after_client, {"advisor": "advisor", "quality": "quality"})
    graph.add_edge("quality", "kpi")
    graph.add_edge("kpi", END)
    return graph.compile()


def initial_state(profile: CustomerProfile) -> ConversationState:
    return {"profile": profile.to_dict(), "messages": [], "events": [], "customer_turns": 0}


def run_conversation(
    profile: CustomerProfile,
    mode: str = "auto",
    seed: int = 0,
    runtime: AgentRuntime | None = None,
    variant: str | None = None,
) -> ConversationState:
    """Run one conversation to the end; returns the final state."""
    session = make_session(profile, mode, seed, runtime, variant)
    return build_graph(session).invoke(initial_state(profile), {"recursion_limit": 50})


def stream_conversation(
    profile: CustomerProfile,
    mode: str = "auto",
    seed: int = 0,
    runtime: AgentRuntime | None = None,
    variant: str | None = None,
) -> Iterator[tuple[str, dict[str, Any]]]:
    """Yield (node, update) after every node: used by the dashboard WebSocket."""
    session = make_session(profile, mode, seed, runtime, variant)
    graph = build_graph(session)
    for chunk in graph.stream(initial_state(profile), {"recursion_limit": 50}, stream_mode="updates"):
        for node, update in chunk.items():
            yield node, update


def graph_mermaid() -> str:
    """Mermaid diagram of the graph (for the report and the dashboard)."""
    return (
        "graph LR\n  START((start)) --> client_open[Client agent: opening]\n"
        "  client_open --> workforce_route[Workforce agent: predict + route]\n"
        "  workforce_route --> advisor[Advisor agent: RAG + tools]\n"
        "  advisor --> client_reply[Client agent: reply]\n"
        "  client_reply -->|continue| advisor\n  client_reply -->|ended| quality[Quality agent: judge]\n"
        "  quality --> kpi[KPI engine]\n  kpi --> END((end))"
    )


def save_transcript(
    state: ConversationState, folder: Path = TRACE_DIR / "conversations", suffix: str = ""
) -> Path:
    """Write a finished conversation as JSON (artifacts/traces/conversations/)."""
    folder.mkdir(parents=True, exist_ok=True)
    name = state["profile"]["contact_id"] + (f"_{suffix}" if suffix else "")
    path = folder / f"{name}.json"
    path.write_text(json.dumps(state, default=str, indent=2), encoding="utf-8")
    return path


def run_batch(
    n: int = 30,
    mode: str = "auto",
    seed: int = 0,
    period: tuple[str, str] | None = None,
    log: Callable[[str], None] | None = None,
    variant: str | None = None,
) -> pd.DataFrame:
    """Run ``n`` conversations on sampled contacts; one KPI row per conversation."""
    from callverse.agents.client.profiles import sample_profiles

    profiles = sample_profiles(loaders.contacts(), n, seed, period)
    rows = []
    for number, profile in enumerate(profiles, start=1):
        state = run_conversation(profile, mode, seed + number, variant=variant)
        used = (
            "template"
            if mode == "template"
            else (variant or get_runtime().settings["advisor"].get("variant", "rag_policy"))
        )
        save_transcript(state, suffix=used)
        rows.append({**state["kpis"], "variant": used})
        if log and (number % 10 == 0 or number == len(profiles)):
            log(f"  conversations {number}/{len(profiles)}")
    return pd.DataFrame(rows)


def conversation_kpis(frame: pd.DataFrame) -> dict[str, float]:
    """BO2 indicators over a batch of conversations."""
    if frame.empty:
        return {}

    def mean(column: str) -> float:
        values = pd.to_numeric(frame[column], errors="coerce").dropna()
        return float(values.mean()) if len(values) else float("nan")

    return {
        "conversations": float(len(frame)),
        "fcr_rate": mean("fcr"),
        "csat_mean": mean("csat"),
        "csat_satisfied_share": float((pd.to_numeric(frame["csat"], errors="coerce") >= 4).mean()),
        "compliance_rate": mean("compliant"),
        "correct_answer_rate": mean("correct"),
        "verified_action_rate": mean("action_correct") if "action_correct" in frame else float("nan"),
        "judge_correct_rate": mean("judge_correct") if "judge_correct" in frame else float("nan"),
        "tool_success_rate": mean("tool_success_rate"),
        "intent_accuracy": mean("intent_correct"),
        "mean_turns": mean("turns"),
        "quality_overall": float(
            np.mean(
                [
                    mean(f"score_{c}")
                    for c in ["compliance", "relevance", "satisfaction", "sentiment", "resolution"]
                ]
            )
        ),
    }


def agents_settings() -> dict[str, Any]:
    return load_yaml("agents")
