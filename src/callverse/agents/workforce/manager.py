"""Workforce manager agent: one agent, two jobs (DSO1 routing, DSO3 planning).

A thin facade so the rest of the system talks to "the workforce agent" rather than
to the individual planners and routers:

- ``plan_week``: shifts and overtime for a week of hourly requirements
  (CP-SAT main idea, Erlang C + rules backup, fixed-schedule baseline).
- ``router``: the routing policy used in real time (PPO main idea, skill-score
  backup, FIFO baseline).
"""

from dataclasses import dataclass, field

import numpy as np

from callverse.agents.workforce.routing import make_router, ppo_available
from callverse.agents.workforce.scheduling import (
    SchedulePlan,
    SchedulingRules,
    cpsat_schedule,
    erlang_hourly_schedule,
    fixed_schedule,
    load_scheduling_rules,
    rule_schedule,
)
from callverse.simulation import TwinSettings, load_twin_settings


@dataclass
class WorkforceManager:
    """Plans shifts and chooses the routing policy."""

    settings: TwinSettings = field(default_factory=load_twin_settings)
    rules: SchedulingRules = field(default_factory=load_scheduling_rules)

    def plan_week(self, requirement: np.ndarray, planner: str = "cpsat") -> SchedulePlan:
        """Shift plan for a (days x 24) matrix of agents needed per hour."""
        sim = self.settings.sim
        if planner == "cpsat":
            return cpsat_schedule(
                requirement,
                self.rules,
                sim.open_hour,
                sim.close_hour,
                self.settings.costs.regular_hourly,
                self.settings.costs.overtime_multiplier,
            )
        if planner == "rules_erlang":
            return rule_schedule(requirement, self.rules)
        if planner in ("fixed", "fixed_tuned"):
            return fixed_schedule(
                requirement, self.rules, sim.open_hour, sim.close_hour, planner == "fixed_tuned"
            )
        if planner == "erlang_hourly":
            return erlang_hourly_schedule(requirement)
        raise ValueError(f"Unknown planner '{planner}'.")

    def router(self, kind: str | None = None):
        """Routing policy; by default the best available (PPO if trained, else skill score)."""
        kind = kind or ("ppo" if ppo_available() else "skill_score")
        return make_router(kind, self.settings.mean_handle)
