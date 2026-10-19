"""Twin fidelity check (DSO4): does the virtual center behave like the logs?

A what-if result is only credible if the twin reproduces what the history shows.
Four checks, each with a pass/fail rule:

1. Queueing theory: with constant arrivals and exponential service (no
   abandonment), simulated waits must match the Erlang C formula (the engine
   is correct).
2. Volume: simulated contacts per day vs the historical daily contacts
   (two-sample Kolmogorov-Smirnov test on the same days, scaled).
3. Time of day: share of contacts per hour, simulated vs historical profile.
4. Handle time: simulated handle times vs the ticket logs (KS test).

Honest limit: the "historical logs" are themselves synthetic (no real call-center
data), so checks 2-4 prove the twin is consistent with its inputs; check 1 proves
the engine is correct. With real logs, the same code becomes a real calibration.
"""

from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from callverse.config import load_yaml
from callverse.data import loaders
from callverse.simulation import (
    SECONDS_PER_DAY,
    SECONDS_PER_HOUR,
    CallCenterEngine,
    Contact,
    FifoRouter,
    duty_from_counts,
    erlang_c_mean_wait,
    erlang_c_service_level,
    erlang_c_wait_probability,
    load_twin_settings,
    make_contacts,
    uniform_agents,
)


def erlang_check(replications: int = 5) -> pd.DataFrame:
    """Simulated M/M/c waits vs the Erlang C formula (engine correctness)."""
    raw = load_yaml("simulation")["validation"]["erlang_check"]
    settings = load_twin_settings()
    rate, service, agents, hours = (
        raw["arrival_rate_per_hour"],
        raw["mean_service_seconds"],
        raw["agents"],
        raw["hours"],
    )
    threshold = settings.sim.service_level_threshold_seconds
    rows = []
    for replication in range(replications):
        rng = np.random.default_rng(1000 + replication)
        arrivals = np.cumsum(rng.exponential(3600 / rate, int(rate * hours * 1.2)))
        arrivals = arrivals[arrivals < (hours - 2) * 3600]
        contacts = [
            Contact(i, float(t), "check", float(s), True, None)
            for i, (t, s) in enumerate(zip(arrivals, rng.exponential(service, len(arrivals))))
        ]
        engine = CallCenterEngine(
            contacts,
            uniform_agents(agents, ["check"]),
            duty_from_counts(np.full(hours, agents)),
            FifoRouter(),
            trace_interval=None,
        )
        records = engine.run()
        steady = records[records["arrival"] > 10 * 3600]
        rows.append(
            {
                "wait_probability": float((steady["wait"] > 1e-9).mean()),
                "mean_wait_seconds": float(steady["wait"].mean()),
                "service_level": float((steady["wait"] <= threshold).mean()),
            }
        )
    sims = pd.DataFrame(rows)
    load = rate * service / 3600
    theory = {
        "wait_probability": erlang_c_wait_probability(agents, load),
        "mean_wait_seconds": erlang_c_mean_wait(agents, rate, service),
        "service_level": erlang_c_service_level(agents, rate, service, threshold),
    }
    out = []
    for kpi, expected in theory.items():
        values = sims[kpi]
        half = stats.t.ppf(0.975, len(values) - 1) * values.std(ddof=1) / np.sqrt(len(values))
        out.append(
            {
                "check": "erlang_c",
                "metric": kpi,
                "simulated": values.mean(),
                "expected": expected,
                "ci_low": values.mean() - half,
                "ci_high": values.mean() + half,
                "relative_error_percent": abs(values.mean() - expected) / expected * 100,
                "passed": abs(values.mean() - expected) / expected < 0.05,
            }
        )
    return pd.DataFrame(out)


def fidelity_report(week_start: str = "2018-05-07", weeks: int = 4, seed: int = 0) -> dict[str, Any]:
    """Volume, time-of-day and handle-time fidelity on a historical period."""
    settings = load_twin_settings()
    alpha = float(load_yaml("simulation")["fidelity"]["ks_alpha"])
    daily = loaders.daily_contacts_by_group()
    shares = loaders.hour_shares()
    days = pd.date_range(week_start, periods=7 * weeks)
    contacts = make_contacts(daily, days, settings, shares, np.random.default_rng(seed))
    arrivals = np.array([c.arrival for c in contacts])

    simulated_daily = np.bincount((arrivals // SECONDS_PER_DAY).astype(int), minlength=len(days))
    historical_daily = (
        daily[daily["date"].isin(days)]
        .groupby("date")["contacts"]
        .sum()
        .reindex(days, fill_value=0)
        .to_numpy()
        * settings.sim.scale_factor
    )
    volume = stats.ks_2samp(simulated_daily, historical_daily)

    simulated_hours = np.bincount((arrivals % SECONDS_PER_DAY // SECONDS_PER_HOUR).astype(int), minlength=24)
    simulated_profile = simulated_hours / simulated_hours.sum()
    profile_gap = float(np.abs(simulated_profile - shares).sum() / 2)  # total variation distance

    tickets = loaders.tickets()
    historical_aht = tickets["handle_seconds"].to_numpy(dtype=float)
    simulated_aht = np.array([c.service_seconds for c in contacts])
    sample = int(load_yaml("simulation")["fidelity"]["sample_size"])
    rng = np.random.default_rng(seed)
    aht = stats.ks_2samp(
        rng.choice(simulated_aht, min(sample, len(simulated_aht)), replace=False),
        rng.choice(historical_aht, min(sample, len(historical_aht)), replace=False),
    )

    checks = pd.DataFrame(
        [
            {
                "check": "daily_volume",
                "metric": "KS p-value (simulated vs historical contacts/day)",
                "value": float(volume.pvalue),
                "statistic": float(volume.statistic),
                "passed": bool(volume.pvalue > alpha),
                "detail": f"mean {simulated_daily.mean():.0f} vs {historical_daily.mean():.0f} per day",
            },
            {
                "check": "hour_profile",
                "metric": "Total variation distance of the hourly profile",
                "value": profile_gap,
                "statistic": profile_gap,
                "passed": bool(profile_gap < 0.05),
                "detail": "0 = identical, 1 = disjoint; pass below 0.05",
            },
            {
                "check": "handle_time",
                "metric": "KS p-value (simulated vs ticket handle times)",
                "value": float(aht.pvalue),
                "statistic": float(aht.statistic),
                "passed": bool(aht.pvalue > alpha),
                "detail": f"mean {simulated_aht.mean():.0f}s vs {historical_aht.mean():.0f}s",
            },
        ]
    )
    erlang = erlang_check()
    hourly = pd.DataFrame(
        {"hour": range(24), "simulated_share": simulated_profile, "historical_share": shares}
    )
    daily_frame = pd.DataFrame({"date": days, "simulated": simulated_daily, "historical": historical_daily})
    return {
        "checks": checks,
        "erlang": erlang,
        "hourly_profile": hourly,
        "daily": daily_frame,
        "all_passed": bool(checks["passed"].all() and erlang["passed"].all()),
    }
