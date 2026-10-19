"""Workforce agent, planning part (DSO3): shifts and overtime for a week.

Three planners, all driven by the forecast through the Erlang C requirement
(agents needed per hour to answer 80% of chats within 20 s):

- ``cpsat_schedule`` (main idea B): Google OR-Tools CP-SAT finds the cheapest mix
  of 4/6/8-hour shifts and overtime hours that covers the requirement, then builds
  a legal roster (max 5 days and 40 h per agent per week, 11 h rest).
- ``rule_schedule`` (backup): Erlang C + two fixed shift templates (morning,
  afternoon); overtime is decided in real time by a queue rule in the twin.
- ``fixed_schedule`` (baseline of the DSO document): the same number of agents
  every open hour of every day, no overtime logic.

Each planner returns a ``SchedulePlan`` the twin can simulate and cost.
"""

import math
import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from callverse.config import load_yaml


@dataclass(frozen=True)
class SchedulingRules:
    """Labour rules and solver settings (``workforce.scheduling`` in agents.yaml)."""

    shift_lengths: tuple[int, ...]
    max_days_per_week: int
    max_regular_hours_per_week: int
    min_rest_hours: int
    max_overtime_agents_per_hour: int
    max_overtime_hours_per_week: int
    headcount: int | None
    understaffing_penalty_eur: float
    time_limit_seconds: float
    random_seed: int
    fixed_quantile: float
    fixed_tuned_quantile: float
    rule_templates: dict[str, tuple[int, int]]
    overtime_queue_threshold: int
    overtime_extra_agents: int


def load_scheduling_rules() -> SchedulingRules:
    """Read the scheduling section of ``configs/agents.yaml``."""
    raw = load_yaml("agents")["workforce"]["scheduling"]
    headcount = raw["headcount"]
    return SchedulingRules(
        shift_lengths=tuple(int(x) for x in raw["shift_lengths_hours"]),
        max_days_per_week=int(raw["max_days_per_week"]),
        max_regular_hours_per_week=int(raw["max_regular_hours_per_week"]),
        min_rest_hours=int(raw["min_rest_hours"]),
        max_overtime_agents_per_hour=int(raw["max_overtime_agents_per_hour"]),
        max_overtime_hours_per_week=int(raw["max_overtime_hours_per_week"]),
        headcount=None if headcount == "auto" else int(headcount),
        understaffing_penalty_eur=float(raw["understaffing_penalty_eur"]),
        time_limit_seconds=float(raw["solver_time_limit_seconds"]),
        random_seed=int(raw["random_seed"]),
        fixed_quantile=float(raw["fixed_schedule_quantile"]),
        fixed_tuned_quantile=float(raw.get("fixed_tuned_quantile", 0.75)),
        rule_templates={k: (int(v[0]), int(v[1])) for k, v in raw["rule_templates"].items()},
        overtime_queue_threshold=int(raw["overtime_rule"]["queue_threshold"]),
        overtime_extra_agents=int(raw["overtime_rule"]["extra_agents"]),
    )


@dataclass
class SchedulePlan:
    """Agents per day and hour (regular and overtime), and the named roster."""

    name: str
    regular: np.ndarray  # (days, 24)
    overtime: np.ndarray  # (days, 24)
    roster: pd.DataFrame  # agent_id, day, start_hour, end_hour, hours
    requirement: np.ndarray  # (days, 24) Erlang C agents needed
    status: str = "ok"
    solve_seconds: float = 0.0
    realtime_overtime: bool = False
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def days(self) -> int:
        return self.regular.shape[0]

    @property
    def headcount(self) -> int:
        if self.roster.empty:
            return int(self.regular.max(initial=0))
        return int(self.roster["agent_id"].nunique())

    def shortfall(self) -> np.ndarray:
        """Agents missing per day and hour versus the requirement."""
        return np.maximum(self.requirement - self.regular - self.overtime, 0)

    def planned_cost(self, regular_hourly: float, overtime_multiplier: float) -> dict[str, float]:
        """Planned paid hours and cost (before simulation)."""
        regular_hours = float(self.regular.sum())
        overtime_hours = float(self.overtime.sum())
        return {
            "planned_regular_hours": regular_hours,
            "planned_overtime_hours": overtime_hours,
            "planned_cost_eur": regular_hourly * (regular_hours + overtime_multiplier * overtime_hours),
            "planned_shortfall_agent_hours": float(self.shortfall().sum()),
            "planned_understaffed_hours": float((self.shortfall() > 0).sum()),
            "headcount": float(self.headcount),
        }

    def duty_matrices(self, drain_days: int = 1) -> tuple[np.ndarray, np.ndarray]:
        """(regular duty, overtime duty): one row per agent, one column per hour.

        Drain days repeat the first day's pattern (they only serve the backlog and
        are not costed).
        """
        hours = (self.days + drain_days) * 24
        if not self.roster.empty:
            agents = sorted(self.roster["agent_id"].unique())
            row_of = {agent: row for row, agent in enumerate(agents)}
            regular = np.zeros((len(agents), hours), dtype=bool)
            for shift in self.roster.itertuples():
                for day in [shift.day] + (
                    [self.days + k for k in range(drain_days)] if shift.day == 0 else []
                ):
                    regular[
                        row_of[shift.agent_id], day * 24 + shift.start_hour : day * 24 + shift.end_hour
                    ] = True
        else:
            counts = np.concatenate([self.regular.ravel(), np.tile(self.regular[0], drain_days)])
            regular = np.arange(int(counts.max(initial=0)))[:, None] < counts[None, :]
        overtime_counts = np.concatenate([self.overtime.ravel(), np.zeros(drain_days * 24, dtype=int)])
        overtime = np.arange(int(overtime_counts.max(initial=0)))[:, None] < overtime_counts[None, :]
        return regular, overtime

    def to_frame(self) -> pd.DataFrame:
        """Long table: day, hour, required, regular, overtime (for the dashboard)."""
        days, hours = np.indices(self.regular.shape)
        return pd.DataFrame(
            {
                "day": days.ravel(),
                "hour": hours.ravel(),
                "required": self.requirement.ravel(),
                "regular": self.regular.ravel(),
                "overtime": self.overtime.ravel(),
                "plan": self.name,
            }
        )


def _open_hours(requirement: np.ndarray, open_hour: int, close_hour: int) -> list[int]:
    return list(range(open_hour, close_hour))


def fixed_schedule(
    requirement: np.ndarray, rules: SchedulingRules, open_hour: int, close_hour: int, tuned: bool = False
) -> SchedulePlan:
    """Baseline: a constant number of agents every open hour, no overtime.

    Sized for the busiest hour (quantile 1.0) by default; ``tuned`` uses a lower
    quantile and accepts some understaffed hours (sensitivity check).
    """
    quantile = rules.fixed_tuned_quantile if tuned else rules.fixed_quantile
    open_values = requirement[:, open_hour:close_hour].ravel()
    level = int(math.ceil(np.quantile(open_values, quantile)))
    regular = np.zeros_like(requirement)
    regular[:, open_hour:close_hour] = level
    return SchedulePlan(
        "fixed_tuned" if tuned else "fixed",
        regular,
        np.zeros_like(requirement),
        pd.DataFrame(),
        requirement,
        meta={"agents_every_open_hour": level, "quantile": quantile},
    )


def erlang_hourly_schedule(requirement: np.ndarray) -> SchedulePlan:
    """Reference: exactly the Erlang C need every hour (ignores shift rules)."""
    return SchedulePlan(
        "erlang_hourly", requirement.copy(), np.zeros_like(requirement), pd.DataFrame(), requirement
    )


def rule_schedule(requirement: np.ndarray, rules: SchedulingRules) -> SchedulePlan:
    """Backup: Erlang C + morning/afternoon templates; overtime by queue rule in the twin."""
    (m_start, m_end), (a_start, a_end) = rules.rule_templates["morning"], rules.rule_templates["afternoon"]
    regular = np.zeros_like(requirement)
    for day in range(requirement.shape[0]):
        need = requirement[day]
        morning = int(need[m_start:a_start].max(initial=0))
        afternoon = int(need[m_end:a_end].max(initial=0))
        overlap = need[a_start:m_end]
        if len(overlap):
            afternoon = max(afternoon, int((overlap - morning).max(initial=0)))
        regular[day, m_start:m_end] += morning
        regular[day, a_start:a_end] += afternoon
    plan = SchedulePlan(
        "rules_erlang",
        regular,
        np.zeros_like(requirement),
        pd.DataFrame(),
        requirement,
        realtime_overtime=True,
    )
    plan.meta = {
        "templates": rules.rule_templates,
        "overtime_rule": {
            "queue_threshold": rules.overtime_queue_threshold,
            "extra_agents": rules.overtime_extra_agents,
        },
    }
    return plan


def shift_templates(lengths: tuple[int, ...], open_hour: int, close_hour: int) -> list[tuple[int, int]]:
    """Every (start, end) shift inside the opening hours."""
    return [
        (start, start + length) for length in lengths for start in range(open_hour, close_hour - length + 1)
    ]


def cpsat_schedule(
    requirement: np.ndarray,
    rules: SchedulingRules,
    open_hour: int,
    close_hour: int,
    regular_hourly: float,
    overtime_multiplier: float,
) -> SchedulePlan:
    """Main DSO3 planner: cheapest legal shifts + overtime covering the requirement."""
    from ortools.sat.python import cp_model

    started = time.perf_counter()
    days = requirement.shape[0]
    templates = shift_templates(rules.shift_lengths, open_hour, close_hour)
    hours = range(open_hour, close_hour)
    peak = int(requirement.max(initial=0))
    big = rules.headcount or max(peak * 4, 10)

    # ---- Stage 1: how many agents on each shift template, and overtime per hour
    model = cp_model.CpModel()
    x = {(d, t): model.new_int_var(0, big, f"x_{d}_{t}") for d in range(days) for t in range(len(templates))}
    o = {
        (d, h): model.new_int_var(0, rules.max_overtime_agents_per_hour, f"o_{d}_{h}")
        for d in range(days)
        for h in hours
    }
    s = {
        (d, h): model.new_int_var(0, int(requirement[d, h]), f"s_{d}_{h}") for d in range(days) for h in hours
    }
    for d in range(days):
        for h in hours:
            covering = [x[d, t] for t, (a, b) in enumerate(templates) if a <= h < b]
            model.add(sum(covering) + o[d, h] + s[d, h] >= int(requirement[d, h]))
        model.add(sum(x[d, t] for t in range(len(templates))) <= big)
    model.add(sum(o.values()) <= rules.max_overtime_hours_per_week)
    if rules.headcount:
        model.add(
            sum(x[d, t] * (b - a) for (d, t), _ in zip(x, x) for a, b in [templates[t]])
            <= rules.headcount * rules.max_regular_hours_per_week
        )
        model.add(sum(x.values()) <= rules.headcount * rules.max_days_per_week)
    regular_cents = int(round(regular_hourly * 100))
    overtime_cents = int(round(regular_hourly * overtime_multiplier * 100))
    penalty_cents = int(round(rules.understaffing_penalty_eur * 100))
    model.minimize(
        sum(regular_cents * (templates[t][1] - templates[t][0]) * var for (d, t), var in x.items())
        + overtime_cents * sum(o.values())
        + penalty_cents * sum(s.values())
    )
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = rules.time_limit_seconds
    solver.parameters.random_seed = rules.random_seed
    solver.parameters.num_workers = 1  # deterministic: same roster every run
    status = solver.solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise RuntimeError("CP-SAT found no shift plan.")
    stage1_status = solver.status_name(status)
    counts = {(d, t): int(solver.value(var)) for (d, t), var in x.items()}
    overtime = np.zeros_like(requirement)
    for (d, h), var in o.items():
        overtime[d, h] = int(solver.value(var))

    # ---- Stage 2: give the shifts to named agents within the labour rules
    shifts = [(d, t) for (d, t), n in counts.items() for _ in range(n)]
    total_hours = sum(templates[t][1] - templates[t][0] for d, t in shifts)
    daily_max = max((sum(1 for dd, _ in shifts if dd == d) for d in range(days)), default=0)
    headcount = rules.headcount or max(
        daily_max,
        math.ceil(len(shifts) / rules.max_days_per_week),
        math.ceil(total_hours / rules.max_regular_hours_per_week),
        1,
    )
    roster = None
    for extra in range(0, 12):
        roster = _assign_roster(counts, templates, days, headcount + extra, rules)
        if roster is not None:
            headcount += extra
            break
    if roster is None:
        raise RuntimeError("CP-SAT could not build a legal roster.")
    regular = np.zeros_like(requirement)
    for shift in roster.itertuples():
        regular[shift.day, shift.start_hour : shift.end_hour] += 1
    plan = SchedulePlan(
        "cpsat",
        regular,
        overtime,
        roster,
        requirement,
        status=stage1_status,
        solve_seconds=time.perf_counter() - started,
    )
    plan.meta = {
        "templates": len(templates),
        "stage1_objective_eur": solver.objective_value / 100,
        "headcount": headcount,
    }
    return plan


def _assign_roster(
    counts: dict[tuple[int, int], int],
    templates: list[tuple[int, int]],
    days: int,
    headcount: int,
    rules: SchedulingRules,
) -> pd.DataFrame | None:
    """Stage 2 of CP-SAT: named roster, or None if ``headcount`` agents are not enough."""
    from ortools.sat.python import cp_model

    model = cp_model.CpModel()
    used = [(d, t) for (d, t), n in counts.items() if n > 0]
    y = {(a, d, t): model.new_bool_var(f"y_{a}_{d}_{t}") for a in range(headcount) for d, t in used}
    for d, t in used:
        model.add(sum(y[a, d, t] for a in range(headcount)) == counts[d, t])
    hours_of = {}
    for a in range(headcount):
        for d in range(days):
            model.add(sum(y[a, dd, t] for dd, t in used if dd == d) <= 1)
        model.add(sum(y[a, d, t] for d, t in used) <= rules.max_days_per_week)
        hours_of[a] = sum((templates[t][1] - templates[t][0]) * y[a, d, t] for d, t in used)
        model.add(hours_of[a] <= rules.max_regular_hours_per_week)
        for d, t1 in used:
            for d2, t2 in used:
                if d2 == d + 1 and 24 - templates[t1][1] + templates[t2][0] < rules.min_rest_hours:
                    model.add(y[a, d, t1] + y[a, d2, t2] <= 1)
    for a in range(headcount - 1):  # symmetry breaking: agents sorted by hours worked
        model.add(hours_of[a] >= hours_of[a + 1])
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max(5.0, rules.time_limit_seconds / 2)
    solver.parameters.random_seed = rules.random_seed
    solver.parameters.num_workers = 1  # deterministic: same roster every run
    status = solver.solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None
    rows = [
        {
            "agent_id": a,
            "day": d,
            "start_hour": templates[t][0],
            "end_hour": templates[t][1],
            "hours": templates[t][1] - templates[t][0],
        }
        for (a, d, t), var in y.items()
        if solver.value(var)
    ]
    return pd.DataFrame(rows).sort_values(["agent_id", "day"]).reset_index(drop=True)


def roster_compliance(roster: pd.DataFrame, rules: SchedulingRules) -> dict[str, bool]:
    """Labour-rule checks of a roster (DSO3: no schedule breaks the limits)."""
    if roster.empty:
        return {"max_days": True, "max_hours": True, "one_shift_per_day": True, "min_rest": True}
    per_agent = roster.groupby("agent_id")
    rest_ok = True
    for _, shifts in per_agent:
        shifts = shifts.sort_values("day")
        for first, second in zip(shifts.itertuples(), list(shifts.itertuples())[1:]):
            if second.day == first.day + 1 and 24 - first.end_hour + second.start_hour < rules.min_rest_hours:
                rest_ok = False
    return {
        "max_days": bool((per_agent["day"].nunique() <= rules.max_days_per_week).all()),
        "max_hours": bool((per_agent["hours"].sum() <= rules.max_regular_hours_per_week).all()),
        "one_shift_per_day": not roster.duplicated(["agent_id", "day"]).any(),
        "min_rest": rest_ok,
    }
