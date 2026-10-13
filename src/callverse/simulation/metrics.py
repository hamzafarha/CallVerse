"""Simulation runtime statistics, queue lengths, and SLA collectors."""

import numpy as np
import pandas as pd
from scipy import stats

from callverse.simulation.customers import SECONDS_PER_HOUR


def contact_kpis(
    records: pd.DataFrame,
    staffing: np.ndarray,
    threshold_seconds: float,
    evaluation_end: float | None = None,
) -> dict[str, float]:
    """Key performance indicators of one simulation run.

    Only contacts arriving before ``evaluation_end`` (seconds) are scored; the
    remaining time lets the queue drain. Definitions:

    - service level: live contacts answered within the threshold / live offered
    - abandon rate: live contacts that hung up / live offered
    - ASA: average wait of answered live contacts
    - backlog wait: average wait (hours) of contacts that arrived while closed
    - occupancy: handled seconds / staffed agent-seconds, over the whole run
    """
    scored = records
    if evaluation_end is not None:
        scored = records[records["arrival"] < evaluation_end]
    live = scored[scored["is_live"]]
    backlog = scored[~scored["is_live"]]
    answered_live = live[live["start"].notna()]
    unfinished = scored["start"].isna() & ~scored["abandoned"]

    staffed_seconds = float(staffing.sum()) * SECONDS_PER_HOUR
    started = records["start"].notna()
    handled_seconds = float(records.loc[started, "service_seconds"].sum())
    answered_in_time = (answered_live["wait"] <= threshold_seconds).sum()
    return {
        "offered": float(len(scored)),
        "live_offered": float(len(live)),
        "service_level": float(answered_in_time / len(live)) if len(live) else np.nan,
        "abandon_rate": float(live["abandoned"].mean()) if len(live) else np.nan,
        "asa_seconds": float(answered_live["wait"].mean())
        if len(answered_live)
        else np.nan,
        "backlog_wait_hours": float(backlog["wait"].mean() / SECONDS_PER_HOUR)
        if backlog["start"].notna().any()
        else np.nan,
        "unfinished": float(unfinished.sum()),
        "occupancy": handled_seconds / staffed_seconds if staffed_seconds else np.nan,
        "agent_hours": float(staffing.sum()),
    }


def summarize_replications(
    runs: pd.DataFrame, confidence_level: float, group_columns: list[str]
) -> pd.DataFrame:
    """Mean and confidence interval of every KPI across replications.

    ``runs`` has one row per replication (and per group in ``group_columns``),
    with one column per KPI. Intervals use the Student t distribution.
    """
    kpi_columns = [
        column
        for column in runs.columns
        if column not in group_columns + ["replication"]
    ]
    rows = []
    for keys, group in runs.groupby(group_columns):
        keys = keys if isinstance(keys, tuple) else (keys,)
        count = len(group)
        t_value = (
            stats.t.ppf((1 + confidence_level) / 2, count - 1) if count > 1 else np.nan
        )
        for kpi in kpi_columns:
            values = group[kpi].astype(float)
            half_width = (
                t_value * values.std(ddof=1) / np.sqrt(count) if count > 1 else np.nan
            )
            row = dict(zip(group_columns, keys))
            row.update(
                {
                    "kpi": kpi,
                    "mean": values.mean(),
                    "ci_low": values.mean() - half_width,
                    "ci_high": values.mean() + half_width,
                    "replications": count,
                }
            )
            rows.append(row)
    return pd.DataFrame(rows)
