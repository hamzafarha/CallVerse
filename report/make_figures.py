"""Draw every chart of the technical report from the project's result files (artifacts/), as vector PDFs.

Run from the project root:  python report/make_figures.py
Colours: the validated categorical palette of the app (frontend/shared/src/styles/tokens.css, light mode),
always in the same order; text stays in neutral ink; one axis per chart.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
EVAL = ROOT / "artifacts" / "evaluations"
OUT = Path(__file__).resolve().parent / "figures"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]  # series-1..4 of the app
NEUTRAL = "#9aa3b2"
INK, MUTED, GRID = "#1f2430", "#5b6475", "#e3e6ec"

plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.size": 8.5,
        "axes.titlesize": 9,
        "axes.labelsize": 8.5,
        "axes.edgecolor": GRID,
        "axes.labelcolor": MUTED,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "text.color": INK,
        "axes.grid": True,
        "grid.color": GRID,
        "grid.linewidth": 0.6,
        "axes.axisbelow": True,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "legend.frameon": False,
        "pdf.fonttype": 42,
    }
)


def save(fig: plt.Figure, name: str) -> None:
    fig.savefig(OUT / f"{name}.pdf", bbox_inches="tight")
    if preview := os.environ.get("FIGURE_PREVIEW_DIR"):  # PNG copies, to look at the charts quickly
        fig.savefig(Path(preview) / f"{name}.png", bbox_inches="tight", dpi=110)
    plt.close(fig)
    print("  figures/" + name + ".pdf")


def forecast() -> None:
    """DSO4: wMAPE of the 5 models on the total (rolling backtest, 46 origins)."""
    m = pd.read_csv(ROOT / "artifacts" / "forecasts" / "contact_forecast_backtest_metrics.csv")
    total = m[m.intent_group == "total"].sort_values("wMAPE_percent", ascending=False)
    names = {
        "lightgbm": "LightGBM (main)",
        "sarima": "SARIMA (backup)",
        "seasonal_naive": "Same day last week (baseline)",
        "weekday_mean_4w": "4-week weekday mean",
        "prophet": "Prophet",
    }
    fig, ax = plt.subplots(figsize=(6.3, 2.0))
    colors = [SERIES[0] if model == "lightgbm" else NEUTRAL for model in total.model]
    bars = ax.barh([names[x] for x in total.model], total.wMAPE_percent, color=colors, height=0.6)
    ax.bar_label(bars, labels=[f"{v:.1f}%" for v in total.wMAPE_percent], padding=3, fontsize=8, color=INK)
    ax.set_xlabel("wMAPE on daily total contacts, 7-day horizon (%, lower is better)")
    ax.grid(axis="y", visible=False)
    ax.set_xlim(0, total.wMAPE_percent.max() * 1.15)
    save(fig, "forecast_wmape")


def preparedness() -> None:
    """BO4: understaffed hours per peak week, unprepared vs prepared plan (10 seeds, 95% CI)."""
    s = pd.read_csv(EVAL / "bo4_preparedness_summary.csv")
    s = s[s.kpi == "understaffed_hours"]
    order = ["promo_spike", "delivery_delays", "staff_shortage", "black_friday_aftermath_2017"]
    labels = [
        "Promo spike",
        "Delivery delays",
        "Staff shortage\n(20% absent)",
        "Black Friday\naftermath 2017",
    ]
    fig, ax = plt.subplots(figsize=(6.3, 2.4))
    x, width = np.arange(len(order)), 0.36
    for i, (option, color, name) in enumerate(
        [
            ("unprepared", SERIES[1], "Unprepared plan (normal forecast)"),
            ("prepared", SERIES[0], "Prepared plan (tested in the twin)"),
        ]
    ):
        rows = s[s.option == option].set_index("scenario").loc[order]
        err = [rows["mean"] - rows.ci_low, rows.ci_high - rows["mean"]]
        bars = ax.bar(
            x + (i - 0.5) * width,
            rows["mean"],
            width * 0.92,
            color=color,
            label=name,
            yerr=err,
            ecolor=INK,
            error_kw={"elinewidth": 0.7, "capsize": 2},
        )
        ax.bar_label(bars, labels=[f"{v:.0f}" for v in rows["mean"]], padding=2, fontsize=7.5, color=INK)
    ax.set_xticks(x, labels)
    ax.set_ylabel("Understaffed hours / week")
    ax.grid(axis="x", visible=False)
    ax.legend(loc="upper left", fontsize=7.5)
    ax.set_ylim(0, s["ci_high"].max() * 1.18)
    save(fig, "bo4_understaffed")


def routing() -> None:
    """DSO1: change vs FIFO (%, 95% CI) of the two routers, on stressed days and in peak weeks."""
    stressed = pd.read_csv(EVAL / "routing_comparison.csv")
    peak = pd.read_csv(EVAL / "dso1_routing_vs_fifo.csv")
    kpis = [
        ("mean_wait", "Mean wait (all live customers)"),
        ("abandon_rate", "Abandonment"),
        ("p90", "90th-percentile wait"),
    ]
    contexts = [
        ("stressed", "Unseen stressed days"),
        ("promo_spike", "Peak week: promo spike"),
        ("delivery_delays", "Peak week: delivery delays"),
        ("staff_shortage", "Peak week: staff shortage"),
    ]
    routers = [
        ("skill_score", "Tuned skill score (backup)", SERIES[2], "o"),
        ("ppo", "MaskablePPO (main idea)", SERIES[0], "D"),
    ]
    fig, axes = plt.subplots(1, 3, figsize=(6.6, 2.5), sharey=True)
    for ax, (kpi, title) in zip(axes, kpis):
        for r, (router, name, color, marker) in enumerate(routers):
            for c, (context, _) in enumerate(contexts):
                if context == "stressed":
                    key = {"mean_wait": "mean_wait_all_live_seconds", "abandon_rate": "abandon_rate"}.get(kpi)
                    if key is None:
                        continue  # p90 not measured in the stressed-day study
                    row = stressed[(stressed.router == router) & (stressed.kpi == key)].iloc[0]
                    base = row.baseline_mean
                    mid, lo, hi = (
                        100 * row.diff_vs_baseline / base,
                        100 * row.ci_low / base,
                        100 * row.ci_high / base,
                    )
                else:
                    key = {
                        "mean_wait": "mean_wait_seconds",
                        "abandon_rate": "abandon_rate",
                        "p90": "p90_wait_seconds",
                    }[kpi]
                    row = peak[(peak.router == router) & (peak.kpi == key) & (peak.scenario == context)].iloc[
                        0
                    ]
                    base = row.baseline_mean
                    mid, lo, hi = (
                        100 * row.difference / base,
                        100 * row.ci_low / base,
                        100 * row.ci_high / base,
                    )
                y = c + (0.16 if r == 0 else -0.16)
                significant = lo > 0 or hi < 0
                ax.errorbar(
                    mid,
                    y,
                    xerr=[[mid - lo], [hi - mid]],
                    fmt=marker,
                    color=color,
                    ms=4.5,
                    elinewidth=1,
                    mfc=color if significant else "white",
                    mec=color,
                    capsize=0,
                    label=name if (c == 1 and kpi == "abandon_rate") else None,
                )
        ax.axvline(0, color=MUTED, lw=0.8)
        ax.set_title(title, color=INK)
        ax.grid(axis="y", visible=False)
        ax.set_xlabel("change vs FIFO (%)")
    axes[0].set_yticks(range(len(contexts)), [label for _, label in contexts])
    axes[0].invert_yaxis()
    handles, names = axes[1].get_legend_handles_labels()
    fig.legend(handles, names, loc="lower center", ncol=2, bbox_to_anchor=(0.55, -0.2), fontsize=7.5)
    fig.text(0.99, -0.24, "hollow = not significant (95% CI includes 0)", ha="right", fontsize=7, color=MUTED)
    save(fig, "dso1_routing")


def retrieval() -> None:
    """DSO2: retrieval on 255 Bitext questions, keyword baseline vs bge-m3 + FAISS."""
    r = pd.read_csv(EVAL / "dso2_rag_retrieval.csv").set_index("retriever")
    metrics = [("context_recall_at_1", "Recall@1"), ("context_recall_at_4", "Recall@4"), ("mrr", "MRR")]
    fig, ax = plt.subplots(figsize=(4.6, 2.1))
    x, width = np.arange(len(metrics)), 0.36
    for i, (name, color, label) in enumerate(
        [
            ("keyword baseline (TF-IDF)", SERIES[1], "Keyword search, TF-IDF (baseline)"),
            ("bge-m3 + FAISS", SERIES[0], "bge-m3 + FAISS (main)"),
        ]
    ):
        values = [r.loc[name, m] for m, _ in metrics]
        bars = ax.bar(x + (i - 0.5) * width, values, width * 0.92, color=color, label=label)
        ax.bar_label(bars, labels=[f"{v:.2f}" for v in values], padding=2, fontsize=7.5, color=INK)
    ax.set_xticks(x, [label for _, label in metrics])
    ax.set_ylim(0, 1.08)
    ax.grid(axis="x", visible=False)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.12), fontsize=7, ncol=2)
    save(fig, "dso2_retrieval")


def planners() -> None:
    """DSO3: weekly labour cost of the 4 planners in a normal week (service level in the labels)."""
    s = pd.read_csv(EVAL / "dso3_scheduling_summary.csv")
    s = s[s.scenario == "baseline"].pivot(index="plan", columns="kpi", values="mean")
    order = [
        ("fixed", "Fixed, sized for the peak (baseline)"),
        ("rules_erlang", "Erlang C + templates (backup)"),
        ("fixed_tuned", "Fixed, tuned by hand (sensitivity)"),
        ("cpsat", "CP-SAT (main)"),
    ]
    fig, ax = plt.subplots(figsize=(6.3, 1.9))
    costs = [s.loc[p, "labour_cost_eur"] for p, _ in order]
    colors = [SERIES[0] if p == "cpsat" else NEUTRAL for p, _ in order]
    bars = ax.barh([label for _, label in order], costs, color=colors, height=0.6)
    labels = [
        f"€{s.loc[p, 'labour_cost_eur']:,.0f} · {100 * s.loc[p, 'service_level']:.1f}% answered < 20 s"
        for p, _ in order
    ]
    ax.bar_label(bars, labels=labels, padding=3, fontsize=7.5, color=INK)
    ax.invert_yaxis()
    ax.set_xlim(0, max(costs) * 1.75)
    ax.set_xlabel("Labour cost of a normal week (€), FIFO routing, 10 seeds")
    ax.grid(axis="y", visible=False)
    save(fig, "dso3_planners")


def monitoring() -> dict:
    """Monitoring (live + evaluation traces): latency per model, and routing accuracy by confidence."""
    os.environ.setdefault("CALLVERSE_LLM_MODE", "off")
    from callverse.evaluation.monitoring import monitoring_report

    report = monitoring_report(None, "all")
    models = pd.DataFrame(report["llm"]["by_model"])
    models = models[(models.calls >= 10) & models.p50_ms.notna()].copy()
    models["label"] = models.apply(
        lambda r: f"{r.agent} · {str(r.model).split('/')[-1].replace(':free', '')}", axis=1
    )
    models = models.sort_values("p50_ms")
    fig, ax = plt.subplots(figsize=(6.3, 2.7))
    y = np.arange(len(models))
    colors = [SERIES[0] if p == "openrouter" else SERIES[1] for p in models.provider]
    ax.hlines(y, models.p50_ms / 1000, models.p95_ms / 1000, color=GRID, lw=3)
    ax.scatter(models.p50_ms / 1000, y, color=colors, s=26, zorder=3)
    ax.scatter(models.p95_ms / 1000, y, color=colors, s=26, marker="|", zorder=3)
    ax.set_yticks(y, models.label)
    ax.set_xlabel("Seconds per LLM call: dot = median (p50), bar end = p95")
    ax.grid(axis="y", visible=False)
    from matplotlib.lines import Line2D

    ax.legend(
        handles=[
            Line2D([], [], marker="o", ls="", color=SERIES[0], label="OpenRouter (hosted, free tier)"),
            Line2D([], [], marker="o", ls="", color=SERIES[1], label="Local GPU (4 GB laptop)"),
        ],
        loc="lower right",
        fontsize=7.5,
    )
    save(fig, "llm_latency")

    bins = pd.DataFrame(report["routing"]["confidence"])
    fig, ax = plt.subplots(figsize=(4.6, 1.9))
    labels = [f"{a:.1f}–{b:.1f}" for a, b in zip(bins["from"], bins["to"])]
    bars = ax.bar(labels, 100 * bins.accuracy, color=SERIES[0], width=0.6)
    ax.bar_label(
        bars,
        labels=[f"{100 * a:.0f}%\n(n={n})" for a, n in zip(bins.accuracy, bins.chats)],
        padding=2,
        fontsize=7,
        color=INK,
    )
    ax.set_ylim(0, 125)
    ax.set_xlabel("Confidence of the Workforce agent's intent prediction")
    ax.set_ylabel("Right problem (%)")
    ax.grid(axis="x", visible=False)
    save(fig, "routing_confidence")
    return report


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    os.chdir(ROOT)
    print("Writing:")
    for draw in (forecast, preparedness, routing, retrieval, planners):
        draw()
    report = monitoring()
    keep = {k: report[k] for k in ("headline", "business", "judge_vs_customer", "grounding")}
    keep["tools_callers"] = report["tools"]["callers"]
    (OUT / "monitoring_numbers.json").write_text(json.dumps(keep, indent=2, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
