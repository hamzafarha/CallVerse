"""Builders shared by the RL environment, the schedulers and the digital twin.

They turn daily contact counts (observed or forecast) into what the engine needs:
customers (with personas), Erlang C staffing plans, skilled agent pools, absences.
Every assumption comes from ``configs/simulation.yaml`` and ``configs/agents.yaml``.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from callverse.config import config_path, load_yaml
from callverse.simulation.customers import Contact, generate_contacts
from callverse.simulation.engine import CostModel, build_agent_pool
from callverse.simulation.policy import Agent
from callverse.simulation.resources import hourly_plan_inputs, plan_hourly_staffing
from callverse.simulation.scenarios import SimulationConfig, load_simulation_config
from callverse.simulation.service import LognormalServiceModel


@dataclass(frozen=True)
class TwinSettings:
    """Everything the twin assumes, in one object."""

    sim: SimulationConfig
    costs: CostModel
    specialist_multiplier: float
    weak_multiplier: float
    skills_seed: int
    patience_mix: dict[str, tuple[float, float]]

    @property
    def groups(self) -> list[str]:
        return list(self.sim.service_times)

    @property
    def mean_handle(self) -> dict[str, float]:
        return {g: s.mean_seconds for g, s in self.sim.service_times.items()}

    @property
    def service_model(self) -> LognormalServiceModel:
        return LognormalServiceModel(self.sim.service_times)


def load_twin_settings() -> TwinSettings:
    """Read the simulation, skills, cost and persona assumptions."""
    raw = load_yaml("simulation")
    personas = load_yaml("agents")["client"]["personas"]
    return TwinSettings(
        sim=load_simulation_config(config_path("simulation")),
        costs=CostModel(
            float(raw["costs"]["regular_hourly_eur"]),
            float(raw["costs"]["overtime_multiplier"]),
            float(raw["costs"].get("abandonment_cost_eur", 0.0)),
        ),
        specialist_multiplier=float(raw["skills"]["specialist_multiplier"]),
        weak_multiplier=float(raw["skills"]["weak_multiplier"]),
        skills_seed=int(raw["skills"]["random_seed"]),
        patience_mix={
            name: (float(p["share"]), float(p["patience_multiplier"])) for name, p in personas.items()
        },
    )


def hourly_requirements(
    daily_counts: pd.DataFrame,
    days: pd.DatetimeIndex,
    settings: TwinSettings,
    hour_shares: np.ndarray,
    group_multipliers: dict[str, float] | None = None,
    handle_time_multiplier: float = 1.0,
    absence_rate: float = 0.0,
) -> np.ndarray:
    """Erlang C agents needed per hour (one value per hour of ``days``).

    With ``absence_rate`` > 0 the requirement is inflated so that enough agents
    remain after absences (this is how a "prepared" plan anticipates a shortage).
    """
    sim = settings.sim
    planned, handle, open_mask = hourly_plan_inputs(
        daily_counts,
        days,
        hour_shares,
        sim.scale_factor,
        settings.mean_handle,
        sim.open_hour,
        sim.close_hour,
        sim.backlog_spread_hours,
        group_multipliers,
        handle_time_multiplier,
    )
    plan = plan_hourly_staffing(
        planned,
        handle,
        open_mask,
        sim.service_level_target,
        sim.service_level_threshold_seconds,
        sim.max_occupancy,
        sim.min_agents,
    )
    if absence_rate > 0:
        plan = np.where(open_mask, np.ceil(plan / (1 - absence_rate)), 0).astype(int)
    return plan


def make_contacts(
    daily_counts: pd.DataFrame,
    days: pd.DatetimeIndex,
    settings: TwinSettings,
    hour_shares: np.ndarray,
    rng: np.random.Generator,
    group_multipliers: dict[str, float] | None = None,
    handle_time_multiplier: float = 1.0,
) -> list[Contact]:
    """Customers of the given days (Poisson arrivals, personas, handle times)."""
    return generate_contacts(
        daily_counts[daily_counts["date"].isin(days)],
        hour_shares,
        days[0],
        settings.sim,
        settings.service_model,
        rng,
        patience_mix=settings.patience_mix,
        group_multipliers=group_multipliers,
        handle_time_multiplier=handle_time_multiplier,
    )


def workload_shares(daily_counts: pd.DataFrame, settings: TwinSettings) -> dict[str, float]:
    """Share of the handle-time workload of each intent group."""
    volume = daily_counts.groupby("intent_group")["contacts"].sum()
    work = {g: float(volume.get(g, 0)) * settings.mean_handle[g] for g in settings.groups}
    total = sum(work.values()) or 1.0
    return {g: w / total for g, w in work.items()}


def make_agent_pool(
    n_agents: int,
    shares: dict[str, float],
    settings: TwinSettings,
    overtime: bool = False,
    seed_offset: int = 0,
    first_id: int = 0,
) -> list[Agent]:
    """Skilled agents (fixed seed: the same people for every plan compared)."""
    rng = np.random.default_rng(settings.skills_seed + seed_offset)
    return build_agent_pool(
        n_agents,
        shares,
        settings.specialist_multiplier,
        settings.weak_multiplier,
        rng,
        overtime=overtime,
        first_id=first_id,
    )


def apply_absence(duty: np.ndarray, rate: float, rng: np.random.Generator) -> np.ndarray:
    """Remove each agent's whole day with probability ``rate`` (sick leave)."""
    if rate <= 0:
        return duty
    duty = duty.copy()
    n_days = duty.shape[1] // 24
    absent = rng.random((duty.shape[0], n_days)) < rate
    for day in range(n_days):
        duty[absent[:, day], day * 24 : (day + 1) * 24] = False
    return duty
