"""The digital twin: test staffing and routing decisions on a virtual call center.

One twin run = one scenario week:

1. Reality: the week's observed (synthetic) contacts, changed by the scenario
   multipliers, are replayed as Poisson arrivals with personas and handle times.
2. Plan: the Workforce agent plans shifts from the *forecast* (never from reality).
   "unprepared" plans from the normal forecast; "prepared" plans from the forecast
   adjusted by the scenario (this is the BO4 "test first" decision).
3. Routing: FIFO, skill score or the PPO agent assigns customers to advisors.
4. KPIs per seed (mean and 95% CI computed by the evaluation layer).

Ten seeds take a few seconds, so a manager can compare options interactively.
"""

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from callverse.agents.workforce.routing import make_router
from callverse.agents.workforce.scheduling import (
    SchedulePlan,
    cpsat_schedule,
    erlang_hourly_schedule,
    fixed_schedule,
    load_scheduling_rules,
    rule_schedule,
)
from callverse.data import loaders
from callverse.forecasting import weekly_forecast
from callverse.simulation import (
    SECONDS_PER_DAY,
    CallCenterEngine,
    OvertimeRule,
    apply_absence,
    engine_kpis,
    hourly_requirements,
    load_twin_settings,
    make_agent_pool,
    make_contacts,
    workload_shares,
)
from callverse.twin.state import ScenarioSpec, load_scenarios, scenario_defaults

PLAN_KINDS = ["cpsat", "rules_erlang", "fixed", "fixed_tuned", "erlang_hourly"]
ROUTERS = ["fifo", "skill_score", "ppo"]


@dataclass
class TwinRun:
    """One simulated week."""

    scenario: str
    plan: str
    router: str
    prepared: bool
    seed: int
    kpis: dict[str, float]
    records: pd.DataFrame | None = None
    queue: pd.DataFrame | None = None


class DigitalTwin:
    """Scenario runner over the SimPy engine, the forecast and the Workforce agent."""

    def __init__(self) -> None:
        self.settings = load_twin_settings()
        self.rules = load_scheduling_rules()
        self.daily = loaders.daily_contacts_by_group()
        self.hour_shares = loaders.hour_shares()
        self.scenarios = load_scenarios()
        self.drain_days = scenario_defaults()["drain_days"]
        self.agent_mix = workload_shares(self.daily, self.settings)
        self._plan_cache: dict[tuple, SchedulePlan] = {}

    # ------------------------------------------------------------------ planning
    def scenario(self, name: str) -> ScenarioSpec:
        if name not in self.scenarios:
            raise KeyError(f"Unknown scenario '{name}'. Known: {sorted(self.scenarios)}")
        return self.scenarios[name]

    def _horizon(self, spec: ScenarioSpec) -> pd.DatetimeIndex:
        return pd.date_range(spec.week_start, periods=spec.days + self.drain_days)

    def forecast_counts(self, spec: ScenarioSpec) -> pd.DataFrame:
        """Out-of-sample LightGBM forecast of the scenario days (+ drain days)."""
        return weekly_forecast(spec.week_start, days=spec.days + self.drain_days)

    def requirement(self, spec: ScenarioSpec, prepared: bool) -> np.ndarray:
        """Erlang C agents needed per day and hour, from the forecast."""
        days = pd.date_range(spec.week_start, periods=spec.days)
        forecast = self.forecast_counts(spec)
        if prepared:
            need = hourly_requirements(
                forecast,
                days,
                self.settings,
                self.hour_shares,
                spec.multipliers,
                spec.handle_time_multiplier,
                spec.absence_rate,
            )
        else:
            need = hourly_requirements(forecast, days, self.settings, self.hour_shares)
        return need.reshape(spec.days, 24)

    def plan(self, spec: ScenarioSpec, kind: str, prepared: bool = True) -> SchedulePlan:
        """Shift plan of a planner for a scenario (cached)."""
        key = (
            spec.name,
            spec.week_start,
            tuple(sorted(spec.multipliers.items())),
            spec.absence_rate,
            spec.handle_time_multiplier,
            kind,
            prepared,
        )
        if key in self._plan_cache:
            return self._plan_cache[key]
        need = self.requirement(spec, prepared)
        sim = self.settings.sim
        if kind == "cpsat":
            plan = cpsat_schedule(
                need,
                self.rules,
                sim.open_hour,
                sim.close_hour,
                self.settings.costs.regular_hourly,
                self.settings.costs.overtime_multiplier,
            )
        elif kind == "rules_erlang":
            plan = rule_schedule(need, self.rules)
        elif kind == "fixed":
            plan = fixed_schedule(need, self.rules, sim.open_hour, sim.close_hour)
        elif kind == "fixed_tuned":
            plan = fixed_schedule(need, self.rules, sim.open_hour, sim.close_hour, tuned=True)
        elif kind == "erlang_hourly":
            plan = erlang_hourly_schedule(need)
        else:
            raise ValueError(f"Unknown plan '{kind}' ({', '.join(PLAN_KINDS)}).")
        self._plan_cache[key] = plan
        return plan

    # ---------------------------------------------------------------- simulation
    def simulate(
        self,
        spec: ScenarioSpec,
        plan: SchedulePlan,
        router: str = "fifo",
        seed: int = 0,
        keep_records: bool = False,
        trace: bool = False,
        prepared: bool = True,
    ) -> TwinRun:
        """Replay the scenario's reality against a plan and a router."""
        days = self._horizon(spec)
        contacts = make_contacts(
            self.daily,
            days,
            self.settings,
            self.hour_shares,
            np.random.default_rng(seed),
            spec.multipliers,
            spec.handle_time_multiplier,
        )
        regular, overtime = plan.duty_matrices(self.drain_days)
        agents = make_agent_pool(regular.shape[0], self.agent_mix, self.settings)
        overtime_agents = make_agent_pool(
            overtime.shape[0],
            self.agent_mix,
            self.settings,
            overtime=True,
            seed_offset=99,
            first_id=len(agents),
        )
        regular = apply_absence(regular, spec.absence_rate, np.random.default_rng(seed + 7))
        duty = np.vstack([regular, overtime]) if len(overtime_agents) else regular
        rule = pool = None
        if plan.realtime_overtime:
            sim = self.settings.sim
            rule = OvertimeRule(
                self.rules.overtime_queue_threshold,
                self.rules.overtime_extra_agents,
                sim.open_hour,
                sim.close_hour,
            )
            pool = make_agent_pool(
                self.rules.overtime_extra_agents,
                self.agent_mix,
                self.settings,
                overtime=True,
                seed_offset=199,
                first_id=10_000,
            )
        engine = CallCenterEngine(
            contacts,
            agents + overtime_agents,
            duty,
            make_router(router, self.settings.mean_handle),
            overtime_rule=rule,
            overtime_pool=pool,
            trace_interval=900.0 if trace else None,
        )
        records = engine.run()
        sim = self.settings.sim
        kpis = engine_kpis(
            engine,
            records,
            sim.service_level_threshold_seconds,
            sim.service_level_target,
            self.settings.costs,
            evaluation_end=spec.days * SECONDS_PER_DAY,
        )
        kpis.update(
            plan.planned_cost(self.settings.costs.regular_hourly, self.settings.costs.overtime_multiplier)
        )
        return TwinRun(
            spec.name,
            plan.name,
            router,
            prepared,
            seed,
            kpis,
            records if keep_records else None,
            engine.queue_trace_frame() if trace else None,
        )

    def run(
        self,
        spec: ScenarioSpec | str,
        plan_kind: str = "cpsat",
        router: str = "fifo",
        seeds: int | None = None,
        prepared: bool = True,
        trace_first: bool = False,
    ) -> list[TwinRun]:
        """Simulate one configuration over several seeds (common random numbers)."""
        spec = self.scenario(spec) if isinstance(spec, str) else spec
        seeds = seeds or scenario_defaults()["seeds"]
        plan = self.plan(spec, plan_kind, prepared)
        return [
            self.simulate(
                spec,
                plan,
                router,
                seed,
                keep_records=trace_first and seed == 0,
                trace=trace_first and seed == 0,
                prepared=prepared,
            )
            for seed in range(seeds)
        ]

    def describe(self) -> dict[str, Any]:
        """Settings shown on the dashboard."""
        sim = self.settings.sim
        return {
            "scenarios": {
                n: {
                    "label": s.label,
                    "description": s.description,
                    "week_start": str(s.week_start.date()),
                    "multipliers": s.multipliers,
                    "absence_rate": s.absence_rate,
                    "handle_time_multiplier": s.handle_time_multiplier,
                }
                for n, s in self.scenarios.items()
            },
            "plans": PLAN_KINDS,
            "routers": ROUTERS,
            "opening_hours": [sim.open_hour, sim.close_hour],
            "service_level_target": sim.service_level_target,
            "threshold_seconds": sim.service_level_threshold_seconds,
            "scale_factor": sim.scale_factor,
            "costs": {
                "regular_hourly_eur": self.settings.costs.regular_hourly,
                "overtime_multiplier": self.settings.costs.overtime_multiplier,
                "abandonment_cost_eur": self.settings.costs.abandonment_cost,
            },
        }


def runs_to_frame(runs: list[TwinRun]) -> pd.DataFrame:
    """One row per run with every KPI."""
    return pd.DataFrame(
        [
            {
                "scenario": r.scenario,
                "plan": r.plan,
                "router": r.router,
                "prepared": r.prepared,
                "seed": r.seed,
                **r.kpis,
            }
            for r in runs
        ]
    )
