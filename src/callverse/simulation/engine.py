"""Digital-twin engine (version 2): skilled agents, pluggable routing, costs.

Compared with ``environment.run_simulation`` (version 1, one FIFO pool), this
engine adds what DSO1 and DSO3 need:

- agents with a skill profile (handle-time multiplier per intent group),
- a router that decides who takes whom (FIFO, skill score, or an RL agent),
- a duty matrix (which agent works which hour), regular vs overtime agents,
- an optional real-time overtime rule (call extra agents when the queue is long),
- waiting-time and cost accounting.

With every skill multiplier at 1.0 and the FIFO router, it reproduces version 1.

The engine can also run step by step for reinforcement learning: with an
``external`` router it stops whenever a routing decision is needed
(``pending``), the RL loop answers with ``resolve(index)``, then ``advance()``.
"""

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
import simpy

from callverse.simulation.customers import SECONDS_PER_DAY, SECONDS_PER_HOUR, Contact
from callverse.simulation.policy import Agent, Router


@dataclass(frozen=True)
class OvertimeRule:
    """Backup DSO3 rule: at the top of an open hour, if at least ``queue_threshold``
    live customers are waiting, ``extra_agents`` overtime agents work that hour."""

    queue_threshold: int
    extra_agents: int
    open_hour: int
    close_hour: int


@dataclass(frozen=True)
class CostModel:
    """Labour cost assumptions (EUR)."""

    regular_hourly: float = 12.0
    overtime_multiplier: float = 1.5
    abandonment_cost: float = 8.0


def build_agent_pool(
    n_agents: int,
    workload_share: dict[str, float],
    specialist: float,
    weak: float,
    rng: np.random.Generator,
    overtime: bool = False,
    first_id: int = 0,
) -> list[Agent]:
    """Agents with a primary group (faster) and one weak group (slower).

    Primary groups are spread in proportion to each group's share of the workload
    (volume x handle time), so the pool matches the demand mix.
    """
    groups = list(workload_share)
    shares = np.array([workload_share[g] for g in groups], dtype=float)
    shares = shares / shares.sum()
    # Deterministic largest-remainder allocation, then a shuffled order
    quotas = shares * n_agents
    counts = np.floor(quotas).astype(int)
    for index in np.argsort(-(quotas - counts))[: n_agents - counts.sum()]:
        counts[index] += 1
    primaries = [g for g, c in zip(groups, counts) for _ in range(c)]
    rng.shuffle(primaries)
    agents = []
    for offset, primary in enumerate(primaries):
        others = [g for g in groups if g != primary]
        weak_group = others[int(rng.integers(len(others)))] if others else None
        speed = {g: 1.0 for g in groups}
        speed[primary] = specialist
        if weak_group:
            speed[weak_group] = weak
        agents.append(Agent(first_id + offset, speed, primary, overtime=overtime))
    return agents


def uniform_agents(n_agents: int, groups: list[str]) -> list[Agent]:
    """Identical generalists (version-1 behaviour)."""
    return [Agent(i, {g: 1.0 for g in groups}, "") for i in range(n_agents)]


def duty_from_counts(staffing: np.ndarray, n_agents: int | None = None) -> np.ndarray:
    """Duty matrix where agent ``a`` works hour ``h`` when ``a < staffing[h]``."""
    n_agents = int(staffing.max(initial=0)) if n_agents is None else n_agents
    return np.arange(n_agents)[:, None] < np.asarray(staffing)[None, :]


class CallCenterEngine:
    """SimPy call center with pluggable routing. Use ``run()`` or the RL stepping API."""

    def __init__(
        self,
        contacts: list[Contact],
        agents: list[Agent],
        duty: np.ndarray,
        router: Router,
        overtime_rule: OvertimeRule | None = None,
        overtime_pool: list[Agent] | None = None,
        trace_interval: float | None = 900.0,
        backlog_wait_weight: float = 1.0,
    ) -> None:
        if any(b.arrival < a.arrival for a, b in zip(contacts, contacts[1:])):
            raise ValueError("Contacts must be sorted by arrival time.")
        if duty.shape[0] != len(agents):
            raise ValueError("The duty matrix needs one row per agent.")
        self.contacts = contacts
        self.agents = list(agents)
        self.duty = np.asarray(duty, dtype=bool)
        self.hours = self.duty.shape[1]
        self.end_time = float(self.hours * SECONDS_PER_HOUR)
        self.router = router
        self.overtime_rule = overtime_rule
        self.overtime_pool = list(overtime_pool or [])
        self.trace_interval = trace_interval
        self.backlog_wait_weight = backlog_wait_weight

        for contact in contacts:  # each run starts from fresh contact state
            contact.start = contact.end = contact.agent_id = contact.handle_seconds = None
            contact.abandoned = False
        for agent in self.agents + self.overtime_pool:
            agent.on_duty = agent.busy = agent.leave_after_contact = False
            agent.idle_since = agent.busy_seconds = 0.0
            agent.handled = 0

        self.env = simpy.Environment()
        self.waiting: list[Contact] = []
        self.free: list[Agent] = []
        self.pending: tuple[Agent, list[Contact]] | None = None
        self.wait_area = 0.0  # weighted customer-seconds spent waiting so far
        self.abandons = 0
        self.dynamic_overtime_hours = np.zeros(self.hours, dtype=int)
        self.queue_trace: list[tuple[float, int, int, int]] = []
        self._last = 0.0
        self._started = False
        if hasattr(router, "bind"):
            router.bind(self)

    # ----------------------------------------------------------------- bookkeeping
    def _tick(self, at: float | None = None) -> None:
        """Accumulate waiting time since the last event and drop abandoned contacts."""
        now = self.env.now if at is None else at
        if now > self._last:
            for contact in self.waiting:
                end = now if contact.abandon_at is None else min(now, contact.abandon_at)
                waited = max(0.0, end - max(self._last, contact.arrival))
                weight = 1.0 if contact.is_live else self.backlog_wait_weight
                self.wait_area += weight * waited
            self._last = now
        if any(c.abandon_at is not None and c.abandon_at <= now for c in self.waiting):
            keep = []
            for contact in self.waiting:
                if contact.abandon_at is not None and contact.abandon_at <= now:
                    contact.abandoned = True
                    self.abandons += 1
                else:
                    keep.append(contact)
            self.waiting = keep

    def _start_service(self, agent: Agent, contact: Contact) -> None:
        now = self.env.now
        handle = contact.service_seconds * agent.speed.get(contact.intent_group, 1.0)
        contact.start = now
        contact.agent_id = agent.agent_id
        contact.handle_seconds = handle
        agent.busy = True
        agent.busy_seconds += handle
        agent.handled += 1
        self.env.process(self._serve(agent, contact, handle))

    def _assign(self, agent: Agent, contact: Contact) -> None:
        self.waiting.remove(contact)
        self.free.remove(agent)
        self._start_service(agent, contact)

    def _dispatch(self) -> None:
        """Match free agents and waiting customers until one side is empty."""
        if self.pending is not None:
            return
        now = self.env.now
        while self.free and self.waiting:
            if len(self.waiting) == 1:
                contact = self.waiting[0]
                agent = self.free[self.router.pick_agent(contact, self.free, now)]
                self._assign(agent, contact)
                continue
            agent = min(self.free, key=lambda a: a.idle_since)  # longest idle first
            if self.router.external:
                self.pending = (agent, list(self.waiting))
                return
            index = self.router.pick_contact(agent, self.waiting, now)
            self._assign(agent, self.waiting[index])

    # ------------------------------------------------------------------- processes
    def _arrivals(self):
        for contact in self.contacts:
            if contact.arrival >= self.end_time:
                return
            yield self.env.timeout(contact.arrival - self.env.now)
            self._tick()
            self.waiting.append(contact)
            self._dispatch()

    def _serve(self, agent: Agent, contact: Contact, handle: float):
        yield self.env.timeout(handle)
        self._tick()
        contact.end = self.env.now
        agent.busy = False
        if agent.on_duty:
            agent.idle_since = self.env.now
            self.free.append(agent)
            self._dispatch()

    def _set_duty(self, agent: Agent, on: bool) -> None:
        if on and not agent.on_duty:
            agent.on_duty = True
            if not agent.busy:
                agent.idle_since = self.env.now
                self.free.append(agent)
        elif not on and agent.on_duty:
            agent.on_duty = False
            if agent in self.free:
                self.free.remove(agent)

    def _shift_clock(self):
        for hour in range(self.hours):
            yield self.env.timeout(hour * SECONDS_PER_HOUR - self.env.now)
            self._tick()
            for index, agent in enumerate(self.agents):
                self._set_duty(agent, bool(self.duty[index, hour]))
            if self.overtime_rule and self.overtime_pool:
                rule = self.overtime_rule
                hour_of_day = hour % 24
                live_waiting = sum(c.is_live for c in self.waiting)
                call_in = (
                    rule.open_hour <= hour_of_day < rule.close_hour and live_waiting >= rule.queue_threshold
                )
                extra = min(rule.extra_agents, len(self.overtime_pool)) if call_in else 0
                for index, agent in enumerate(self.overtime_pool):
                    self._set_duty(agent, index < extra)
                self.dynamic_overtime_hours[hour] = extra
            self._dispatch()

    def _queue_sampler(self):
        while self.env.now < self.end_time:
            self._tick()
            self.queue_trace.append(
                (
                    self.env.now,
                    sum(c.is_live for c in self.waiting),
                    sum(a.busy for a in self.agents + self.overtime_pool),
                    sum(a.on_duty for a in self.agents + self.overtime_pool),
                )
            )
            yield self.env.timeout(self.trace_interval)

    # ------------------------------------------------------------------- execution
    def start(self) -> None:
        """Register the processes (called once, by ``run`` or the RL wrapper)."""
        if self._started:
            return
        self._started = True
        self.env.process(self._shift_clock())
        self.env.process(self._arrivals())
        if self.trace_interval:
            self.env.process(self._queue_sampler())

    def advance(self) -> bool:
        """Run until a routing decision is pending (True) or the horizon ends (False)."""
        self.start()
        while self.pending is None:
            if self.env.peek() >= self.end_time:
                self._tick(self.end_time)  # count waiting up to the end of the horizon
                return False
            self.env.step()
        return True

    def resolve(self, index: int) -> None:
        """Apply the external router's choice for the pending decision."""
        if self.pending is None:
            raise RuntimeError("No routing decision is pending.")
        agent, candidates = self.pending
        self.pending = None
        contact = candidates[index]
        self._assign(agent, contact)
        self._dispatch()

    def run(self) -> pd.DataFrame:
        """Simulate the whole horizon with an internal router."""
        if self.router.external:
            raise RuntimeError("An external router must drive the engine with advance().")
        self.start()
        self.env.run(until=self.end_time)
        return self.records()

    def finish(self) -> None:
        """Flag customers whose patience ran out before the end as abandoned."""
        for contact in self.contacts:
            if (
                contact.start is None
                and not contact.abandoned
                and contact.abandon_at is not None
                and contact.abandon_at <= self.end_time
                and contact.arrival < self.end_time
            ):
                contact.abandoned = True

    def records(self) -> pd.DataFrame:
        """One row per contact (same columns as version 1, plus skills and agent)."""
        self.finish()
        contacts = [c for c in self.contacts if c.arrival < self.end_time]
        records = pd.DataFrame(
            {
                "contact_id": [c.contact_id for c in contacts],
                "arrival": [c.arrival for c in contacts],
                "intent_group": [c.intent_group for c in contacts],
                "patience_class": [c.patience_class for c in contacts],
                "is_live": [c.is_live for c in contacts],
                "service_seconds": [c.service_seconds for c in contacts],
                "handle_seconds": [c.handle_seconds for c in contacts],
                "abandon_at": [c.abandon_at for c in contacts],
                "start": [c.start for c in contacts],
                "end": [c.end for c in contacts],
                "abandoned": [c.abandoned for c in contacts],
                "agent_id": [c.agent_id for c in contacts],
            }
        )
        records["wait"] = records["start"] - records["arrival"]
        return records

    # ------------------------------------------------------------------- staffing
    def staffed_hours(self, until_hour: int | None = None) -> dict[str, float]:
        """Paid agent-hours (before ``until_hour``): regular, planned and real-time overtime."""
        duty = self.duty[:, :until_hour]
        overtime_rows = np.array([a.overtime for a in self.agents], dtype=bool)
        planned_overtime = float(duty[overtime_rows].sum()) if overtime_rows.any() else 0.0
        regular = float(duty[~overtime_rows].sum())
        return {
            "regular_hours": regular,
            "planned_overtime_hours": planned_overtime,
            "dynamic_overtime_hours": float(self.dynamic_overtime_hours[:until_hour].sum()),
        }

    def busy_seconds(self, until: float | None = None) -> float:
        """Handle time worked before ``until`` (default: end of the horizon)."""
        until = self.end_time if until is None else until
        records = self.records()
        started = records["start"].notna() & (records["start"] < until)
        begin = records.loc[started, "start"]
        end = np.minimum(begin + records.loc[started, "handle_seconds"], until)
        return float((end - begin).sum())

    def queue_trace_frame(self) -> pd.DataFrame:
        """Queue length, busy and on-duty agents every ``trace_interval`` seconds."""
        frame = pd.DataFrame(self.queue_trace, columns=["time", "live_waiting", "busy", "on_duty"])
        frame["day"] = (frame["time"] // SECONDS_PER_DAY).astype(int)
        frame["hour"] = frame["time"] / SECONDS_PER_HOUR
        return frame


def engine_kpis(
    engine: CallCenterEngine,
    records: pd.DataFrame,
    threshold_seconds: float,
    service_level_target: float,
    costs: CostModel,
    evaluation_end: float | None = None,
) -> dict[str, Any]:
    """Business KPIs of one run (BO1, BO3, BO4 side; BO2 comes from the agents).

    Only contacts arriving before ``evaluation_end`` are scored (the rest of the
    horizon lets the queue drain). Definitions:

    - service level: live contacts answered within the threshold / live offered
    - abandon rate: live contacts that hung up / live offered
    - ASA: average wait of answered live contacts
    - understaffed hours: open hours whose service level is below the target
    - labour cost: paid hours x rate (overtime x multiplier); cost per handled contact
    """
    scored = records if evaluation_end is None else records[records["arrival"] < evaluation_end]
    live = scored[scored["is_live"]]
    backlog = scored[~scored["is_live"]]
    answered_live = live[live["start"].notna()]
    handled = scored[scored["start"].notna()]
    in_time = answered_live["wait"] <= threshold_seconds

    until_hour = None if evaluation_end is None else int(evaluation_end // SECONDS_PER_HOUR)
    hours = engine.staffed_hours(until_hour)
    paid_regular = hours["regular_hours"]
    paid_overtime = hours["planned_overtime_hours"] + hours["dynamic_overtime_hours"]
    labour_cost = costs.regular_hourly * (paid_regular + costs.overtime_multiplier * paid_overtime)
    staffed_seconds = (paid_regular + paid_overtime) * SECONDS_PER_HOUR
    busy = engine.busy_seconds(None if until_hour is None else until_hour * SECONDS_PER_HOUR)

    hourly = live.assign(hour=(live["arrival"] // SECONDS_PER_HOUR).astype(int))
    hourly_in_time = hourly["start"].notna() & (hourly["wait"] <= threshold_seconds)
    per_hour = hourly_in_time.groupby(hourly["hour"]).mean()
    per_hour_count = hourly.groupby("hour").size()
    understaffed = int(((per_hour < service_level_target) & (per_hour_count >= 3)).sum())

    def mean_or_nan(series: pd.Series) -> float:
        return float(series.mean()) if len(series) else float("nan")

    # Wait of every live customer: until answered, or until they hung up (or the end).
    horizon_end = engine.end_time
    waited_all = np.where(
        live["start"].notna(),
        live["wait"],
        np.minimum(pd.to_numeric(live["abandon_at"], errors="coerce").fillna(horizon_end), horizon_end)
        - live["arrival"],
    )

    return {
        "offered": float(len(scored)),
        "live_offered": float(len(live)),
        "handled": float(len(handled)),
        "service_level": float(in_time.sum() / len(live)) if len(live) else float("nan"),
        "abandon_rate": mean_or_nan(live["abandoned"].astype(float)),
        "asa_seconds": mean_or_nan(answered_live["wait"]),
        "mean_wait_seconds": float(np.mean(waited_all)) if len(live) else float("nan"),
        "p90_wait_seconds": float(answered_live["wait"].quantile(0.9))
        if len(answered_live)
        else float("nan"),
        "backlog_wait_hours": mean_or_nan(backlog["wait"].dropna()) / SECONDS_PER_HOUR
        if backlog["start"].notna().any()
        else float("nan"),
        "aht_seconds": mean_or_nan(handled["handle_seconds"]),
        "occupancy": busy / staffed_seconds if staffed_seconds else float("nan"),
        "idle_share": 1 - busy / staffed_seconds if staffed_seconds else float("nan"),
        "agent_hours": paid_regular + paid_overtime,
        "regular_hours": paid_regular,
        "overtime_hours": paid_overtime,
        "labour_cost_eur": labour_cost,
        "overtime_cost_eur": costs.regular_hourly * costs.overtime_multiplier * paid_overtime,
        "cost_per_contact_eur": labour_cost / len(handled) if len(handled) else float("nan"),
        "abandonment_cost_eur": costs.abandonment_cost * float(live["abandoned"].sum()),
        "total_cost_eur": labour_cost + costs.abandonment_cost * float(live["abandoned"].sum()),
        "understaffed_hours": float(understaffed),
        "unfinished": float((scored["start"].isna() & ~scored["abandoned"]).sum()),
    }
