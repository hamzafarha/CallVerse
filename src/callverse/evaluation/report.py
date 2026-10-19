"""Component metrics and the BO -> DSO scorecard, from the saved evaluation tables.

The scorecard applies the switch rules of the DSO document: each main idea is
kept only if it beats its baseline (thresholds are starting targets):

- DSO1: >= 10% less waiting time than FIFO in simulation.
- DSO2: wrong answers <= 10%, judge agreement (quadratic kappa) >= 0.4.
- DSO3: lower cost at equal service vs the fixed schedule (labour-rule compliant).
- DSO4: forecast beats "same day last week"; twin passes the fidelity checks.
"""

from typing import Any

import pandas as pd

from callverse.config import EVALUATION_DIR, FORECAST_DIR
from callverse.evaluation.forecast_metrics import forecast_summary


def _read(name: str) -> pd.DataFrame:
    path = EVALUATION_DIR / name
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def component_metrics() -> pd.DataFrame:
    """Is each part good on its own? (component metrics card of the architecture)."""
    rows: list[dict[str, Any]] = []
    forecast = forecast_summary()
    if forecast.get("available"):
        rows += [
            {
                "component": "Forecast",
                "metric": "wMAPE total (rolling backtest)",
                "value": forecast["main_wmape"],
                "baseline": forecast["naive_wmape"],
                "unit": "%",
                "better": "lower",
            },
            {
                "component": "Forecast",
                "metric": "RMSE total (contacts/day)",
                "value": forecast["rmse_total"],
                "baseline": None,
                "unit": "",
                "better": "lower",
            },
        ]
    rag = _read("dso2_rag_retrieval.csv")
    for row in rag.itertuples():
        rows.append(
            {
                "component": "RAG advisor",
                "metric": f"Context recall@4 ({row.retriever})",
                "value": row.context_recall_at_4,
                "baseline": None,
                "unit": "share",
                "better": "higher",
            }
        )
    faith = _read("dso2_rag_faithfulness.csv")
    if not faith.empty:
        key = "variant" if "variant" in faith else "mode"
        for mode, group in faith.groupby(key):
            rows.append(
                {
                    "component": "RAG advisor",
                    "metric": f"Faithfulness ({mode})",
                    "value": group["faithfulness"].mean(),
                    "baseline": None,
                    "unit": "share",
                    "better": "higher",
                }
            )
            rows.append(
                {
                    "component": "RAG advisor",
                    "metric": f"Answer relevance ({mode})",
                    "value": group["answer_relevance"].mean(),
                    "baseline": None,
                    "unit": "cosine",
                    "better": "higher",
                }
            )
    similarity = _read("dso2_rag_answer_similarity.csv")
    if not similarity.empty:
        for variant, group in similarity.groupby("variant"):
            rows.append(
                {
                    "component": "RAG advisor",
                    "metric": f"Similarity to the policy answer ({variant})",
                    "value": group["similarity_to_policy_answer"].mean(),
                    "baseline": None,
                    "unit": "cosine",
                    "better": "higher",
                }
            )
    judge = _read("dso2_judge_calibration_agreement.csv")
    for row in judge.itertuples():
        rows.append(
            {
                "component": "LLM judge",
                "metric": f"Quadratic kappa - {row.criterion} ({getattr(row, 'judge', 'judge')} judge)",
                "value": row.quadratic_kappa,
                "baseline": 0.4,
                "unit": "kappa",
                "better": "higher",
            }
        )
        rows.append(
            {
                "component": "LLM judge",
                "metric": f"Spearman - {row.criterion} ({getattr(row, 'judge', 'judge')} judge)",
                "value": row.spearman,
                "baseline": None,
                "unit": "rho",
                "better": "higher",
            }
        )
    twin = _read("twin_fidelity_checks.csv")
    for row in twin.itertuples():
        rows.append(
            {
                "component": "Twin",
                "metric": row.metric,
                "value": row.value,
                "baseline": 0.05 if "p-value" in row.metric else 0.05,
                "unit": "",
                "better": "higher" if "p-value" in row.metric else "lower",
            }
        )
    erlang = _read("twin_fidelity_erlang.csv")
    for row in erlang.itertuples():
        rows.append(
            {
                "component": "Twin",
                "metric": f"Erlang C check - {row.metric} (error %)",
                "value": row.relative_error_percent,
                "baseline": 5.0,
                "unit": "%",
                "better": "lower",
            }
        )
    return pd.DataFrame(rows)


def _relative(table: pd.DataFrame, **filters: str) -> float | None:
    rows = table
    for column, value in filters.items():
        rows = rows[rows[column] == value]
    return float(rows["relative_percent"].mean()) if len(rows) else None


def scorecard() -> list[dict[str, Any]]:
    """One line per BO/DSO: measured result, baseline, rule, verdict."""
    cards: list[dict[str, Any]] = []

    routing = _read("dso1_routing_vs_fifo.csv")
    best_router, best_gain = None, None
    if not routing.empty:
        for router in routing["router"].unique():
            gain = _relative(routing, router=router, kpi="mean_wait_seconds")
            if gain is not None and (best_gain is None or gain < best_gain):
                best_router, best_gain = router, gain
    ppo_gain = _relative(routing, router="ppo", kpi="mean_wait_seconds") if not routing.empty else None
    ppo_abandon = _relative(routing, router="ppo", kpi="abandon_rate") if not routing.empty else None
    stress = _read("routing_comparison.csv")
    stress_gain = None
    if not stress.empty:
        rows = stress[(stress["router"] == "ppo") & (stress["kpi"] == "asa_seconds")]
        stress_gain = float(rows["relative_change_percent"].iloc[0]) if len(rows) else None
    result = None
    if ppo_gain is not None:
        result = f"PPO mean wait {ppo_gain:+.1f}%, abandonment {ppo_abandon:+.1f}% vs FIFO (3 peak weeks)"
        if stress_gain is not None:
            result += f"; ASA {stress_gain:+.1f}% on stressed test days"
    cards.append(
        {
            "bo": "BO1",
            "dso": "DSO1",
            "objective": "Reduce customer waiting time",
            "main_idea": "RL routing (MaskablePPO)",
            "baseline": "FIFO with skill matching",
            "result": result,
            "rule": ">= 10% less waiting time in the twin's peak weeks",
            "passed": ppo_gain is not None and ppo_gain <= -10,
            "fallback": f"best router in peak weeks: {best_router} ({best_gain:+.1f}% mean wait)"
            if best_router
            else None,
        }
    )

    agents = _read("dso2_agents_summary.csv")
    calibration = _read("dso2_judge_calibration_agreement.csv")
    correct = None
    if not agents.empty:
        llm = agents[agents["variant"] != "template"]
        source = llm if not llm.empty else agents
        correct = float(source["correct_answer_rate"].max())
    kappa = float(calibration["quadratic_kappa"].mean()) if not calibration.empty else None
    cards.append(
        {
            "bo": "BO2",
            "dso": "DSO2",
            "objective": "Solve problems correctly, raise satisfaction",
            "main_idea": "Agentic RAG advisor + LLM judge",
            "baseline": "keyword FAQ search / templates",
            "result": (f"correct answers {correct:.0%}" if correct is not None else "n/a")
            + (f", judge kappa {kappa:.2f}" if kappa is not None else ""),
            "rule": "wrong answers <= 10%, kappa >= 0.4",
            "passed": bool(correct is not None and correct >= 0.9 and (kappa or 0) >= 0.4),
            "fallback": "intent classifier + approved templates (+ checklist reviewer)",
        }
    )

    scheduling = _read("dso3_scheduling_vs_fixed.csv")
    cost = (
        _relative(scheduling, plan="cpsat", kpi="labour_cost_eur", scenario="baseline")
        if not scheduling.empty
        else None
    )
    service_level = None
    if not scheduling.empty:
        rows = scheduling[
            (scheduling["plan"] == "cpsat")
            & (scheduling["kpi"] == "service_level")
            & (scheduling["scenario"] == "baseline")
        ]
        service_level = float(rows["option_mean"].mean()) if len(rows) else None
    from callverse.config import load_yaml

    target = float(load_yaml("simulation")["resources"]["staffing"]["service_level_target"])
    cards.append(
        {
            "bo": "BO3",
            "dso": "DSO3",
            "objective": "Cut costs without hurting service",
            "main_idea": "Forecast + CP-SAT shift planning",
            "baseline": "fixed schedule (peak-sized)",
            "result": None
            if cost is None
            else f"labour cost {cost:+.1f}% vs fixed; service level {service_level:.1%} "
            f"(target {target:.0%})",
            "rule": "cost -5% or better while the service target is still met; labour rules respected",
            "passed": cost is not None and cost <= -5 and (service_level or 0) >= target,
            "fallback": "Erlang C + shift templates + overtime rule",
        }
    )

    forecast = forecast_summary()
    savings = _read("bo4_preparedness_savings.csv")
    fidelity = _read("twin_fidelity_checks.csv")
    fidelity_ok = bool(fidelity["passed"].all()) if not fidelity.empty else False
    saved = float(savings["money_saved_by_testing_eur"].sum()) if not savings.empty else None
    cards.append(
        {
            "bo": "BO4",
            "dso": "DSO4",
            "objective": "Prepare for busy periods by testing first",
            "main_idea": "Intent-level forecast + SimPy digital twin",
            "baseline": "same day last week; Erlang C queue model",
            "result": (
                f"wMAPE {forecast['main_wmape']:.1f}% vs {forecast['naive_wmape']:.1f}% naive "
                f"({forecast['gain_vs_naive_percent']:+.1f}%)"
                if forecast.get("available")
                else "n/a"
            )
            + (f"; twin fidelity {'passed' if fidelity_ok else 'failed'}")
            + (
                f"; EUR {saved:,.0f} net saved over 3 peak weeks by testing first"
                if saved is not None
                else ""
            ),
            "rule": "beat the naive forecast; twin passes fidelity checks",
            "passed": bool(forecast.get("beats_baseline")) and fidelity_ok,
            "fallback": "Prophet/SARIMA + Erlang C queue model",
        }
    )
    return cards


def artifacts_inventory() -> list[dict[str, Any]]:
    """Files produced by the pipeline (for the MLOps page)."""
    rows = []
    for folder in [FORECAST_DIR, EVALUATION_DIR, EVALUATION_DIR.parent / "policies"]:
        if folder.exists():
            for path in sorted(folder.glob("*")):
                if path.is_file() and path.name != ".gitkeep":
                    rows.append(
                        {
                            "folder": folder.name,
                            "file": path.name,
                            "size_kb": round(path.stat().st_size / 1024, 1),
                        }
                    )
    return rows
