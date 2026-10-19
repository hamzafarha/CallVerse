"""Train the routing agent (MaskablePPO) and compare it with the baselines.

DSO1 rule: every idea is compared with "first come, first served with skill
matching" on days the agent never saw (test period), with common random numbers:
for each test day and seed, every router faces exactly the same customers and
the same absences. The gain is reported with a paired 95% confidence interval.
"""

import json
from collections.abc import Callable
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from callverse.agents.workforce.gym_wrapper import RoutingEnv
from callverse.agents.workforce.routing import (
    PPO_MODEL_FILE,
    make_router,
    routing_settings,
)
from callverse.config import EVALUATION_DIR, POLICY_DIR, ensure_dirs
from callverse.data import loaders
from callverse.simulation import (
    CallCenterEngine,
    TwinSettings,
    apply_absence,
    duty_from_counts,
    engine_kpis,
    hourly_requirements,
    load_twin_settings,
    make_agent_pool,
    make_contacts,
    workload_shares,
)
from callverse.tracking import log_dataframe, mlflow_run


def _period(settings_raw: dict[str, Any], key: str) -> pd.DatetimeIndex:
    period = settings_raw[key]
    return pd.date_range(period["start"], period["end"])


def make_env(seed: int, days: pd.DatetimeIndex | None = None) -> RoutingEnv:
    """Training environment configured from ``configs/agents.yaml``."""
    raw = routing_settings()
    return RoutingEnv(
        load_twin_settings(),
        loaders.daily_contacts_by_group(),
        loaders.hour_shares(),
        _period(raw, "train_period") if days is None else days,
        slots=int(raw["queue_slots"]),
        load_range=(raw["load_multiplier"]["low"], raw["load_multiplier"]["high"]),
        absence_range=(raw["absence_rate"]["low"], raw["absence_rate"]["high"]),
        abandon_penalty_seconds=float(raw["abandon_penalty_seconds"]),
        reward_scale_seconds=float(raw["reward_scale_seconds"]),
        backlog_wait_weight=float(raw.get("backlog_wait_weight", 0.1)),
        seed=seed,
        group_surge=tuple(raw.get("group_surge", [1.0, 1.0])),
    )


def simulate_day_with_router(
    router_kind: str,
    day: pd.Timestamp,
    seed: int,
    load: float,
    absence: float,
    settings: TwinSettings,
    daily: pd.DataFrame,
    shares: np.ndarray,
) -> dict[str, float]:
    """KPIs of one stressed test day for one router (common random numbers)."""
    days = pd.DatetimeIndex([day])
    rng = np.random.default_rng(seed)
    plan = hourly_requirements(daily, days, settings, shares)
    contacts = make_contacts(daily, days, settings, shares, rng, {g: load for g in settings.groups})
    n_agents = int(plan.max(initial=1))
    agents = make_agent_pool(n_agents, workload_shares(daily, settings), settings, seed_offset=seed)
    duty = apply_absence(duty_from_counts(plan, n_agents), absence, np.random.default_rng(seed + 1))
    engine = CallCenterEngine(
        contacts, agents, duty, make_router(router_kind, settings.mean_handle), trace_interval=None
    )
    records = engine.run()
    sim = settings.sim
    kpis = engine_kpis(
        engine, records, sim.service_level_threshold_seconds, sim.service_level_target, settings.costs
    )
    live = records[records["is_live"]]
    kpis["mean_wait_all_live_seconds"] = float(
        np.where(
            live["start"].notna(),
            live["wait"],
            np.minimum(live["abandon_at"].fillna(engine.end_time), engine.end_time) - live["arrival"],
        ).mean()
    )
    return kpis


def evaluate_routers(
    routers: list[str],
    n_days: int = 20,
    seeds_per_day: int = 2,
    load: float = 1.6,
    absence: float = 0.15,
    log: Callable[[str], None] | None = None,
) -> pd.DataFrame:
    """Every router on the same stressed test days (one row per router, day, seed)."""
    raw = routing_settings()
    settings = load_twin_settings()
    daily = loaders.daily_contacts_by_group()
    shares = loaders.hour_shares()
    test_days = _period(raw, "test_period")
    rng = np.random.default_rng(2024)
    picked = sorted(rng.choice(len(test_days), size=min(n_days, len(test_days)), replace=False))
    rows = []
    for number, index in enumerate(picked, start=1):
        day = test_days[index]
        for replica in range(seeds_per_day):
            seed = 10_000 + int(index) * 10 + replica
            for router in routers:
                kpis = simulate_day_with_router(router, day, seed, load, absence, settings, daily, shares)
                rows.append({"router": router, "day": day, "seed": seed, **kpis})
        if log and number % 5 == 0:
            log(f"  evaluated {number}/{len(picked)} test days")
    return pd.DataFrame(rows)


def paired_comparison(
    runs: pd.DataFrame,
    baseline: str = "fifo",
    kpis: tuple[str, ...] = (
        "asa_seconds",
        "mean_wait_all_live_seconds",
        "abandon_rate",
        "service_level",
        "aht_seconds",
    ),
) -> pd.DataFrame:
    """Mean of each router and paired difference vs the baseline with a 95% CI."""
    rows = []
    base = runs[runs["router"] == baseline].set_index(["day", "seed"])
    for router in runs["router"].unique():
        current = runs[runs["router"] == router].set_index(["day", "seed"])
        for kpi in kpis:
            diff = (current[kpi] - base[kpi]).dropna()
            n = len(diff)
            half = stats.t.ppf(0.975, n - 1) * diff.std(ddof=1) / np.sqrt(n) if n > 1 else np.nan
            base_mean = base[kpi].mean()
            rows.append(
                {
                    "router": router,
                    "kpi": kpi,
                    "mean": current[kpi].mean(),
                    "baseline_mean": base_mean,
                    "diff_vs_baseline": diff.mean(),
                    "ci_low": diff.mean() - half,
                    "ci_high": diff.mean() + half,
                    "relative_change_percent": diff.mean() / base_mean * 100 if base_mean else np.nan,
                    "pairs": n,
                }
            )
    return pd.DataFrame(rows)


def train_routing_policy(
    total_timesteps: int | None = None, log: Callable[[str], None] = print
) -> dict[str, Any]:
    """Train MaskablePPO in the twin, save it, evaluate it vs FIFO and skill score."""
    from sb3_contrib import MaskablePPO
    from stable_baselines3.common.monitor import Monitor

    ensure_dirs()
    raw = routing_settings()
    ppo = raw["ppo"]
    steps = int(total_timesteps or ppo["total_timesteps"])
    env = Monitor(make_env(seed=int(ppo["seed"])))
    model = MaskablePPO(
        "MlpPolicy",
        env,
        n_steps=int(ppo["n_steps"]),
        batch_size=int(ppo["batch_size"]),
        learning_rate=float(ppo["learning_rate"]),
        gamma=float(ppo["gamma"]),
        ent_coef=float(ppo["ent_coef"]),
        policy_kwargs={"net_arch": list(ppo["net_arch"])},
        seed=int(ppo["seed"]),
        device="cpu",
        verbose=0,
    )
    log(f"Training MaskablePPO for {steps:,} decisions ...")
    model.learn(total_timesteps=steps)
    model.save(str(POLICY_DIR / PPO_MODEL_FILE))
    episode_rewards = pd.DataFrame(
        {
            "episode": range(1, len(env.get_episode_rewards()) + 1),
            "reward": env.get_episode_rewards(),
            "decisions": env.get_episode_lengths(),
        }
    )
    episode_rewards.to_csv(EVALUATION_DIR / "routing_ppo_training_curve.csv", index=False)

    log("Evaluating fifo / skill_score / ppo on unseen stressed days ...")
    routers = ["fifo", "skill_score", "ppo"]
    runs = evaluate_routers(routers, log=log)
    comparison = paired_comparison(runs)
    runs.to_csv(EVALUATION_DIR / "routing_comparison_runs.csv", index=False)
    comparison.to_csv(EVALUATION_DIR / "routing_comparison.csv", index=False)

    with mlflow_run("routing", "maskable_ppo", {"dso": "DSO1"}) as run:
        run.log_params(
            {
                **{f"ppo_{k}": v for k, v in ppo.items()},
                "queue_slots": raw["queue_slots"],
                "total_timesteps": steps,
                "load_low": raw["load_multiplier"]["low"],
                "load_high": raw["load_multiplier"]["high"],
            }
        )
        for window_end in range(50, len(episode_rewards) + 1, 50):
            window = episode_rewards["reward"].iloc[window_end - 50 : window_end]
            run.log_metric("episode_reward_mean50", float(window.mean()), step=window_end)
        for row in comparison.itertuples():
            run.log_metric(f"{row.router}_{row.kpi}", float(row.mean))
            if row.router != "fifo":
                run.log_metric(f"{row.router}_{row.kpi}_change_pct", float(row.relative_change_percent))
        run.log_artifact(str(POLICY_DIR / PPO_MODEL_FILE), artifact_path="model")
        log_dataframe(run, comparison, "evaluation", "routing_comparison.csv")

    summary = comparison[comparison["kpi"].isin(["asa_seconds", "abandon_rate", "service_level"])]
    log(
        summary[["router", "kpi", "mean", "relative_change_percent", "ci_low", "ci_high"]]
        .round(4)
        .to_string(index=False)
    )
    (POLICY_DIR / "routing_ppo_meta.json").write_text(
        json.dumps({"total_timesteps": steps, "episodes": len(episode_rewards)}, indent=2),
        encoding="utf-8",
    )
    return {"comparison": comparison, "training_curve": episode_rewards}
