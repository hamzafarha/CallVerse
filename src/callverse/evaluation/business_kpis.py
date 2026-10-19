"""KPI engine: measures every simulated run against the four business objectives.

    BO1 Reduce customer wait     -> ASA, abandon rate, service level (answered < 20 s)
    BO2 Resolve, raise CSAT      -> FCR, CSAT, compliance, correct answers
    BO3 Cut cost, keep service   -> cost per contact, labour/overtime cost, occupancy
    BO4 Prepare for peaks        -> understaffed hours, money saved by testing first,
                                    time needed to decide

Every KPI of a simulated configuration is reported as mean and 95% confidence
interval over seeds (Student t), so a difference is only claimed when the
intervals say so.
"""

from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

BO_KPIS: dict[str, dict[str, Any]] = {
    "BO1": {
        "title": "Reduce customer waiting time",
        "dso": "DSO1",
        "kpis": {
            "mean_wait_seconds": "lower",
            "abandon_rate": "lower",
            "service_level": "higher",
            "asa_seconds": "lower",
        },
    },
    "BO2": {
        "title": "Solve problems correctly, raise satisfaction",
        "dso": "DSO2",
        "kpis": {
            "fcr_rate": "higher",
            "csat_mean": "higher",
            "compliance_rate": "higher",
            "correct_answer_rate": "higher",
        },
    },
    "BO3": {
        "title": "Cut running costs without hurting service",
        "dso": "DSO3",
        "kpis": {
            "cost_per_contact_eur": "lower",
            "labour_cost_eur": "lower",
            "overtime_hours": "lower",
            "occupancy": "higher",
        },
    },
    "BO4": {
        "title": "Prepare for busy periods by testing first",
        "dso": "DSO4",
        "kpis": {
            "understaffed_hours": "lower",
            "money_saved_by_testing_eur": "higher",
            "decision_time_seconds": "lower",
        },
    },
}

KPI_LABELS = {
    "mean_wait_seconds": "Average wait, all live customers (s)",
    "asa_seconds": "Average speed of answer (ASA, s)",
    "abandon_rate": "Abandon rate",
    "service_level": "Answered within 20 s",
    "p90_wait_seconds": "90th percentile wait (s)",
    "aht_seconds": "Average handle time (s)",
    "occupancy": "Occupancy",
    "labour_cost_eur": "Labour cost (EUR)",
    "overtime_hours": "Overtime hours",
    "overtime_cost_eur": "Overtime cost (EUR)",
    "cost_per_contact_eur": "Cost per contact (EUR)",
    "total_cost_eur": "Labour + lost-customer cost (EUR)",
    "understaffed_hours": "Understaffed hours",
    "fcr_rate": "First-contact resolution",
    "csat_mean": "CSAT (1-5)",
    "compliance_rate": "Policy compliance",
    "correct_answer_rate": "Correct answers",
}


def mean_ci(values: pd.Series, confidence: float = 0.95) -> dict[str, float]:
    """Mean and t-based confidence interval of a series of replications."""
    values = pd.to_numeric(values, errors="coerce").dropna()
    n = len(values)
    mean = float(values.mean()) if n else float("nan")
    if n < 2:
        return {"mean": mean, "ci_low": mean, "ci_high": mean, "n": n}
    half = stats.t.ppf((1 + confidence) / 2, n - 1) * values.std(ddof=1) / np.sqrt(n)
    return {"mean": mean, "ci_low": mean - half, "ci_high": mean + half, "n": n}


def summarize_runs(runs: pd.DataFrame, group_columns: list[str], kpis: list[str]) -> pd.DataFrame:
    """Mean +/- 95% CI of each KPI for each configuration (long table)."""
    rows = []
    for keys, group in runs.groupby(group_columns, sort=False):
        keys = keys if isinstance(keys, tuple) else (keys,)
        for kpi in kpis:
            if kpi in group:
                rows.append(
                    {
                        **dict(zip(group_columns, keys)),
                        "kpi": kpi,
                        "label": KPI_LABELS.get(kpi, kpi),
                        **mean_ci(group[kpi]),
                    }
                )
    return pd.DataFrame(rows)


def paired_difference(
    runs: pd.DataFrame, by: str, baseline: str, kpis: list[str], pair_on: list[str]
) -> pd.DataFrame:
    """Difference of each option vs a baseline, paired on the same seeds (95% CI)."""
    base = runs[runs[by] == baseline].set_index(pair_on)
    rows = []
    for option in runs[by].unique():
        if option == baseline:
            continue
        current = runs[runs[by] == option].set_index(pair_on)
        for kpi in kpis:
            diff = (current[kpi] - base[kpi]).dropna()
            stats_row = mean_ci(diff)
            base_mean = float(base[kpi].mean())
            rows.append(
                {
                    by: option,
                    "baseline": baseline,
                    "kpi": kpi,
                    "label": KPI_LABELS.get(kpi, kpi),
                    "option_mean": float(current[kpi].mean()),
                    "baseline_mean": base_mean,
                    "difference": stats_row["mean"],
                    "ci_low": stats_row["ci_low"],
                    "ci_high": stats_row["ci_high"],
                    "relative_percent": stats_row["mean"] / base_mean * 100 if base_mean else np.nan,
                    "significant": bool(stats_row["ci_low"] > 0 or stats_row["ci_high"] < 0),
                }
            )
    return pd.DataFrame(rows)


def format_mean_ci(row: pd.Series, digits: int = 3) -> str:
    """'mean [low, high]' for tables."""
    return f"{row['mean']:.{digits}g} [{row['ci_low']:.{digits}g}, {row['ci_high']:.{digits}g}]"
