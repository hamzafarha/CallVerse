"""Backup DSO1 idea: tune the weights of the skill-score formula in the twin.

Random search: draw weight vectors, simulate the same stressed training days
with each (common random numbers), keep the vector with the lowest average wait
of live customers plus an abandonment penalty. Simple, fast, explainable.
"""

import json
from collections.abc import Callable
from typing import Any

import numpy as np
import pandas as pd

from callverse.agents.workforce.routing import SKILL_WEIGHTS_FILE, routing_settings
from callverse.config import POLICY_DIR, ensure_dirs
from callverse.data import loaders
from callverse.simulation import (
    CallCenterEngine,
    SkillScoreRouter,
    apply_absence,
    duty_from_counts,
    hourly_requirements,
    load_twin_settings,
    make_agent_pool,
    make_contacts,
    workload_shares,
)


def _objective(records: pd.DataFrame, end_time: float, abandon_penalty: float) -> float:
    live = records[records["is_live"]]
    waited = np.where(
        live["start"].notna(),
        live["wait"],
        np.minimum(live["abandon_at"].fillna(end_time), end_time) - live["arrival"],
    )
    return float(waited.mean() + abandon_penalty * live["abandoned"].mean())


def optimize_skill_weights(log: Callable[[str], None] = print) -> dict[str, Any]:
    """Random search of the skill-score weights; saves them for ``make_router``."""
    ensure_dirs()
    raw = routing_settings()
    search = raw["skill_score"]
    settings = load_twin_settings()
    daily = loaders.daily_contacts_by_group()
    shares = loaders.hour_shares()
    train_days = pd.date_range(raw["train_period"]["start"], raw["train_period"]["end"])
    rng = np.random.default_rng(11)
    days = [train_days[i] for i in rng.choice(len(train_days), int(search["search_days"]), replace=False)]
    load = float(np.mean([raw["load_multiplier"]["low"], raw["load_multiplier"]["high"]]))
    absence = float(np.mean([raw["absence_rate"]["low"], raw["absence_rate"]["high"]]))
    penalty = float(raw["abandon_penalty_seconds"])

    episodes = []
    for number, day in enumerate(days):
        day_index = pd.DatetimeIndex([day])
        plan = hourly_requirements(daily, day_index, settings, shares)
        episodes.append((day_index, plan, 500 + number))

    def score(weights: dict[str, float]) -> float:
        values = []
        for day_index, plan, seed in episodes:
            contacts = make_contacts(
                daily,
                day_index,
                settings,
                shares,
                np.random.default_rng(seed),
                {g: load for g in settings.groups},
            )
            n = int(plan.max(initial=1))
            agents = make_agent_pool(n, workload_shares(daily, settings), settings, seed_offset=seed)
            duty = apply_absence(duty_from_counts(plan, n), absence, np.random.default_rng(seed + 1))
            engine = CallCenterEngine(
                contacts, agents, duty, SkillScoreRouter(settings.mean_handle, weights), trace_interval=None
            )
            values.append(_objective(engine.run(), engine.end_time, penalty))
        return float(np.mean(values))

    candidates = [dict(search["default_weights"]), {"wait": 1.0, "speed": 0, "short_job": 0, "impatient": 0}]
    for _ in range(int(search["search_iterations"])):
        candidates.append({k: float(rng.uniform(0, 3)) for k in ["wait", "speed", "short_job", "impatient"]})
    results = []
    for number, weights in enumerate(candidates, start=1):
        results.append((score(weights), weights))
        if number % 10 == 0:
            log(f"  skill-score search {number}/{len(candidates)}")
    results.sort(key=lambda item: item[0])
    best_value, best = results[0]
    fifo_like = next(v for v, w in results if w == candidates[1])
    payload = {
        "weights": best,
        "objective": best_value,
        "fifo_like_objective": fifo_like,
        "days": [str(d.date()) for d in days],
        "load": load,
        "absence": absence,
    }
    (POLICY_DIR / SKILL_WEIGHTS_FILE).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    log(f"Best skill-score weights {best} (objective {best_value:.1f} vs wait-only {fifo_like:.1f})")
    return payload
