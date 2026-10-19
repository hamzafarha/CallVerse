"""Gymnasium environment: the twin as a practice ground for the routing agent.

One episode = one simulated day of the training period, made busier than planned
(load multiplier) and with random absences, so queues form and routing matters.
No LLM is called: arrivals and handle times are sampled (fast).

- Observation: ``routing.build_observation`` (K slots + global state).
- Action: index of the waiting customer to serve (invalid slots are masked).
- Reward: minus the customer-seconds spent waiting since the last decision,
  minus a penalty per abandonment, divided by a scale. Minimising total waiting
  time is the same as minimising average waiting time (Little's law).
"""

from typing import Any

import gymnasium as gym
import numpy as np
import pandas as pd

from callverse.agents.workforce.routing import (
    ExternalRouter,
    build_observation,
    observation_size,
)
from callverse.simulation import (
    CallCenterEngine,
    TwinSettings,
    apply_absence,
    duty_from_counts,
    hourly_requirements,
    make_agent_pool,
    make_contacts,
    workload_shares,
)


class RoutingEnv(gym.Env):
    """Day-long routing episodes on the SimPy twin (for MaskablePPO)."""

    metadata = {"render_modes": []}

    def __init__(
        self,
        settings: TwinSettings,
        daily_counts: pd.DataFrame,
        hour_shares: np.ndarray,
        days: pd.DatetimeIndex,
        slots: int = 10,
        load_range: tuple[float, float] = (1.0, 1.6),
        absence_range: tuple[float, float] = (0.0, 0.25),
        abandon_penalty_seconds: float = 600.0,
        reward_scale_seconds: float = 600.0,
        backlog_wait_weight: float = 0.1,
        seed: int | None = None,
        group_surge: tuple[float, float] = (1.0, 1.0),
    ) -> None:
        super().__init__()
        self.settings = settings
        self.daily_counts = daily_counts
        self.hour_shares = hour_shares
        self.days = pd.DatetimeIndex(days)
        self.slots = slots
        self.load_range = load_range
        self.absence_range = absence_range
        self.abandon_penalty = abandon_penalty_seconds
        self.reward_scale = reward_scale_seconds
        self.backlog_wait_weight = backlog_wait_weight
        # Extra surge of each problem type on top of the day's load (scenario-like peaks)
        self.group_surge = group_surge
        self.shares = workload_shares(daily_counts, settings)
        self.observation_space = gym.spaces.Box(
            low=-1.0, high=20.0, shape=(observation_size(slots),), dtype=np.float32
        )
        self.action_space = gym.spaces.Discrete(slots)
        self.engine: CallCenterEngine | None = None
        self._mask = np.zeros(slots, dtype=bool)
        self._rng = np.random.default_rng(seed)
        self.episode_info: dict[str, Any] = {}

    def _new_episode(self) -> bool:
        rng = self._rng
        day = pd.Timestamp(self.days[int(rng.integers(len(self.days)))])
        days = pd.DatetimeIndex([day])
        load = float(rng.uniform(*self.load_range))
        absence = float(rng.uniform(*self.absence_range))
        plan = hourly_requirements(self.daily_counts, days, self.settings, self.hour_shares)
        contacts = make_contacts(
            self.daily_counts,
            days,
            self.settings,
            self.hour_shares,
            rng,
            group_multipliers={g: load * float(rng.uniform(*self.group_surge)) for g in self.settings.groups},
        )
        n_agents = int(plan.max(initial=1))
        agents = make_agent_pool(
            n_agents, self.shares, self.settings, seed_offset=int(rng.integers(1_000_000))
        )
        duty = apply_absence(duty_from_counts(plan, n_agents), absence, rng)
        self.engine = CallCenterEngine(
            contacts,
            agents,
            duty,
            ExternalRouter(),
            trace_interval=None,
            backlog_wait_weight=self.backlog_wait_weight,
        )
        self.episode_info = {
            "day": str(day.date()),
            "load": load,
            "absence": absence,
            "contacts": len(contacts),
            "agents": n_agents,
        }
        return self.engine.advance()

    def _observe(self) -> np.ndarray:
        assert self.engine is not None and self.engine.pending is not None
        agent, candidates = self.engine.pending
        obs, self._mask = build_observation(
            self.engine, agent, candidates, self.slots, self.settings.mean_handle
        )
        return obs

    def reset(self, *, seed: int | None = None, options: dict | None = None):
        super().reset(seed=seed)
        if seed is not None:
            self._rng = np.random.default_rng(seed)
        for _ in range(20):  # a quiet day may need no decision at all: draw another
            if self._new_episode():
                return self._observe(), dict(self.episode_info)
        raise RuntimeError("No routing decision in 20 sampled days; raise the load.")

    def step(self, action: int):
        engine = self.engine
        assert engine is not None
        area, abandons = engine.wait_area, engine.abandons
        n_candidates = len(engine.pending[1]) if engine.pending else 0
        engine.resolve(int(action) if action < min(n_candidates, self.slots) else 0)
        has_decision = engine.advance()
        cost = (engine.wait_area - area) + self.abandon_penalty * (engine.abandons - abandons)
        reward = -cost / self.reward_scale
        if has_decision:
            return self._observe(), float(reward), False, False, {}
        self._mask = np.zeros(self.slots, dtype=bool)
        records = engine.records()
        live = records[records["is_live"]]
        info = {
            **self.episode_info,
            "abandon_rate": float(live["abandoned"].mean()) if len(live) else 0.0,
            "asa_seconds": float(live["wait"].dropna().mean()) if live["wait"].notna().any() else 0.0,
        }
        return np.zeros(self.observation_space.shape, dtype=np.float32), float(reward), True, False, info

    def action_masks(self) -> np.ndarray:
        """Valid actions (required by MaskablePPO)."""
        if not self._mask.any():
            mask = np.zeros(self.slots, dtype=bool)
            mask[0] = True
            return mask
        return self._mask.copy()
