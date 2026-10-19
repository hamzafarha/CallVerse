"""Experiment suites: every claim of the project is produced here, with seeds and CIs.

- ``scheduling_experiment`` (DSO3 / BO3): CP-SAT vs rules vs fixed schedules,
  same customers (common random numbers), cost and service per configuration.
- ``routing_experiment`` (DSO1 / BO1): FIFO vs skill score vs PPO inside the
  scenario weeks of the twin.
- ``preparedness_experiment`` (DSO4 / BO4): for each peak scenario, the plan built
  from the normal forecast (unprepared) vs the plan tested in the twin first
  (prepared): understaffed hours, service, labour + lost-customer cost, and the
  time the twin needed to decide.
- ``agents_experiment`` (DSO2 / BO2): conversation batches for the advisor
  variants, plus judge calibration against labels.

Results go to ``artifacts/evaluations/*.csv`` and to MLflow.
"""

import time
from collections.abc import Callable
from typing import Any

import pandas as pd

from callverse.agents.quality.rubric import CRITERIA
from callverse.agents.quality.validation import (
    calibration_table,
    load_human_labels,
    resolution_label,
)
from callverse.agents.workforce.routing import ppo_available
from callverse.config import EVALUATION_DIR, ensure_dirs
from callverse.data import loaders
from callverse.evaluation.business_kpis import mean_ci, paired_difference, summarize_runs
from callverse.tracking import log_dataframe, mlflow_run
from callverse.twin import DigitalTwin, runs_to_frame

SIM_KPIS = [
    "mean_wait_seconds",
    "service_level",
    "abandon_rate",
    "asa_seconds",
    "p90_wait_seconds",
    "aht_seconds",
    "occupancy",
    "labour_cost_eur",
    "overtime_hours",
    "overtime_cost_eur",
    "cost_per_contact_eur",
    "total_cost_eur",
    "understaffed_hours",
    "agent_hours",
    "handled",
]


def scheduling_experiment(
    twin: DigitalTwin,
    seeds: int = 10,
    scenarios: tuple[str, ...] = ("baseline", "promo_spike"),
    plans: tuple[str, ...] = ("fixed", "fixed_tuned", "rules_erlang", "cpsat"),
    log: Callable[[str], None] | None = None,
) -> dict[str, pd.DataFrame]:
    """DSO3: every planner on the same customers (FIFO routing, prepared plans)."""
    runs = []
    for scenario in scenarios:
        for plan in plans:
            runs.append(runs_to_frame(twin.run(scenario, plan, "fifo", seeds, prepared=True)))
            if log:
                log(f"  scheduling: {scenario} / {plan}")
    frame = pd.concat(runs, ignore_index=True)
    summary = summarize_runs(frame, ["scenario", "plan"], SIM_KPIS)
    diffs = pd.concat(
        [
            paired_difference(
                frame[frame["scenario"] == s],
                "plan",
                "fixed",
                [
                    "labour_cost_eur",
                    "cost_per_contact_eur",
                    "service_level",
                    "asa_seconds",
                    "overtime_hours",
                    "understaffed_hours",
                ],
                ["seed"],
            ).assign(scenario=s)
            for s in scenarios
        ],
        ignore_index=True,
    )
    return {"runs": frame, "summary": summary, "vs_fixed": diffs}


def routing_experiment(
    twin: DigitalTwin,
    seeds: int = 10,
    scenarios: tuple[str, ...] = ("promo_spike", "delivery_delays", "staff_shortage"),
    log: Callable[[str], None] | None = None,
) -> dict[str, pd.DataFrame]:
    """DSO1: routers inside the scenario weeks (same plan: the unprepared CP-SAT plan).

    The unprepared plan creates the queues where routing decisions matter.
    """
    routers = ["fifo", "skill_score"] + (["ppo"] if ppo_available() else [])
    runs = []
    for scenario in scenarios:
        for router in routers:
            runs.append(runs_to_frame(twin.run(scenario, "cpsat", router, seeds, prepared=False)))
            if log:
                log(f"  routing: {scenario} / {router}")
    frame = pd.concat(runs, ignore_index=True)
    summary = summarize_runs(frame, ["scenario", "router"], SIM_KPIS)
    diffs = pd.concat(
        [
            paired_difference(
                frame[frame["scenario"] == s],
                "router",
                "fifo",
                [
                    "mean_wait_seconds",
                    "asa_seconds",
                    "abandon_rate",
                    "service_level",
                    "p90_wait_seconds",
                    "aht_seconds",
                ],
                ["seed"],
            ).assign(scenario=s)
            for s in scenarios
        ],
        ignore_index=True,
    )
    return {"runs": frame, "summary": summary, "vs_fifo": diffs}


def preparedness_experiment(
    twin: DigitalTwin,
    seeds: int = 10,
    scenarios: tuple[str, ...] = ("promo_spike", "delivery_delays", "staff_shortage"),
    plan: str = "cpsat",
    log: Callable[[str], None] | None = None,
) -> dict[str, pd.DataFrame]:
    """BO4: unprepared vs prepared plan for each peak scenario."""
    runs, decision_rows = [], []
    for scenario in scenarios:
        for prepared in (False, True):
            started = time.perf_counter()
            frame = runs_to_frame(twin.run(scenario, plan, "fifo", seeds, prepared=prepared))
            runs.append(frame)
            decision_rows.append(
                {
                    "scenario": scenario,
                    "prepared": prepared,
                    "decision_time_seconds": time.perf_counter() - started,
                }
            )
            if log:
                log(f"  preparedness: {scenario} / {'prepared' if prepared else 'unprepared'}")
    frame = pd.concat(runs, ignore_index=True)
    frame["option"] = frame["prepared"].map({True: "prepared", False: "unprepared"})
    summary = summarize_runs(frame, ["scenario", "option"], SIM_KPIS)
    diffs = pd.concat(
        [
            paired_difference(
                frame[frame["scenario"] == s],
                "option",
                "unprepared",
                [
                    "understaffed_hours",
                    "service_level",
                    "abandon_rate",
                    "mean_wait_seconds",
                    "labour_cost_eur",
                    "total_cost_eur",
                ],
                ["seed"],
            ).assign(scenario=s)
            for s in scenarios
        ],
        ignore_index=True,
    )
    rows = []
    for scenario in scenarios:
        part = frame[frame["scenario"] == scenario]
        prepared = part[part["prepared"]].set_index("seed")
        unprepared = part[~part["prepared"]].set_index("seed")
        saved = unprepared["total_cost_eur"] - prepared["total_cost_eur"]
        extra_labour = float((prepared["labour_cost_eur"] - unprepared["labour_cost_eur"]).mean())
        avoided = float(
            (
                (unprepared["abandon_rate"] * unprepared["live_offered"])
                - (prepared["abandon_rate"] * prepared["live_offered"])
            ).mean()
        )
        stats_row = mean_ci(saved)
        rows.append(
            {
                "scenario": scenario,
                "money_saved_by_testing_eur": stats_row["mean"],
                "ci_low": stats_row["ci_low"],
                "ci_high": stats_row["ci_high"],
                "extra_labour_eur": extra_labour,
                "abandonments_avoided": avoided,
                "break_even_abandonment_cost_eur": extra_labour / avoided if avoided > 0 else None,
                "understaffed_hours_avoided": float(
                    (unprepared["understaffed_hours"] - prepared["understaffed_hours"]).mean()
                ),
            }
        )
    savings = pd.DataFrame(rows)
    return {
        "runs": frame,
        "summary": summary,
        "vs_unprepared": diffs,
        "savings": savings,
        "decision_time": pd.DataFrame(decision_rows),
    }


def agents_experiment(
    n: int = 40,
    variants: tuple[str, ...] = ("template",),
    seed: int = 0,
    log: Callable[[str], None] | None = None,
) -> dict[str, pd.DataFrame]:
    """BO2/DSO2: conversation batches per advisor variant (template, rag, rag_policy)."""
    from callverse.orchestration.graph import conversation_kpis, run_batch

    frames, summary_rows = [], []
    for variant in variants:
        mode = "template" if variant == "template" else "llm"
        frame = run_batch(
            n, mode=mode, seed=seed, log=log, variant=None if variant == "template" else variant
        )
        frame["variant"] = variant
        frames.append(frame)
        summary_rows.append({"variant": variant, **conversation_kpis(frame)})
        if log:
            log(f"  agents: {variant} done")
    return {"conversations": pd.concat(frames, ignore_index=True), "summary": pd.DataFrame(summary_rows)}


def judge_calibration(
    conversations: pd.DataFrame | None = None, sample: int = 60, judge_mode: str = "rules", seed: int = 3
) -> dict[str, pd.DataFrame]:
    """Agreement of the judge with labels: human labels if available, else proxy labels.

    Proxy labels = the generator's answer key of the synthetic tickets: resolution
    from the outcome class, satisfaction from the customer's survey score.
    """
    from callverse.agents.quality.reviewer import QualityReviewer
    from callverse.orchestration.runtime import get_runtime

    tickets = loaders.tickets()
    messages = loaders.chat_messages()
    human = load_human_labels()
    labeled_ids = set(human["ticket_id"]) if len(human) else set()
    if len(labeled_ids) >= 20:
        chosen = tickets[tickets["ticket_id"].isin(labeled_ids)]
        source = "human"
    else:
        pool = tickets[tickets["csat_score"].notna()]
        chosen = pool.sample(min(sample, len(pool)), random_state=seed)
        source = "proxy (generator answer key)"
    reviewer = QualityReviewer(
        get_runtime().llm if judge_mode != "rules" else None, "rules" if judge_mode == "rules" else judge_mode
    )
    by_ticket = {
        k: g.sort_values("turn")
        for k, g in messages[messages["ticket_id"].isin(chosen["ticket_id"])].groupby("ticket_id")
    }
    rows = []
    for ticket in chosen.itertuples():
        chat = by_ticket.get(ticket.ticket_id)
        if chat is None:
            continue
        transcript = [{"speaker": r.speaker, "text": r.text} for r in chat.itertuples()]
        sources = [c for c in chat["kb_chunk_id"].dropna()]
        meta = {
            "sources": sources,
            "tools": [{"name": "lookup_order", "ok": True}],
            "outcome": ticket.outcome,
            "handed_to": ticket.handed_to,
        }
        reference = {"outcome": ticket.outcome, "kb_chunk_id": ticket.kb_chunk_id}
        card = reviewer.review(transcript, reference, meta)
        rows.append({"ticket_id": ticket.ticket_id, **card.scores})
    judge = pd.DataFrame(rows)
    if source == "human":
        labels = human.groupby("ticket_id")[CRITERIA].mean().round().reset_index()
    else:
        labels = chosen[["ticket_id", "outcome_class", "csat_score"]].copy()
        labels["resolution"] = labels["outcome_class"].map(resolution_label)
        labels["satisfaction"] = labels["csat_score"].astype(float)
        labels = labels[["ticket_id", "resolution", "satisfaction"]]
    table = calibration_table(judge, labels, source)
    table.insert(0, "judge", "llm" if judge_mode != "rules" else "rules (checklist)")
    return {"judge_scores": judge, "labels": labels, "agreement": table}


def rag_experiment(
    use_embeddings: bool = True, log: Callable[[str], None] | None = None
) -> dict[str, pd.DataFrame]:
    """DSO2 retrieval quality (bge-m3 vs keyword baseline) and answer faithfulness."""
    from callverse.evaluation.advisor_metrics import (
        answer_similarity,
        faithfulness_and_relevance,
        load_saved_conversations,
        retrieval_metrics,
        retrieval_test_set,
    )
    from callverse.orchestration.runtime import get_runtime

    runtime = get_runtime()
    test_set = retrieval_test_set()
    keyword = runtime.keyword_retriever()
    rows = [{"retriever": "keyword baseline (TF-IDF)", **retrieval_metrics(keyword, test_set)}]
    embedder = None
    if use_embeddings:
        try:
            retriever = runtime.retriever()
            if retriever is not keyword:
                rows.append({"retriever": "bge-m3 + FAISS", **retrieval_metrics(retriever, test_set)})
                embedder = retriever.embedder
        except Exception as error:  # model not downloaded: keyword baseline only
            if log:
                log(f"  embedding retriever unavailable ({error}); keyword baseline only")
    retrieval = pd.DataFrame(rows)
    faithfulness = pd.DataFrame()
    similarity = pd.DataFrame()
    conversations = load_saved_conversations()
    labelled = [c for c in conversations if c["_variant"] != "unlabelled"]
    conversations = labelled or conversations
    if embedder is not None and conversations:
        chunk_text = {c.chunk_id: c.text for c in keyword.chunks}
        faithfulness = faithfulness_and_relevance(conversations, embedder, chunk_text)
        similarity = answer_similarity(conversations, embedder)
    if log:
        log(retrieval.round(3).to_string(index=False))
    return {"retrieval": retrieval, "faithfulness": faithfulness, "answer_similarity": similarity}


def save_tables(prefix: str, tables: dict[str, pd.DataFrame]) -> None:
    """Write every table of an experiment to artifacts/evaluations/."""
    ensure_dirs()
    for name, table in tables.items():
        table.to_csv(EVALUATION_DIR / f"{prefix}_{name}.csv", index=False)


def merge_tables(prefix: str, tables: dict[str, pd.DataFrame], key: str) -> None:
    """Like ``save_tables`` but keeps rows of other ``key`` values already saved.

    Used so a slow LLM batch (variants rag, rag_policy, or the LLM judge) adds its
    rows next to the template results instead of replacing them.
    """
    ensure_dirs()
    for name, table in tables.items():
        path = EVALUATION_DIR / f"{prefix}_{name}.csv"
        if path.exists() and key in table:
            old = pd.read_csv(path)
            if key in old:
                table = pd.concat([old[~old[key].isin(table[key].unique())], table], ignore_index=True)
        table.to_csv(path, index=False)


def run_all_experiments(
    seeds: int = 10,
    agent_conversations: int = 40,
    llm_variants: tuple[str, ...] = (),
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Every experiment of the evaluation chapter, logged to MLflow."""
    twin = DigitalTwin()
    log("DSO3 scheduling experiment ...")
    scheduling = scheduling_experiment(twin, seeds, log=log)
    save_tables("dso3_scheduling", scheduling)
    log("DSO1 routing experiment ...")
    routing = routing_experiment(twin, seeds, log=log)
    save_tables("dso1_routing", routing)
    log("BO4 preparedness experiment ...")
    preparedness = preparedness_experiment(twin, seeds, log=log)
    save_tables("bo4_preparedness", preparedness)
    log("DSO2 conversation experiment ...")
    agents = agents_experiment(agent_conversations, ("template", *llm_variants), log=log)
    merge_tables("dso2_agents", agents, key="variant")
    calibration = judge_calibration()
    merge_tables("dso2_judge_calibration", {"agreement": calibration["agreement"]}, key="judge")
    save_tables("dso2_judge_calibration_rules", {k: v for k, v in calibration.items() if k != "agreement"})
    log("DSO2 RAG retrieval and faithfulness ...")
    rag = rag_experiment(log=log)
    save_tables("dso2_rag", rag)
    from callverse.evaluation.twin_metrics import run_fidelity

    log("DSO4 twin fidelity ...")
    run_fidelity()

    with mlflow_run("twin", "evaluation_suite", {"seeds": str(seeds)}) as run:
        run.log_param("seeds", seeds)
        for row in preparedness["savings"].itertuples():
            run.log_metric(f"bo4_money_saved_{row.scenario}", float(row.money_saved_by_testing_eur))
        for row in routing["vs_fifo"].itertuples():
            run.log_metric(f"dso1_{row.scenario}_{row.router}_{row.kpi}_pct", float(row.relative_percent))
        for row in scheduling["vs_fixed"].itertuples():
            run.log_metric(f"dso3_{row.scenario}_{row.plan}_{row.kpi}_pct", float(row.relative_percent))
        for row in agents["summary"].itertuples():
            for kpi in ["fcr_rate", "csat_mean", "compliance_rate", "correct_answer_rate"]:
                run.log_metric(f"dso2_{row.variant}_{kpi}", float(getattr(row, kpi)))
        for name, tables in [
            ("scheduling", scheduling),
            ("routing", routing),
            ("preparedness", preparedness),
        ]:
            log_dataframe(run, tables["summary"], "evaluation", f"{name}_summary.csv")
    return {
        "scheduling": scheduling,
        "routing": routing,
        "preparedness": preparedness,
        "agents": agents,
        "calibration": calibration,
        "rag": rag,
    }
