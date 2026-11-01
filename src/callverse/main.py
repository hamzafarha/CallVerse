"""CallVerse command line: every stage of the pipeline, and the whole pipeline.

callverse all              # data -> forecast -> RL -> evaluation (end to end)
callverse serve            # FastAPI backend for the React control room
callverse --help           # every command
"""

import json
import os
import time
from typing import Optional

import typer

app = typer.Typer(
    name="callverse",
    help="CallVerse: multi-agent digital twin of an e-commerce customer service center.",
    no_args_is_help=True,
    pretty_exceptions_show_locals=False,
)


def say(text: str) -> None:
    typer.echo(text)


def stage(title: str) -> None:
    typer.secho(f"\n=== {title} ===", fg=typer.colors.CYAN, bold=True)


# ------------------------------------------------------------------------- data
@app.command()
def data(
    notebooks: bool = typer.Option(True, help="Re-run the preparation notebooks 03-08."),
    database: bool = typer.Option(True, help="Rebuild tickets, chats and the SQLite store."),
    knowledge_base: bool = typer.Option(True, help="Rebuild the bge-m3 FAISS index."),
) -> None:
    """Data layer: prepare Olist + Bitext, generate contacts, validate, build stores."""
    from callverse.config import ensure_dirs
    from callverse.data import loaders

    ensure_dirs()
    if notebooks:
        from callverse.data.pipeline import run_data_pipeline

        stage("Data preparation notebooks (03 -> 08)")
        run_data_pipeline(log=say)
        loaders.clear_caches()
    if database:
        stage("Tickets, chat logs and SQLite store")
        import runpy

        from callverse.config import PROJECT_ROOT

        runpy.run_path(str(PROJECT_ROOT / "scripts" / "build_database.py"), run_name="__main__")
    validate()
    if knowledge_base:
        stage("Knowledge base index (bge-m3 + FAISS)")
        try:
            import runpy

            from callverse.config import PROJECT_ROOT

            runpy.run_path(str(PROJECT_ROOT / "scripts" / "build_knowledge_base.py"), run_name="__main__")
        except Exception as error:  # model download can fail offline: keyword search still works
            typer.secho(
                f"Knowledge base index not rebuilt ({error}). The advisor falls back to keyword search.",
                fg=typer.colors.YELLOW,
            )


@app.command()
def validate() -> None:
    """Check the Pandera data contracts of the processed tables."""
    from callverse.data.validation import validate_processed_data

    stage("Data contracts (Pandera)")
    results = validate_processed_data()
    for result in results:
        mark = "PASS" if result.passed else "FAIL"
        say(f"  [{mark}] {result.table:<36} {result.rows:>8,} rows {result.errors}")
    if not all(r.passed for r in results):
        raise typer.Exit(code=1)


# --------------------------------------------------------------------- forecast
@app.command()
def forecast(fast: bool = typer.Option(False, help="Skip SARIMA and Prophet (1 min instead of 5).")) -> None:
    """DSO4: rolling-origin backtest of 5 models, final LightGBM, next-week forecast."""
    from callverse.forecasting.train import run_forecast_stage

    stage("Contact volume forecast (DSO4)")
    run_forecast_stage(fast=fast, log=say)


# ------------------------------------------------------------------- workforce
@app.command("train-rl")
def train_rl(
    timesteps: Optional[int] = typer.Option(None, help="PPO decisions (default from agents.yaml)."),
) -> None:
    """DSO1: tune the skill-score backup, then train the MaskablePPO routing agent."""
    from callverse.agents.workforce.optimization import optimize_skill_weights
    from callverse.agents.workforce.train import train_routing_policy

    stage("Skill-score weights (DSO1 backup)")
    optimize_skill_weights(log=say)
    stage("MaskablePPO routing agent (DSO1 main idea)")
    train_routing_policy(timesteps, log=say)


@app.command()
def schedule(
    scenario: str = typer.Option("baseline", help="Scenario of configs/scenarios.yaml."),
    planner: str = typer.Option("cpsat", help="cpsat, rules_erlang, fixed, fixed_tuned, erlang_hourly."),
    unprepared: bool = typer.Option(False, help="Plan from the normal forecast."),
) -> None:
    """DSO3: plan a week of shifts and overtime from the forecast."""
    from callverse.agents.workforce.scheduling import roster_compliance
    from callverse.twin import DigitalTwin

    twin = DigitalTwin()
    spec = twin.scenario(scenario)
    plan = twin.plan(spec, planner, prepared=not unprepared)
    costs = twin.settings.costs
    stage(f"{planner} plan for {spec.label} ({spec.week_start.date()})")
    say(
        json.dumps(
            {
                k: round(v, 1)
                for k, v in plan.planned_cost(costs.regular_hourly, costs.overtime_multiplier).items()
            },
            indent=2,
        )
    )
    say("Agents per hour (rows = days, 08:00-21:00):")
    for day in range(plan.days):
        regular = plan.regular[day, 8:22]
        overtime = plan.overtime[day, 8:22]
        say(f"  day {day}: " + " ".join(f"{r}{'+' + str(o) if o else ''}" for r, o in zip(regular, overtime)))
    if not plan.roster.empty:
        say(f"Roster compliance: {roster_compliance(plan.roster, twin.rules)}")


@app.command()
def simulate(
    scenario: str = typer.Option("baseline"),
    planner: str = typer.Option("cpsat"),
    router: str = typer.Option("fifo", help="fifo, skill_score or ppo."),
    seeds: int = typer.Option(10),
    unprepared: bool = typer.Option(False),
) -> None:
    """Run the digital twin on a scenario week (mean and 95% CI over seeds)."""
    from callverse.evaluation.business_kpis import format_mean_ci, summarize_runs
    from callverse.evaluation.experiments import SIM_KPIS
    from callverse.twin import DigitalTwin, runs_to_frame

    twin = DigitalTwin()
    started = time.perf_counter()
    frame = runs_to_frame(twin.run(scenario, planner, router, seeds, prepared=not unprepared))
    summary = summarize_runs(frame, ["scenario"], SIM_KPIS)
    stage(
        f"{scenario} | plan {planner} | router {router} | {'unprepared' if unprepared else 'prepared'}"
        f" | {seeds} seeds in {time.perf_counter() - started:.1f}s"
    )
    for row in summary.itertuples():
        say(f"  {row.label:<36} {format_mean_ci(pd_row(row))}")


def pd_row(row):
    import pandas as pd

    return pd.Series(row._asdict())


@app.command()
def fidelity() -> None:
    """DSO4: twin fidelity checks (Erlang C, volume, time of day, handle time)."""
    from callverse.evaluation.twin_metrics import run_fidelity

    report = run_fidelity()
    stage("Twin fidelity")
    say(report["checks"][["check", "value", "passed", "detail"]].to_string(index=False))
    say(report["erlang"][["metric", "simulated", "expected", "passed"]].round(3).to_string(index=False))


# ----------------------------------------------------------------------- agents
@app.command()
def chat(
    contact: Optional[str] = typer.Option(None, help="Contact id (SC000123); random if empty."),
    mode: str = typer.Option("auto", help="auto, llm or template."),
    variant: str = typer.Option("rag_policy", help="rag_policy or rag (LLM advisor)."),
    seed: int = typer.Option(0),
) -> None:
    """Run one LangGraph conversation (client <-> advisor -> quality) and print it."""
    from callverse.agents.client.profiles import profile_by_contact_id, sample_profiles
    from callverse.data import loaders
    from callverse.orchestration.graph import run_conversation, save_transcript

    profile = (
        profile_by_contact_id(loaders.contacts(), contact, seed)
        if contact
        else sample_profiles(loaders.contacts(), 1, seed)[0]
    )
    stage(f"Conversation {profile.contact_id} ({profile.intent}, {profile.persona} customer)")
    state = run_conversation(profile, mode, seed, variant=variant)
    for event in state["events"]:
        if event["node"] in ("client", "advisor"):
            say(f"  {event['node'].upper():8} {event.get('text', '')}")
            if event.get("tools"):
                say(f"           tools: {event['tools']}")
        else:
            say(f"  [{event['node']}] {event['summary']}")
    say(f"Reference outcome: {state['reference'].get('outcome')}")
    say(f"Scorecard: {state['scorecard']['scores']} correct={state['kpis']['correct']}")
    say(f"Saved to {save_transcript(state)}")


@app.command()
def agents(
    n: int = typer.Option(20, help="Conversations per variant."),
    variants: str = typer.Option("template", help="Comma list: template, rag, rag_policy."),
) -> None:
    """DSO2: conversation batches and BO2 KPIs per advisor variant."""
    from callverse.evaluation.experiments import agents_experiment, merge_tables

    result = agents_experiment(n, tuple(v.strip() for v in variants.split(",")), log=say)
    merge_tables("dso2_agents", result, key="variant")
    stage("BO2 KPIs per advisor variant")
    say(result["summary"].round(3).to_string(index=False))


@app.command("judge-calibrate")
def judge_calibrate(judge: str = typer.Option("rules", help="rules or llm.")) -> None:
    """DSO2: agreement of the judge with human labels (or proxy labels)."""
    from callverse.evaluation.experiments import judge_calibration, merge_tables, save_tables

    result = judge_calibration(judge_mode=judge)
    merge_tables("dso2_judge_calibration", {"agreement": result["agreement"]}, key="judge")
    save_tables(f"dso2_judge_calibration_{judge}", {k: v for k, v in result.items() if k != "agreement"})
    stage("Judge calibration")
    say(result["agreement"].round(3).to_string(index=False))


@app.command("llm-pull")
def llm_pull() -> None:
    """Download the pinned Hugging Face models of the active profile, then pin their commits."""
    os.environ["HF_HUB_OFFLINE"] = "0"
    from huggingface_hub import constants, snapshot_download

    from callverse.llm import get_llm

    constants.HF_HUB_OFFLINE = False  # .env keeps the hub offline for everything else
    llm = get_llm()
    patterns = ["*.json", "*.safetensors", "*.txt", "*.model", "*.jinja", "tokenizer*"]
    for repo in dict.fromkeys(llm.settings.models.values()):
        stage(f"Downloading {repo}")
        say(f"  -> {snapshot_download(repo, allow_patterns=patterns)}")
    llm_pin()


@app.command("llm-pin")
def llm_pin() -> None:
    """Record the commit of every pinned Hugging Face model (reproducibility)."""
    from callverse.config import TRACE_DIR, ensure_dirs
    from callverse.llm import get_llm

    ensure_dirs()
    lock = get_llm().model_digests()
    path = TRACE_DIR / "llm_models.lock.json"
    path.write_text(json.dumps(lock, indent=2), encoding="utf-8")
    say(json.dumps(lock, indent=2))
    say(f"Written to {path}")


# ------------------------------------------------------------------- evaluation
@app.command()
def evaluate(
    seeds: int = typer.Option(10, help="Replications per configuration."),
    conversations: int = typer.Option(40, help="Template conversations for BO2."),
    llm_variants: str = typer.Option("", help="Also run LLM variants, e.g. 'rag_policy,rag' (slow)."),
) -> None:
    """Every experiment (DSO1-DSO4), the component metrics and the BO/DSO scorecard."""
    from callverse.evaluation.experiments import run_all_experiments
    from callverse.evaluation.report import component_metrics, scorecard

    variants = tuple(v.strip() for v in llm_variants.split(",") if v.strip())
    stage("Evaluation suite")
    run_all_experiments(seeds, conversations, variants, log=say)
    from callverse.config import EVALUATION_DIR

    metrics = component_metrics()
    metrics.to_csv(EVALUATION_DIR / "component_metrics.csv", index=False)
    cards = scorecard()
    (EVALUATION_DIR / "scorecard.json").write_text(json.dumps(cards, indent=2), encoding="utf-8")
    stage("BO -> DSO scorecard")
    for card in cards:
        mark = "PASS" if card["passed"] else "CHECK"
        say(f"  [{mark}] {card['bo']}/{card['dso']} {card['objective']}: {card['result']}")


@app.command()
def status() -> None:
    """What is built (data, models, evaluations) and whether the local LLMs can run."""
    from callverse.config import EVALUATION_DIR, FORECAST_DIR, POLICY_DIR, PROCESSED_DIR, database_path
    from callverse.llm import get_llm

    checks = {
        "processed data": (PROCESSED_DIR / "synthetic_contacts.parquet").exists(),
        "SQLite store": database_path().exists(),
        "knowledge base index": (PROCESSED_DIR.parent / "knowledge_base" / "index" / "index.faiss").exists(),
        "forecast backtest": (FORECAST_DIR / "contact_forecast_backtest_predictions.parquet").exists(),
        "PPO routing policy": (POLICY_DIR / "routing_maskable_ppo.zip").exists(),
        "intent classifier": (POLICY_DIR / "intent_classifier.joblib").exists(),
        "evaluation scorecard": (EVALUATION_DIR / "scorecard.json").exists(),
    }
    stage("CallVerse status")
    for name, ok in checks.items():
        say(f"  [{'x' if ok else ' '}] {name}")
    info = get_llm().status()
    gpu = info["gpu"]
    say(f"  LLMs ({info['provider']}, profile {info['profile']}): available={info['available']}")
    say(f"  GPU: {gpu['name']} ({gpu['total_mb']} MB)" if gpu else "  GPU: none visible to PyTorch")
    for role, model in info["roles"].items():
        say(f"    {role:8s} {model['pinned']}  downloaded={model['downloaded']}")
    if info["reason"]:
        say(f"  Note: {info['reason']}")


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1"),
    port: int = typer.Option(8000),
    reload: bool = typer.Option(False),
) -> None:
    """Start the FastAPI backend (REST + WebSocket) for the React control room."""
    import uvicorn

    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    uvicorn.run("callverse.api.app:app", host=host, port=port, reload=reload)


@app.command("all")
def run_all(
    quick: bool = typer.Option(False, help="Fast path: no notebooks, fast forecast, 50k PPO steps, 5 seeds."),
    skip_data: bool = typer.Option(False, help="Use the processed data already on disk."),
) -> None:
    """End-to-end pipeline: data -> forecast -> workforce agent -> evaluation."""
    started = time.perf_counter()
    if not skip_data:
        data(notebooks=not quick, database=True, knowledge_base=not quick)
    else:
        validate()
    forecast(fast=quick)
    train_rl(timesteps=50_000 if quick else None)
    fidelity()
    evaluate(seeds=5 if quick else 10, conversations=20 if quick else 40, llm_variants="")
    stage(f"Pipeline finished in {(time.perf_counter() - started) / 60:.1f} min")
    say("Next: `callverse serve` and `npm run dev` in frontend/ (see docs/RUN_GUIDE.md).")


if __name__ == "__main__":
    app()
