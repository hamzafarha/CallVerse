"""FastAPI backend of CallVerse (REST + WebSocket), shared by both React apps.

Run with ``callverse serve`` (or ``uvicorn callverse.api.app:app``).

- Front office (``frontend/front-office``): customer portal, live chat with the
  Advisor agent and the advisor desk -> ``/api/portal``, ``/api/kb``, ``/api/desk``,
  ``/ws/session``.
- Back office (``frontend/back-office``): the managers' control room -> every
  other route (forecast, workforce, twin, agents, quality, evaluation, MLOps).
"""

import asyncio
import json
import threading
import time
from typing import Any

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from callverse.api.schemas import ConversationRequest, HumanLabel, TwinCompareRequest, TwinRunRequest
from callverse.api.services import clean, read_eval, records, twin
from callverse.config import (
    EVALUATION_DIR,
    FORECAST_DIR,
    PROJECT_ROOT,
    TRACE_DIR,
    load_yaml,
)
from callverse.data import loaders
from callverse.evaluation.business_kpis import BO_KPIS, summarize_runs
from callverse.evaluation.experiments import SIM_KPIS

settings = load_yaml("app")
app = FastAPI(
    title="CallVerse API", version=settings["app"]["version"], description=settings["app"]["description"]
)
app.add_middleware(
    CORSMiddleware, allow_origins=settings["server"]["cors_origins"], allow_methods=["*"], allow_headers=["*"]
)


# --------------------------------------------------------------------- overview
@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "version": settings["app"]["version"]}


@app.get("/api/overview")
def overview() -> dict[str, Any]:
    """Headline numbers, BO/DSO definitions and the scorecard."""
    contacts = loaders.contacts()
    tickets = loaders.tickets()
    scorecard_path = EVALUATION_DIR / "scorecard.json"
    return clean(
        {
            "app": settings["app"],
            "data": {
                "orders": int(len(loaders.orders_analytical())),
                "contacts": int(len(contacts)),
                "tickets": int(len(tickets)),
                "chat_messages": int(len(loaders.chat_messages())),
                "first_day": str(contacts["contact_date"].min().date()),
                "last_day": str(contacts["contact_date"].max().date()),
                "fcr_rate_history": float(tickets["first_contact_resolution"].mean()),
                "csat_history": float(tickets["csat_score"].dropna().astype(float).mean()),
            },
            "objectives": BO_KPIS,
            "scorecard": json.loads(scorecard_path.read_text(encoding="utf-8"))
            if scorecard_path.exists()
            else [],
        }
    )


# ------------------------------------------------------------------------- data
@app.get("/api/data/summary")
def data_summary() -> dict[str, Any]:
    """Contacts over time, intent mix, outcomes, CSAT, data contracts."""
    from callverse.data.validation import validate_processed_data

    daily = loaders.daily_contacts_by_group()
    weekly = (
        daily.assign(week=daily["date"].dt.to_period("W").dt.start_time)
        .groupby(["week", "intent_group"])["contacts"]
        .sum()
        .unstack(fill_value=0)
        .reset_index()
    )
    contacts = loaders.contacts()
    tickets = loaders.tickets()
    intents = contacts.groupby(["intent_group", "intent"]).size().rename("contacts").reset_index()
    outcomes = (
        tickets["outcome_class"].value_counts().rename_axis("outcome_class").rename("tickets").reset_index()
    )
    csat = tickets["csat_score"].dropna().astype(int).value_counts().sort_index()
    situations = (
        contacts["generator_situation"]
        .value_counts()
        .rename_axis("situation")
        .rename("contacts")
        .reset_index()
    )
    hours = pd.DataFrame({"hour": range(24), "share": loaders.hour_shares()})
    contracts = [r.__dict__ for r in validate_processed_data()]
    return clean(
        {
            "weekly": records(weekly),
            "intents": records(intents),
            "outcomes": records(outcomes),
            "csat": [{"score": int(k), "tickets": int(v)} for k, v in csat.items()],
            "situations": records(situations),
            "hour_profile": records(hours),
            "contracts": contracts,
            "sample_contacts": records(
                contacts.sample(8, random_state=1)[
                    [
                        "contact_id",
                        "contact_timestamp",
                        "intent",
                        "intent_group",
                        "message_text",
                        "generator_situation",
                    ]
                ]
            ),
        }
    )


# --------------------------------------------------------------------- forecast
@app.get("/api/forecast")
def forecast() -> dict[str, Any]:
    """Backtest accuracy, actual vs forecast series, next week, feature importance."""
    from callverse.evaluation.forecast_metrics import forecast_summary

    summary = forecast_summary()
    if not summary.get("available"):
        raise HTTPException(404, "Run `callverse forecast` first.")
    backtest = pd.read_parquet(FORECAST_DIR / "contact_forecast_backtest_predictions.parquet")
    horizon1 = backtest[(backtest["horizon"].between(1, 7))]
    total = horizon1[horizon1["intent_group"] == "total"].pivot_table(
        index="date", columns="model", values="forecast", aggfunc="mean"
    )
    total["actual"] = horizon1[horizon1["intent_group"] == "total"].groupby("date")["actual"].first()
    total = total.reset_index()
    by_group = horizon1[(horizon1["model"] == "lightgbm") & (horizon1["intent_group"] != "total")]
    by_group = by_group.groupby(["date", "intent_group"])[["forecast", "actual"]].mean().reset_index()
    by_horizon = (
        horizon1[horizon1["intent_group"] == "total"]
        .groupby(["horizon", "model"])
        .apply(
            lambda t: (t["forecast"] - t["actual"]).abs().sum() / t["actual"].sum() * 100,
            include_groups=False,
        )
        .rename("wmape")
        .reset_index()
    )
    next_week = FORECAST_DIR / "contact_forecast_next_week.csv"
    importance = FORECAST_DIR / "lightgbm_feature_importance.csv"
    return clean(
        {
            "summary": summary,
            "total_series": records(total),
            "group_series": records(by_group),
            "by_horizon": records(by_horizon),
            "next_week": records(pd.read_csv(next_week)) if next_week.exists() else [],
            "importance": records(pd.read_csv(importance).head(12)) if importance.exists() else [],
        }
    )


# ------------------------------------------------------------------------- twin
@app.get("/api/twin/config")
def twin_config() -> dict[str, Any]:
    from callverse.agents.workforce.routing import ppo_available

    return clean({**twin().describe(), "ppo_available": ppo_available()})


def _spec(request: TwinRunRequest):
    spec = twin().scenario(request.scenario)
    return spec.with_overrides(
        name=spec.name
        if not (request.multipliers or request.absence_rate is not None or request.handle_time_multiplier)
        else f"{spec.name}_custom",
        multipliers={**spec.multipliers, **(request.multipliers or {})},
        absence_rate=request.absence_rate,
        handle_time_multiplier=request.handle_time_multiplier,
    )


@app.post("/api/twin/run")
def twin_run(request: TwinRunRequest) -> dict[str, Any]:
    """Simulate one configuration: KPIs (mean, 95% CI), queue over the week, the plan."""
    try:
        spec = _spec(request)
        started = time.perf_counter()
        runs = twin().run(
            spec, request.plan, request.router, request.seeds, request.prepared, trace_first=True
        )
    except FileNotFoundError as error:
        raise HTTPException(409, str(error)) from error
    elapsed = time.perf_counter() - started
    frame = pd.DataFrame([{"seed": r.seed, **r.kpis} for r in runs]).assign(config="run")
    summary = summarize_runs(frame, ["config"], SIM_KPIS)
    queue = runs[0].queue
    hourly = (
        queue.assign(hour_index=(queue["time"] // 3600).astype(int))
        .groupby("hour_index")[["live_waiting", "busy", "on_duty"]]
        .mean()
        .reset_index()
    )
    records0 = runs[0].records
    live = records0[records0["is_live"]]
    per_hour = (
        live.assign(hour_index=(live["arrival"] // 3600).astype(int))
        .groupby("hour_index")
        .agg(
            arrivals=("contact_id", "size"),
            abandoned=("abandoned", "sum"),
            answered_in_time=("wait", lambda w: float((w.dropna() <= 20).sum())),
        )
        .reset_index()
    )
    hourly = hourly.merge(per_hour, on="hour_index", how="left").fillna(0)
    plan = twin().plan(spec, request.plan, request.prepared)
    return clean(
        {
            "request": request.model_dump(),
            "elapsed_seconds": elapsed,
            "kpis": records(summary),
            "queue": records(hourly),
            "plan": records(plan.to_frame()),
            "plan_meta": plan.meta,
            "per_seed": records(frame),
        }
    )


@app.post("/api/twin/compare")
def twin_compare(request: TwinCompareRequest) -> dict[str, Any]:
    """Several plans / routers / preparedness on the same simulated customers."""
    rows = []
    for option in request.options:
        option = option.model_copy(update={"scenario": request.scenario, "seeds": request.seeds})
        label = f"{option.plan} | {option.router} | {'prepared' if option.prepared else 'unprepared'}"
        for run in twin().run(_spec(option), option.plan, option.router, request.seeds, option.prepared):
            rows.append({"option": label, "seed": run.seed, **run.kpis})
    frame = pd.DataFrame(rows)
    return clean({"summary": records(summarize_runs(frame, ["option"], SIM_KPIS))})


@app.get("/api/twin/floor")
def twin_floor(
    scenario: str = "promo_spike",
    plan: str = "cpsat",
    router: str = "fifo",
    day: int = 0,
    seed: int = 0,
    prepared: bool = True,
) -> dict[str, Any]:
    """One simulated day, contact by contact, for the animated live floor."""
    try:
        return clean(twin().floor(scenario, plan, router, seed, day, prepared))
    except (FileNotFoundError, KeyError) as error:
        raise HTTPException(409, str(error)) from error


# -------------------------------------------------------------------- workforce
@app.get("/api/workforce/schedule")
def workforce_schedule(
    scenario: str = "baseline", planner: str = "cpsat", prepared: bool = True
) -> dict[str, Any]:
    """A week plan: agents per hour (required / regular / overtime), roster, rules."""
    from callverse.agents.workforce.scheduling import roster_compliance

    spec = twin().scenario(scenario)
    plan = twin().plan(spec, planner, prepared)
    costs = twin().settings.costs
    return clean(
        {
            "plan": records(plan.to_frame()),
            "roster": records(plan.roster),
            "costs": plan.planned_cost(costs.regular_hourly, costs.overtime_multiplier),
            "compliance": roster_compliance(plan.roster, twin().rules) if not plan.roster.empty else None,
            "status": plan.status,
            "solve_seconds": plan.solve_seconds,
            "meta": plan.meta,
            "week_start": str(spec.week_start.date()),
        }
    )


@app.get("/api/workforce/routing")
def workforce_routing() -> dict[str, Any]:
    """PPO learning curve and the router comparison on unseen stressed days."""
    from callverse.agents.workforce.routing import load_skill_weights
    from callverse.evaluation.workforce_metrics import routing_training_curve

    curve = routing_training_curve()
    if len(curve) > 400:
        curve = curve.iloc[:: max(1, len(curve) // 400)]
    return clean(
        {
            "training_curve": records(curve),
            "comparison": read_eval("routing_comparison.csv"),
            "scenario_comparison": read_eval("dso1_routing_vs_fifo.csv"),
            "skill_weights": load_skill_weights(),
            "settings": load_yaml("agents")["workforce"],
        }
    )


# ----------------------------------------------------------------------- agents
@app.get("/api/agents/status")
def agents_status() -> dict[str, Any]:
    from callverse.orchestration.graph import graph_mermaid
    from callverse.orchestration.runtime import get_runtime

    return clean({**get_runtime().status(), "graph": graph_mermaid()})


@app.get("/api/agents/contacts")
def agents_contacts(n: int = 25, seed: int = 0) -> list[dict[str, Any]]:
    """Contacts the playground can replay."""
    contacts = loaders.contacts()
    contacts = contacts[~contacts["bitext_tags"].fillna("").str.contains("W")]
    sample = contacts.sample(n, random_state=seed)
    return records(sample[["contact_id", "contact_timestamp", "intent", "intent_group", "message_text"]])


def _profile(contact_id: str | None, seed: int):
    from callverse.agents.client.profiles import profile_by_contact_id, sample_profiles

    if contact_id:
        return profile_by_contact_id(loaders.contacts(), contact_id, seed)
    return sample_profiles(loaders.contacts(), 1, seed)[0]


@app.post("/api/agents/conversation")
def agents_conversation(request: ConversationRequest) -> dict[str, Any]:
    """Run one LangGraph conversation and return the final state."""
    from callverse.orchestration.graph import run_conversation, save_transcript

    try:
        profile = _profile(request.contact_id, request.seed)
    except KeyError as error:
        raise HTTPException(404, str(error)) from error
    state = run_conversation(profile, request.mode, request.seed, variant=request.variant)
    save_transcript(state)
    return clean(dict(state))


@app.websocket("/ws/conversation")
async def ws_conversation(websocket: WebSocket) -> None:
    """Stream every LangGraph node of a conversation as it happens."""
    from callverse.orchestration.graph import save_transcript, stream_conversation

    await websocket.accept()
    try:
        request = ConversationRequest(**(await websocket.receive_json()))
        profile = _profile(request.contact_id, request.seed)
    except Exception as error:
        await websocket.send_json({"type": "error", "message": str(error)})
        await websocket.close()
        return
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    await websocket.send_json({"type": "profile", "profile": clean(profile.to_dict())})

    def worker() -> None:
        state: dict[str, Any] = {}
        try:
            for node, update in stream_conversation(
                profile, request.mode, request.seed, variant=request.variant
            ):
                state.update(update)
                loop.call_soon_threadsafe(
                    queue.put_nowait, {"type": "update", "node": node, "update": clean(update)}
                )
            state["profile"] = profile.to_dict()
            save_transcript(state)  # type: ignore[arg-type]
            loop.call_soon_threadsafe(queue.put_nowait, {"type": "done"})
        except Exception as error:  # surfaced to the UI
            loop.call_soon_threadsafe(queue.put_nowait, {"type": "error", "message": str(error)})

    threading.Thread(target=worker, daemon=True).start()
    try:
        while True:
            message = await queue.get()
            await websocket.send_json(message)
            if message["type"] in ("done", "error"):
                break
    except WebSocketDisconnect:
        return
    await websocket.close()


# ---------------------------------------------------------------------- quality
@app.get("/api/quality/next")
def quality_next(labeler: str = "anonymous", seed: int = 0) -> dict[str, Any]:
    """A historical conversation not yet labeled by this person (for calibration)."""
    from callverse.agents.quality.rubric import rubric
    from callverse.agents.quality.validation import load_human_labels

    labels = load_human_labels()
    done = set(labels.loc[labels["labeler"] == labeler, "ticket_id"]) if len(labels) else set()
    tickets = loaders.tickets()
    pool = tickets[~tickets["ticket_id"].isin(done)]
    rng = np.random.default_rng(seed + len(done))
    ticket = pool.iloc[int(rng.integers(len(pool)))]
    chat = loaders.chat_messages()
    chat = chat[chat["ticket_id"] == ticket["ticket_id"]].sort_values("turn")
    return clean(
        {
            "ticket_id": ticket["ticket_id"],
            "intent": ticket["intent"],
            "messages": records(chat[["turn", "speaker", "text"]]),
            "rubric": rubric(),
            "labeled_by_you": len(done),
            "labeled_total": int(labels["ticket_id"].nunique()) if len(labels) else 0,
        }
    )


@app.post("/api/quality/labels")
def quality_label(label: HumanLabel) -> dict[str, Any]:
    from callverse.agents.quality.validation import save_human_label

    total = save_human_label({**label.model_dump(), "labeled_at": pd.Timestamp.now().isoformat()})
    return {"saved": True, "labeled_conversations": total}


@app.get("/api/quality/calibration")
def quality_calibration() -> dict[str, Any]:
    from callverse.agents.quality.validation import load_human_labels

    labels = load_human_labels()
    return clean(
        {
            "agreement": read_eval("dso2_judge_calibration_agreement.csv"),
            "human_labels": int(labels["ticket_id"].nunique()) if len(labels) else 0,
            "target": load_yaml("agents")["quality"]["calibration_sample_size"],
            "min_kappa": load_yaml("agents")["quality"]["min_quadratic_kappa"],
        }
    )


@app.post("/api/quality/calibrate")
def quality_calibrate(judge: str = "rules") -> dict[str, Any]:
    """Recompute judge agreement (uses human labels when >= 20 exist)."""
    from callverse.evaluation.experiments import judge_calibration, save_tables

    result = judge_calibration(judge_mode=judge)
    save_tables("dso2_judge_calibration", result)
    return clean({"agreement": records(result["agreement"])})


# ------------------------------------------------------------------- evaluation
@app.get("/api/evaluation")
def evaluation() -> dict[str, Any]:
    """Component metrics, scorecard and every experiment table."""
    from callverse.evaluation.report import component_metrics, scorecard

    return clean(
        {
            "scorecard": scorecard(),
            "component_metrics": records(component_metrics()),
            "dso1": {
                "summary": read_eval("dso1_routing_summary.csv"),
                "vs_fifo": read_eval("dso1_routing_vs_fifo.csv"),
            },
            "dso2": {
                "summary": read_eval("dso2_agents_summary.csv"),
                "retrieval": read_eval("dso2_rag_retrieval.csv"),
                "calibration": read_eval("dso2_judge_calibration_agreement.csv"),
            },
            "dso3": {
                "summary": read_eval("dso3_scheduling_summary.csv"),
                "vs_fixed": read_eval("dso3_scheduling_vs_fixed.csv"),
            },
            "bo4": {
                "summary": read_eval("bo4_preparedness_summary.csv"),
                "vs_unprepared": read_eval("bo4_preparedness_vs_unprepared.csv"),
                "savings": read_eval("bo4_preparedness_savings.csv"),
                "decision_time": read_eval("bo4_preparedness_decision_time.csv"),
            },
            "fidelity": {
                "checks": read_eval("twin_fidelity_checks.csv"),
                "erlang": read_eval("twin_fidelity_erlang.csv"),
                "hourly": read_eval("twin_fidelity_hourly.csv"),
                "daily": read_eval("twin_fidelity_daily.csv"),
            },
        }
    )


# ------------------------------------------------------------------------ mlops
@app.get("/api/mlops")
def mlops() -> dict[str, Any]:
    """MLflow runs, LLM tracing summary, pinned models, artifacts."""
    from callverse.evaluation.report import artifacts_inventory
    from callverse.llm.tracing import Tracer
    from callverse.tracking import recent_runs, tracking_uri

    traces = pd.DataFrame(Tracer(TRACE_DIR / "llm_calls.jsonl").read(2000))
    by_agent = []
    if not traces.empty and "agent" in traces:
        traces = traces[traces.get("model").notna()] if "model" in traces else traces
        grouped = traces.groupby("agent")
        by_agent = records(
            pd.DataFrame(
                {
                    "calls": grouped.size(),
                    "cached_share": grouped["cached"].mean() if "cached" in traces else 0,
                    "mean_latency_ms": grouped["latency_ms"].mean() if "latency_ms" in traces else 0,
                    "prompt_tokens": grouped["prompt_tokens"].sum() if "prompt_tokens" in traces else 0,
                    "completion_tokens": grouped["completion_tokens"].sum()
                    if "completion_tokens" in traces
                    else 0,
                }
            ).reset_index()
        )
    lock = TRACE_DIR / "llm_models.lock.json"
    try:
        runs = recent_runs(60)
    except Exception:
        runs = []
    return clean(
        {
            "mlflow_uri": tracking_uri(),
            "runs": runs,
            "llm_by_agent": by_agent,
            "llm_recent": records(traces.tail(30)) if not traces.empty else [],
            "model_lock": json.loads(lock.read_text(encoding="utf-8")) if lock.exists() else None,
            "artifacts": artifacts_inventory(),
        }
    )


# ---------------------------------------------------------------- system / LLMs
@app.get("/api/system")
def system() -> dict[str, Any]:
    """Local Hugging Face models (per role), GPU and retriever."""
    from callverse.orchestration.runtime import get_runtime

    return clean(get_runtime().status())


@app.post("/api/system/warmup")
def system_warmup() -> dict[str, Any]:
    """Load the agents' models on the GPU now, so the first chat answers at full speed."""
    from callverse.llm import LLMUnavailableError, get_llm
    from callverse.orchestration.runtime import get_runtime

    llm = get_llm()
    if not llm.available():
        raise HTTPException(409, llm.unavailable_reason() or "LLMs not available")
    try:
        llm.warmup()
        get_runtime().retriever()
    except LLMUnavailableError as error:
        raise HTTPException(409, str(error)) from error
    return clean(get_runtime().status())


# ----------------------------------------------------------------- front office
DEMO_INTENTS = [
    "track_order",
    "delivery_issue",
    "cancel_order",
    "request_refund",
    "damaged_delivery",
    "wrong_item",
    "change_order",
    "request_invoice",
]
# Olist customers are anonymous ids: the portal shows friendly, deterministic demo names.
FIRST_NAMES = [
    "Ana", "Bruno", "Camila", "Diego", "Elisa", "Felipe", "Gabriela", "Hugo", "Isabela", "Joao",
    "Larissa", "Marcos", "Natalia", "Otavio", "Paula", "Rafael", "Sofia", "Thiago", "Vitoria", "Yasmin",
]  # fmt: skip


def _display_name(customer_id: str) -> str:
    number = int(customer_id[:8], 16)
    return f"{FIRST_NAMES[number % len(FIRST_NAMES)]} {chr(65 + (number // 7) % 26)}."


def _timeline(facts: dict[str, Any], as_of: pd.Timestamp) -> list[dict[str, Any]]:
    """Order journey at the contact date: done, current, upcoming or late steps."""

    def stamp(key: str) -> pd.Timestamp | None:
        value = facts.get(key)
        return None if value is None or pd.isna(value) else pd.Timestamp(value)

    steps = [
        ("Order placed", stamp("order_purchase_timestamp"), None),
        ("Payment approved", stamp("order_approved_at"), None),
        ("Handed to the carrier", stamp("order_delivered_carrier_date"), stamp("latest_shipping_limit_date")),
        ("Delivered", stamp("order_delivered_customer_date"), stamp("order_estimated_delivery_date")),
    ]
    rows, current_set = [], False
    for label, done_at, due in steps:
        done = done_at is not None and done_at <= as_of
        late = not done and due is not None and as_of > due
        state = "done" if done else ("late" if late else ("current" if not current_set else "upcoming"))
        if not done:
            current_set = True
        rows.append({"label": label, "state": state, "at": done_at if done else None, "due": due})
    if facts.get("order_status") == "canceled":
        rows.append({"label": "Order canceled", "state": "late", "at": None, "due": None})
    return rows


def _customer_card(contact: pd.Series, profile: Any, with_details: bool = False) -> dict[str, Any]:
    from callverse.agents.advisor.tools import AdvisorTools

    as_of = pd.Timestamp(contact["contact_timestamp"])
    facts = AdvisorTools(as_of=as_of).order_facts(str(contact["order_id"]), str(contact["intent"])) or {}
    card = {
        "contact_id": contact["contact_id"],
        "name": _display_name(str(contact["customer_unique_id"])),
        "city": str(facts.get("customer_city", "")).title(),
        "state": facts.get("customer_state"),
        "persona": profile.persona,
        "tone": profile.tone,
        "is_repeat_contact": profile.is_repeat_contact,
        "intent": contact["intent"],
        "intent_group": contact["intent_group"],
        "opening_message": contact["message_text"],
        "contact_timestamp": as_of,
        "order": {
            "order_id": contact["order_id"],
            "status_at_contact": facts.get("order_status_at_contact"),
            "category": str(facts.get("primary_category_english") or "").replace("_", " "),
            "value": facts.get("order_value"),
            "items": facts.get("item_count"),
            "payment": facts.get("primary_payment_type"),
            "purchased_at": facts.get("order_purchase_timestamp"),
            "estimated_delivery": facts.get("order_estimated_delivery_date"),
            "days_past_estimate": facts.get("days_past_estimate"),
            "needs_investigation": facts.get("needs_investigation"),
        },
    }
    if with_details:
        card["timeline"] = _timeline(facts, as_of)
        history = loaders.contacts()
        history = history[
            (history["customer_unique_id"] == contact["customer_unique_id"])
            & (history["contact_timestamp"] < as_of)
        ]
        card["previous_contacts"] = records(
            history[["contact_id", "contact_timestamp", "intent", "message_text"]].tail(5)
        )
    return card


def _chat_contacts() -> pd.DataFrame:
    contacts = loaders.contacts()
    return contacts[~contacts["bitext_tags"].fillna("").str.contains("W")]


@app.get("/api/portal/customers")
def portal_customers(seed: int = 0) -> list[dict[str, Any]]:
    """Demo customers for the portal: one real contact per main problem type."""
    from callverse.agents.client.profiles import profile_by_contact_id

    contacts = _chat_contacts()
    cards = []
    for intent in DEMO_INTENTS:
        pool = contacts[contacts["intent"] == intent]
        if pool.empty:
            continue
        contact = pool.sample(1, random_state=seed).iloc[0]
        profile = profile_by_contact_id(contacts, contact["contact_id"], seed)
        cards.append(_customer_card(contact, profile))
    return clean(cards)


@app.get("/api/portal/customers/{contact_id}")
def portal_customer(contact_id: str, seed: int = 0) -> dict[str, Any]:
    """One demo customer: order journey at the contact date and previous contacts."""
    from callverse.agents.client.profiles import profile_by_contact_id

    contacts = loaders.contacts()
    match = contacts[contacts["contact_id"] == contact_id]
    if match.empty:
        raise HTTPException(404, f"Unknown contact {contact_id}")
    profile = profile_by_contact_id(contacts, contact_id, seed)
    return clean(_customer_card(match.iloc[0], profile, with_details=True))


@app.get("/api/desk/queue")
def desk_queue(n: int = 10, seed: int = 0) -> list[dict[str, Any]]:
    """Contacts waiting for a human advisor (the Client agent plays each customer)."""
    from callverse.agents.client.profiles import profile_by_contact_id

    contacts = _chat_contacts()
    sample = contacts.sample(n, random_state=seed)
    rng = np.random.default_rng(seed)
    queue = []
    for contact in sample.itertuples(index=False):
        profile = profile_by_contact_id(contacts, contact.contact_id, seed)
        queue.append(
            {
                "contact_id": contact.contact_id,
                "name": _display_name(str(contact.customer_unique_id)),
                "intent": contact.intent,
                "intent_group": contact.intent_group,
                "message_text": contact.message_text,
                "persona": profile.persona,
                "is_repeat_contact": profile.is_repeat_contact,
                "waiting_seconds": int(rng.integers(5, 240)),
                "channel": "chat",
            }
        )
    return clean(sorted(queue, key=lambda q: -q["waiting_seconds"]))


# ------------------------------------------------------------------ help centre
def _kb_docs() -> dict[str, Any]:
    from callverse.agents.advisor import load_knowledge_base_config
    from callverse.config import config_path

    docs_dir = load_knowledge_base_config(config_path("agents"), PROJECT_ROOT).docs_dir
    return {p.stem: p for p in sorted(docs_dir.glob("*.md"))}


def _article(path: Any) -> dict[str, Any]:
    """Front matter (YAML) + Markdown body without the retrieval comments."""
    import re

    import yaml

    text = path.read_text(encoding="utf-8")
    meta: dict[str, Any] = {}
    if text.startswith("---"):
        _, header, text = text.split("---", 2)
        meta = yaml.safe_load(header) or {}
    body = re.sub(r"<!--.*?-->\n?", "", text, flags=re.S).strip()
    title = meta.get("title") or next(
        (line[2:].strip() for line in body.splitlines() if line.startswith("# ")), path.stem
    )
    paragraphs = [
        line for line in body.splitlines() if line.strip() and not line.startswith(("#", "|", "-", "1."))
    ]
    return {
        "id": path.stem,
        "title": title,
        "type": meta.get("doc_type"),
        "intents": meta.get("intents", []),
        "summary": (paragraphs[0] if paragraphs else "")[:220],
        "sections": [line[3:].strip() for line in body.splitlines() if line.startswith("## ")],
        "internal": meta.get("doc_type") == "playbook" or path.stem == "advisor_playbook",
        "markdown": body,
    }


@app.get("/api/kb/articles")
def kb_articles() -> list[dict[str, Any]]:
    """Help-centre articles = the advisor's knowledge base (one source of truth)."""
    return [{k: v for k, v in _article(path).items() if k != "markdown"} for path in _kb_docs().values()]


@app.get("/api/kb/articles/{article_id}")
def kb_article(article_id: str) -> dict[str, Any]:
    docs = _kb_docs()
    if article_id not in docs:
        raise HTTPException(404, f"Unknown article {article_id}")
    return _article(docs[article_id])


@app.get("/api/kb/search")
def kb_search(q: str, k: int = 5) -> dict[str, Any]:
    """Semantic search (bge-m3 + FAISS, or the TF-IDF backup) over the knowledge base."""
    from callverse.orchestration.runtime import get_runtime

    runtime = get_runtime()
    retriever = runtime.retriever()
    started = time.perf_counter()
    hits = retriever.search(q, top_k=k) if q.strip() else []
    return clean(
        {
            "query": q,
            "retriever": runtime.retriever_name,
            "latency_ms": (time.perf_counter() - started) * 1000,
            "results": [
                {
                    "chunk_id": h.chunk.chunk_id,
                    "article": h.chunk.chunk_id.split("__")[0],
                    "section": h.chunk.section,
                    "text": h.chunk.text[:600],
                    "score": h.score,
                }
                for h in hits
            ],
        }
    )


# ------------------------------------------------------------ live conversation
@app.websocket("/ws/session")
async def ws_session(websocket: WebSocket) -> None:
    """A conversation where a human plays the customer or the advisor.

    First message: ``{"type": "start", "contact_id", "customer": "human"|"agent",
    "advisor": "human"|"agent", "mode", "variant", "seed"}``. Then the UI sends
    ``customer_message`` / ``advisor_message`` / ``suggest`` / ``autopilot`` / ``end``
    and receives ``ready``, ``message``, ``token``, ``stage``, ``routing``,
    ``suggestion``, ``review`` and ``done`` events.
    """
    from callverse.orchestration.live import LiveSession

    await websocket.accept()
    loop = asyncio.get_running_loop()
    outbox: asyncio.Queue = asyncio.Queue()

    def emit(kind: str, data: dict[str, Any]) -> None:
        loop.call_soon_threadsafe(outbox.put_nowait, {"type": kind, **clean(data)})

    async def sender() -> None:
        while (message := await outbox.get()) is not None:
            try:
                await websocket.send_json(message)
            except (WebSocketDisconnect, RuntimeError):
                return

    sending = asyncio.create_task(sender())
    try:
        start = await websocket.receive_json()
        seed = int(start.get("seed", 0))
        profile = _profile(start.get("contact_id"), seed)
        session = await asyncio.to_thread(
            LiveSession,
            profile,
            emit,
            start.get("mode", "auto"),
            seed,
            start.get("variant"),
            start.get("customer", "human"),
            start.get("advisor", "agent"),
        )
        advisor = session.session.advisor
        llm = advisor.use_llm()
        emit(
            "ready",
            {
                "profile": profile.to_dict(),
                "llm": llm,
                "model": advisor.llm.resolve_model("advisor") if llm and advisor.llm else None,
                "retriever": type(advisor.retriever).__name__,
            },
        )
        await asyncio.to_thread(session.begin)
        while not session.finished:
            message = await websocket.receive_json()
            await asyncio.to_thread(session.handle, message)
    except WebSocketDisconnect:
        pass
    except Exception as error:  # surfaced to the UI
        emit("error", {"message": str(error)})
    finally:
        outbox.put_nowait(None)
        await sending
        try:
            await websocket.close()
        except (RuntimeError, WebSocketDisconnect):
            pass  # the browser already closed it
