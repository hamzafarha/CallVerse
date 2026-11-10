"""FastAPI backend of CallVerse (REST + WebSocket), shared by both React apps.

Run with ``callverse serve`` (or ``uvicorn callverse.api.app:app``).

- Front office (``frontend/front-office``): customer portal, live chat with the
  Advisor agent and the advisor desk -> ``/api/portal``, ``/api/kb``, ``/api/desk``,
  ``/ws/session``.
- Back office (``frontend/back-office``): the managers' control room -> every
  other route (forecast, workforce, twin, agents, quality, evaluation, MLOps), and
  the contact centre page -> ``/api/centre``, ``/ws/centre``.
"""

# How to read this file: one Python function per URL. The decorator gives the HTTP method and the path:
# @app.get("/api/forecast") answers GET requests on that path, and FastAPI turns the returned dictionary into
# JSON. Sections: overview, data, forecast, twin, workforce, agents, quality, evaluation, MLOps, system
# (LLMs), MCP, front office (portal, desk), help centre, the live WebSocket, and the contact centre page at
# the end. The MCP server itself answers at /mcp (see callverse/mcp/desk.py).
import asyncio
import json
import threading
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache
from typing import Any

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from callverse.api.schemas import (
    CentreArrival,
    ConversationRequest,
    HumanLabel,
    NewCustomerRequest,
    TwinCompareRequest,
    TwinRunRequest,
)
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
from callverse.mcp.desk import HttpEndpoint

# Settings from configs/app.yaml (version, description, allowed browser origins).
settings = load_yaml("app")


@lru_cache(maxsize=1)
def mcp_catalog() -> Any:
    """The menu of the CallVerse MCP server for outside apps (callverse/mcp/desk.py), with the API's twin."""
    from callverse.mcp.desk import CaseDesk, desk_catalog

    return desk_catalog(CaseDesk(twin=twin))


# MCP over HTTP at /mcp (Streamable HTTP): MCP clients on this PC (e.g. the MCP Inspector) connect to
# http://127.0.0.1:8000/mcp while the API runs.
MCP_HTTP = HttpEndpoint(lambda: mcp_catalog().server())


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """What runs for the whole life of the API: the MCP connection manager of /mcp."""
    async with MCP_HTTP.running():
        yield


app = FastAPI(
    title="CallVerse API",
    version=settings["app"]["version"],
    description=settings["app"]["description"],
    lifespan=lifespan,
)
app.add_route("/mcp", MCP_HTTP, include_in_schema=False)
# CORS: allow the two React apps (served on other ports, 5173 and 5174) to call this API from the browser.
app.add_middleware(
    CORSMiddleware, allow_origins=settings["server"]["cors_origins"], allow_methods=["*"], allow_headers=["*"]
)


# --------------------------------------------------------------------- overview
@app.get("/api/health")
def health() -> dict[str, Any]:
    """A quick "is the server alive?" check."""
    return {"status": "ok", "version": settings["app"]["version"]}


@app.get("/api/overview")
def overview() -> dict[str, Any]:
    """Headline numbers, BO/DSO definitions and the scorecard."""
    # clean() turns numpy and pandas values into plain JSON (NaN -> null).
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
    # Contacts per week and problem group, for the stacked chart of the Data page.
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
    # Run the data contracts live and show their results.
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
    # Keep the 1-7 day ahead forecasts and pivot them: one column per model.
    horizon1 = backtest[(backtest["horizon"].between(1, 7))]
    total = horizon1[horizon1["intent_group"] == "total"].pivot_table(
        index="date", columns="model", values="forecast", aggfunc="mean"
    )
    total["actual"] = horizon1[horizon1["intent_group"] == "total"].groupby("date")["actual"].first()
    total = total.reset_index()
    by_group = horizon1[(horizon1["model"] == "lightgbm") & (horizon1["intent_group"] != "total")]
    by_group = by_group.groupby(["date", "intent_group"])[["forecast", "actual"]].mean().reset_index()
    # wMAPE by horizon: is the forecast worse 7 days ahead than 1 day ahead?
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
    """Scenarios, planners and routers, for the Scenario lab menus."""
    from callverse.agents.workforce.routing import ppo_available

    return clean({**twin().describe(), "ppo_available": ppo_available()})


def _spec(request: TwinRunRequest):
    """The scenario, with the custom what-if values of the page applied on top."""
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
    # Run the configuration over several seeds; a missing artifact (no forecast or no PPO model yet) gives
    # HTTP 409 with the reason.
    try:
        spec = _spec(request)
        started = time.perf_counter()
        runs = twin().run(
            spec, request.plan, request.router, request.seeds, request.prepared, trace_first=True
        )
    except FileNotFoundError as error:
        raise HTTPException(409, str(error)) from error
    elapsed = time.perf_counter() - started
    # Mean and 95% CI of every KPI over the seeds.
    frame = pd.DataFrame([{"seed": r.seed, **r.kpis} for r in runs]).assign(config="run")
    summary = summarize_runs(frame, ["config"], SIM_KPIS)
    # The queue of the first seed, averaged per hour, for the chart.
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
    # The same seeds for every option (common random numbers), then one summary per option.
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
    # Downsample a long learning curve to about 400 points (lighter for the browser).
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
    # Skip offensive messages (Bitext tag W).
    contacts = contacts[~contacts["bitext_tags"].fillna("").str.contains("W")]
    sample = contacts.sample(n, random_state=seed)
    return records(sample[["contact_id", "contact_timestamp", "intent", "intent_group", "message_text"]])


def _profile(contact_id: str | None, seed: int):
    """The customer profile of a given contact (history or brand-new customer), or of a random one."""
    from callverse.agents.client.profiles import find_profile, sample_profiles

    if contact_id:
        return find_profile(contact_id, seed)
    return sample_profiles(loaders.contacts(), 1, seed)[0]


@app.post("/api/agents/conversation")
def agents_conversation(request: ConversationRequest) -> dict[str, Any]:
    """Run one LangGraph conversation and return the final state."""
    from callverse.orchestration.graph import run_conversation, save_transcript

    try:
        profile = _profile(request.contact_id, request.seed)
    except KeyError as error:
        raise HTTPException(404, str(error)) from error
    # Run the whole graph at once, save the transcript, return the final state.
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
    # The graph runs in a background thread; its updates reach this async function through a queue
    # (call_soon_threadsafe), and are then sent to the browser.
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

    # Pick a historical chat that this person has not graded yet.
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

    # Save one human grade (used to calibrate the judge).
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

    # Summarise the LLM trace file per agent: calls, share answered from the cache, latency, tokens.
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
    """LLM provider (OpenRouter, or the local backup), models per role, GPU and retriever."""
    from callverse.orchestration.runtime import get_runtime

    return clean(get_runtime().status())


@app.post("/api/system/warmup")
def system_warmup() -> dict[str, Any]:
    """Load the agents' models on the GPU now, so the first chat answers at full speed."""
    from callverse.llm import LLMUnavailableError, get_llm
    from callverse.orchestration.runtime import get_runtime

    # Only when an LLM can run; otherwise HTTP 409 with the reason.
    llm = get_llm()
    if not llm.available():
        raise HTTPException(409, llm.unavailable_reason() or "LLMs not available")
    try:
        llm.warmup()
        get_runtime().retriever()
    except LLMUnavailableError as error:
        raise HTTPException(409, str(error)) from error
    return clean(get_runtime().status())


# -------------------------------------------------------------------------- MCP
@app.get("/api/mcp")
async def mcp_overview(request: Request) -> dict[str, Any]:
    """The CallVerse MCP server as a client sees it (tools, resources, prompts) and how to connect."""
    from mcp import Client

    from callverse.mcp.client import read_menu
    from callverse.mcp.desk import connection_info
    from callverse.orchestration.runtime import get_runtime

    # Read the menu THROUGH the protocol, like any MCP client (an in-process connection to the same server).
    catalog = mcp_catalog()
    async with Client(catalog.server()) as client:
        menu = await read_menu(client)
    for tool in menu["tools"]:
        tool["group"] = catalog.tools[tool["name"]].group if tool["name"] in catalog.tools else "advisor"
    advisor = get_runtime().settings["advisor"]
    return {
        "server": {"name": "callverse", "instructions": catalog.instructions},
        **menu,
        "advisor": {
            "tool_transport": advisor.get("tool_transport", "mcp"),
            "variant": advisor.get("variant"),
        },
        "connect": connection_info(f"{str(request.base_url).rstrip('/')}/mcp"),
    }


# ----------------------------------------------------------------- front office
# One demo customer per main problem type, on the portal's home page.
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
    """A friendly, stable fake name made from the customer id (e.g. "Hugo H.")."""
    number = int(customer_id[:8], 16)
    return f"{FIRST_NAMES[number % len(FIRST_NAMES)]} {chr(65 + (number // 7) % 26)}."


def _seconds(value: Any) -> float | None:
    """A duration sent by the UI (None when missing or not a positive number)."""
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return None
    return seconds if 0 <= seconds < 7 * 24 * 3600 else None


def _customer_card(
    contact: pd.Series, profile: Any, with_details: bool = False, new: dict[str, Any] | None = None
) -> dict[str, Any]:
    """A customer as the portal shows it. `new`: the record of a brand-new customer (its own name)."""
    from callverse.agents.advisor.tools import AdvisorTools
    from callverse.agents.client.order_page import order_timeline

    # The order as of the chat date: the twin replays history.
    as_of = pd.Timestamp(contact["contact_timestamp"])
    facts = AdvisorTools(as_of=as_of).order_facts(str(contact["order_id"]), str(contact["intent"])) or {}
    card = {
        "contact_id": contact["contact_id"],
        "name": new["name"] if new else _display_name(str(contact["customer_unique_id"])),
        "is_new": new is not None,
        "order_source": new["order_source"] if new else "history",
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
        card["timeline"] = order_timeline(facts, as_of)  # the same page the Client agent can open
        # Earlier contacts of the same customer, before this one.
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
    """The contacts usable in a chat demo (no offensive messages)."""
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
        # Not in the history: a brand-new customer created on the portal?
        card = _new_customer_card(contact_id, with_details=True)
        if card is None:
            raise HTTPException(404, f"Unknown contact {contact_id}")
        return clean(card)
    profile = profile_by_contact_id(contacts, contact_id, seed)
    return clean(_customer_card(match.iloc[0], profile, with_details=True))


# -------------------------------------------------------- brand-new customers
# Friendly names of the 17 problems (intents) for the "new customer" form.
PROBLEM_LABELS = {
    "track_order": "Where is my order?",
    "track_delivery": "I want to track my delivery",
    "delivery_time": "When will my order arrive?",
    "delivery_issue": "There is a problem with my delivery",
    "cancel_order": "I want to cancel my order",
    "request_refund": "I want a refund",
    "refund_status": "Where is my refund?",
    "product_issue": "The product does not work",
    "wrong_item": "I received the wrong item",
    "damaged_delivery": "My item arrived damaged",
    "missing_item": "An item is missing from my order",
    "return_product": "I want to return a product",
    "return_product_online": "I want to return a product online",
    "exchange_product": "I want to exchange a product",
    "change_order": "I want to change my order",
    "request_invoice": "I need my invoice",
    "payment_issue": "There is a problem with my payment",
}
BR_STATES = [
    "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG", "MS", "MT", "PA",
    "PB", "PE", "PI", "PR", "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO",
]  # fmt: skip


def _new_customer_card(contact_id: str, with_details: bool = False) -> dict[str, Any] | None:
    """The portal card of a brand-new customer, or None when the id is unknown."""
    from callverse.agents.client.profiles import profile_from_record
    from callverse.data.new_customers import get_new_customer

    record = get_new_customer(contact_id)
    if record is None:
        return None
    return _customer_card(pd.Series(record), profile_from_record(record), with_details, new=record)


@app.get("/api/portal/new-customer-options")
def new_customer_options() -> dict[str, Any]:
    """Everything the "new customer" form offers: problems (with a real example message), categories,
    payment types, states and the allowed dates (the history: the twin replays those days)."""
    from callverse.data import new_customers

    groups = new_customers.intent_groups()
    first, last = new_customers.contact_date_range()
    categories = loaders.orders_analytical()["primary_category_english"].dropna().value_counts().head(24)
    return clean(
        {
            "problems": [
                {
                    "intent": intent,
                    "label": label,
                    "group": groups.get(intent),
                    "example": new_customers.example_message(intent),
                }
                for intent, label in PROBLEM_LABELS.items()
            ],
            "categories": [c.replace("_", " ") for c in categories.index],
            "payment_types": list(new_customers.PAYMENT_TYPES),
            "states": BR_STATES,
            "personas": list(new_customers.PERSONAS),
            "dates": {"first": first.date().isoformat(), "last": last.date().isoformat()},
        }
    )


@app.post("/api/portal/customers")
def create_customer(request: NewCustomerRequest) -> dict[str, Any]:
    """Create a brand-new customer, on a real order or on an order typed in the form."""
    from callverse.data import new_customers

    try:
        if request.order_source == "real":
            record = new_customers.create_with_real_order(
                request.name, request.persona, request.intent, request.message
            )
        else:
            if request.order is None:
                raise ValueError("Invent the order first: its dates, value and status are missing.")
            o = request.order
            order = new_customers.InventedOrder(
                category=o.category,
                value_brl=o.value_brl,
                items=o.items,
                payment_type=o.payment_type,
                city=o.city,
                state=o.state,
                purchased_at=pd.Timestamp(o.purchased_at),
                estimated_delivery=pd.Timestamp(o.estimated_delivery),
                progress=o.progress,
                shipped_at=pd.Timestamp(o.shipped_at) if o.shipped_at else None,
                delivered_at=pd.Timestamp(o.delivered_at) if o.delivered_at else None,
            )
            record = new_customers.create_with_invented_order(
                request.name,
                request.persona,
                request.intent,
                order,
                pd.Timestamp(o.contact_at),
                request.message,
            )
    except ValueError as error:  # a field that cannot be true: tell the form why
        raise HTTPException(422, str(error)) from error
    return clean(_new_customer_card(record["contact_id"], with_details=True))


@app.get("/api/portal/new-customers")
def list_new_customers() -> list[dict[str, Any]]:
    """The brand-new customers created on the portal, newest first."""
    from callverse.data.new_customers import list_new_customers as read_all

    cards = [_new_customer_card(record["contact_id"]) for record in read_all()]
    return clean([card for card in cards if card])


@app.delete("/api/portal/new-customers/{contact_id}")
def delete_new_customer(contact_id: str) -> dict[str, Any]:
    """Remove a brand-new customer (and its invented order, if it had one)."""
    from callverse.data.new_customers import delete_new_customer as remove

    if not remove(contact_id):
        raise HTTPException(404, f"Unknown new customer {contact_id}")
    return {"deleted": contact_id}


@app.get("/api/desk/queue")
def desk_queue(n: int = 10, seed: int = 0) -> list[dict[str, Any]]:
    """Contacts waiting for a human advisor (the Client agent plays each customer)."""
    from callverse.agents.client.profiles import profile_by_contact_id

    contacts = _chat_contacts()
    sample = contacts.sample(n, random_state=seed)
    # The queue's waiting times are random demo values (5 to 240 s); the desk page then makes them tick.
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
    """The knowledge-base Markdown files, by id."""
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
        # Split the "---" front matter (YAML) from the Markdown body, and drop the hidden retrieval comments.
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
        # The advisor playbook is internal: it is not shown to customers.
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
def _customer_name(profile: Any) -> str:
    """The name shown for a customer: the one typed for a new customer, else the stable demo name."""
    from callverse.data.new_customers import get_new_customer

    record = get_new_customer(profile.contact_id)
    return record["name"] if record else _display_name(profile.customer_unique_id)


def _ready_payload(session: Any, profile: Any) -> dict[str, Any]:
    """The "ready" event: who the customer is, which provider and model answer, who answers (autopilot)."""
    advisor = session.session.advisor
    llm = advisor.use_llm()
    return {
        "profile": profile.to_dict(),
        "name": _customer_name(profile),
        "llm": llm,
        "model": advisor.llm.resolve_model("advisor") if llm and advisor.llm else None,
        "provider": advisor.llm.backend() if llm and advisor.llm else "off",
        "retriever": type(advisor.retriever).__name__,
        "autopilot": session.advisor == "agent",
        "customer": session.customer,  # "human" (a person) or "agent" (the Client agent)
        "channel": session.channel,
    }


async def _shared_call(websocket: WebSocket, start: dict[str, Any], deliver: Any) -> None:
    """A phone call (orchestration/calls.py): the phone starts it as the customer; the desk joins as the
    advisor. Every screen receives the same events; a screen that joins late first gets the story so far."""
    from callverse.orchestration.calls import HUB, PHONE_GRACE_SECONDS

    if start.get("type") == "join":
        call = HUB.get(start.get("session_id"))
        role = "advisor" if start.get("role") == "advisor" else "customer"
        if call is None:
            deliver({"type": "error", "message": "This call has ended or does not exist any more."})
            return
    else:
        seed = int(start.get("seed", 0))
        profile = _profile(start.get("contact_id"), seed)
        call = await asyncio.to_thread(
            HUB.open, profile, _customer_name(profile), start.get("mode", "auto"), seed, start.get("variant")
        )
        role = "customer"
        call.emit("ready", {**clean(_ready_payload(call.live, profile)), "session_id": call.id})
    token = call.subscribe(deliver)
    if role == "customer":
        call.customer_connected = True
    try:
        while not call.live.finished:
            message = await websocket.receive_json()
            try:
                await asyncio.to_thread(call.handle, message, role)
            except ValueError as error:  # a message this side may not send now: tell this screen only
                deliver({"type": "error", "message": str(error)})
    finally:
        call.unsubscribe(token)
        if role == "customer":
            call.customer_connected = False
            if not call.live.finished:
                # The phone may only have locked its screen: if it is not back in 2 minutes, the customer
                # leaves the contact centre page.
                asyncio.get_running_loop().call_later(PHONE_GRACE_SECONDS, call.close_if_abandoned)


@app.get("/api/phone/calls")
def phone_calls() -> list[dict[str, Any]]:
    """The phone calls for the advisor desk: ringing, talking, or ended in the last 30 minutes."""
    from callverse.orchestration.calls import HUB

    return clean(HUB.calls())


@app.get("/api/phone/info")
def phone_info() -> dict[str, Any]:
    """The link to open on a phone (same Wi-Fi), and whether the HTTPS certificate exists."""
    from callverse.api.phone_setup import certificate_ready, lan_addresses, phone_links

    addresses = lan_addresses()
    return {
        "addresses": addresses,
        "links": phone_links(addresses),
        "certificate": certificate_ready(),
        "setup": ["callverse phone-cert", "cd frontend && npm run dev:phone"],
    }


@app.websocket("/ws/session")
async def ws_session(websocket: WebSocket) -> None:
    """A conversation where a human plays the customer or the advisor.

    First message: ``{"type": "start", "contact_id", "customer": "human"|"agent",
    "advisor": "human"|"agent", "mode", "variant", "seed", "waited_seconds"}``
    (``waited_seconds``: the advisor desk's queue time of the customer). Then the UI sends
    ``customer_message`` / ``advisor_message`` / ``suggest`` / ``autopilot`` / ``end``
    and receives ``ready``, ``message``, ``token``, ``stage``, ``routing``,
    ``suggestion``, ``review`` and ``done`` events.
    """
    from callverse.orchestration.centre import CENTRE, ChatFeed, centre_channel
    from callverse.orchestration.live import LiveSession

    await websocket.accept()
    loop = asyncio.get_running_loop()
    # Bridge between the agents' thread and this async function: emit() puts events in the outbox, sender()
    # sends them to the browser, in order.
    outbox: asyncio.Queue = asyncio.Queue()
    feed: ChatFeed | None = None  # the same chat, copied to the contact centre page (/ws/centre)

    def emit(kind: str, data: dict[str, Any]) -> None:
        loop.call_soon_threadsafe(outbox.put_nowait, {"type": kind, **clean(data)})
        if feed is not None:
            feed.emit(kind, data)

    async def sender() -> None:
        while (message := await outbox.get()) is not None:
            try:
                await websocket.send_json(message)
            except (WebSocketDisconnect, RuntimeError):
                return

    def deliver(event: dict[str, Any]) -> None:
        """Same as emit(), for an event that is already complete (phone calls share their events)."""
        loop.call_soon_threadsafe(outbox.put_nowait, clean(event))

    sending = asyncio.create_task(sender())
    try:
        # 1) The first message configures the session (who plays which side, LLM mode, advisor variant).
        start = await websocket.receive_json()
        # A phone call, or a screen joining one (the desk, or a phone that reconnects): shared conversation.
        if start.get("type") == "join" or start.get("channel") == "phone":
            await _shared_call(websocket, start, deliver)
            return
        seed = int(start.get("seed", 0))
        profile = _profile(start.get("contact_id"), seed)
        # asyncio.to_thread: run the slow agent code in a worker thread, so the server stays responsive.
        session = await asyncio.to_thread(
            LiveSession,
            profile,
            emit,
            start.get("mode", "auto"),
            seed,
            start.get("variant"),
            start.get("customer", "human"),
            start.get("advisor", "agent"),
            _seconds(start.get("waited_seconds")),
            # "visitor": a person speaking into the contact centre page's microphone; else a web chat
            channel="visitor" if start.get("channel") == "visitor" else "web",
        )
        # 2) The contact centre page follows the chat too; tell the browser which provider and model answer.
        feed = CENTRE.open(centre_channel(session.channel, session.customer), _customer_name(profile))
        emit("ready", _ready_payload(session, profile))
        # 3) The Client agent opens (when it plays the customer); then each browser message is handled until
        # the chat ends.
        await asyncio.to_thread(session.begin)
        while not session.finished:
            message = await websocket.receive_json()
            await asyncio.to_thread(session.handle, message)
    except WebSocketDisconnect:
        pass
    except Exception as error:  # surfaced to the UI
        emit("error", {"message": str(error)})
    # 4) Always: end the story on the centre page (a tab closed before the end: the customer leaves), stop the
    # sender and close the socket.
    finally:
        if feed is not None:
            feed.close()
        outbox.put_nowait(None)
        await sending
        try:
            await websocket.close()
        except (RuntimeError, WebSocketDisconnect):
            pass  # the browser already closed it


# ---------------------------------------------------------- contact centre (back office /centre)
def _saved_customer_name(chat: dict[str, Any]) -> str:
    """The customer's name in the advisor history: the typed name of a new customer, else the demo name."""
    from callverse.data.new_customers import get_new_customer

    record = get_new_customer(chat.get("contact_id") or "")
    if record:
        return record["name"]
    try:
        return _display_name(chat.get("customer_unique_id") or "")
    except ValueError:  # not a hexadecimal Olist id
        return "Customer"


@app.get("/api/centre/advisors")
def centre_advisors() -> dict[str, Any]:
    """The centre's KPI wall (totals) and one line per advisor desk, from the finished live chats."""
    from callverse.orchestration.centre import advisors_summary, saved_chats

    return clean(advisors_summary(saved_chats()))


@app.get("/api/centre/advisors/{advisor_id}")
def centre_advisor(advisor_id: str) -> dict[str, Any]:
    """One advisor's finished chats, newest first, each with the Quality agent's scorecard."""
    from callverse.orchestration.centre import advisors_summary, saved_chats

    chats = [chat for chat in saved_chats() if chat["advisor"] == advisor_id]
    for chat in chats:
        chat["customer"] = _saved_customer_name(chat)
    lines = advisors_summary(chats)["advisors"]
    return clean({"id": advisor_id, "summary": lines[0] if lines else None, "chats": chats})


@app.post("/api/centre/arrivals")
async def centre_arrival(request: CentreArrival) -> dict[str, Any]:
    """A customer walks into the centre: the Client agent plays the customer, the Advisor agent answers,
    and every step goes to the centre screens (/ws/centre). One of the centre's own customers at a time."""
    from callverse.orchestration.centre import CENTRE, CentreBusy
    from callverse.orchestration.live import LiveSession

    if CENTRE.running("centre"):
        raise HTTPException(409, "A customer is already being served: wait until the story ends.")
    try:
        profile = await asyncio.to_thread(_profile, request.contact_id, request.seed)
    except KeyError as error:
        raise HTTPException(404, str(error)) from error
    try:
        feed = CENTRE.open("centre", _customer_name(profile), limit=1)
    except CentreBusy as error:  # two clicks at the same moment
        raise HTTPException(409, str(error)) from error
    try:
        # The same agents as every chat; feed.emit sends each step to the centre screens.
        session = await asyncio.to_thread(
            LiveSession,
            profile,
            feed.emit,
            request.mode,
            request.seed,
            request.variant,
            customer="agent",
            advisor="agent",
            channel="centre",
        )
    except Exception:
        feed.close()
        raise
    feed.emit("ready", _ready_payload(session, profile))
    # The whole chat runs in its own thread: this request answers at once, and the centre follows the events.
    threading.Thread(target=feed.run, args=(session.begin,), name=f"centre-{feed.id}", daemon=True).start()
    return {"chat": feed.id, "name": feed.name, "contact_id": profile.contact_id}


@app.websocket("/ws/centre")
async def ws_centre(websocket: WebSocket) -> None:
    """The centre page's live feed: ``{"chat", "channel", "event"}`` for every step of every running chat
    (first the story so far of the chats already running). The page only listens; it sends nothing."""
    from callverse.orchestration.centre import CENTRE

    await websocket.accept()
    loop = asyncio.get_running_loop()
    outbox: asyncio.Queue = asyncio.Queue()
    # Called by the agents' threads: hand the event over to this async function (same bridge as /ws/session).
    token = CENTRE.subscribe(lambda message: loop.call_soon_threadsafe(outbox.put_nowait, clean(message)))

    async def sender() -> None:
        while True:
            await websocket.send_json(await outbox.get())

    async def listener() -> None:
        while True:
            await websocket.receive_text()  # nothing is expected: this only notices when the page closes

    tasks = [asyncio.create_task(sender()), asyncio.create_task(listener())]
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    finally:
        CENTRE.unsubscribe(token)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        try:
            await websocket.close()
        except (RuntimeError, WebSocketDisconnect):
            pass  # the browser already closed it
