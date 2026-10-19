"""Workforce agent, routing part (DSO1): observation, PPO router, router factory.

Decision: an advisor becomes free and several customers wait. The agent sees the
K oldest waiting customers (slots) and picks one. Each slot describes the customer
(wait so far, problem type, persona, live chat or overnight message) and how fast
*this* advisor is on that problem type. The same observation is used for PPO
training (gym_wrapper) and for evaluation (PPORouter), so they cannot drift apart.
"""

import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from callverse.config import POLICY_DIR, load_yaml
from callverse.simulation import (
    PATIENCE_CLASSES,
    SECONDS_PER_DAY,
    SECONDS_PER_HOUR,
    Agent,
    Contact,
    FifoRouter,
    SkillScoreRouter,
    best_skilled_agent,
)

GROUPS = ["wismo", "cancel_refund", "post_delivery", "order_admin"]
SLOT_FEATURES = 1 + 1 + len(GROUPS) + 2 + len(PATIENCE_CLASSES) + 1
GLOBAL_FEATURES = 7
PPO_MODEL_FILE = "routing_maskable_ppo.zip"
SKILL_WEIGHTS_FILE = "skill_score_weights.json"


def observation_size(slots: int) -> int:
    """Length of the observation vector."""
    return slots * SLOT_FEATURES + GLOBAL_FEATURES


def build_observation(
    engine: Any,
    agent: Agent,
    candidates: list[Contact],
    slots: int,
    mean_handle: dict[str, float],
) -> tuple[np.ndarray, np.ndarray]:
    """Observation vector and action mask for one routing decision."""
    now = engine.env.now
    obs = np.zeros(observation_size(slots), dtype=np.float32)
    mask = np.zeros(slots, dtype=bool)
    for slot, contact in enumerate(candidates[:slots]):
        base = slot * SLOT_FEATURES
        speed = agent.speed.get(contact.intent_group, 1.0)
        values = [1.0, min((now - contact.arrival) / 300.0, 10.0)]
        values += [float(contact.intent_group == g) for g in GROUPS]
        values += [mean_handle.get(contact.intent_group, 240.0) * speed / 600.0, speed]
        values += [float(contact.patience_class == p) for p in PATIENCE_CLASSES]
        values += [float(contact.is_live)]
        obs[base : base + SLOT_FEATURES] = values
        mask[slot] = True
    everyone = engine.agents + engine.overtime_pool
    on_duty = sum(a.on_duty for a in everyone)
    hour = (now % SECONDS_PER_DAY) / SECONDS_PER_HOUR
    live_waiting = sum(c.is_live for c in engine.waiting)
    g = slots * SLOT_FEATURES
    obs[g : g + GLOBAL_FEATURES] = [
        live_waiting / 50.0,
        (len(engine.waiting) - live_waiting) / 100.0,
        len(engine.free) / max(on_duty, 1),
        on_duty / 40.0,
        math.sin(2 * math.pi * hour / 24),
        math.cos(2 * math.pi * hour / 24),
        max(len(candidates) - slots, 0) / 50.0,
    ]
    return obs, mask


class ExternalRouter:
    """Marker router: the RL training loop decides (engine stops at each decision)."""

    name = "external"
    external = True

    def pick_contact(self, agent: Agent, waiting: list[Contact], now: float) -> int:
        raise RuntimeError("External router: decisions come from the RL loop.")

    def pick_agent(self, contact: Contact, free: list[Agent], now: float) -> int:
        return best_skilled_agent(contact, free)


class PPORouter:
    """Trained MaskablePPO policy used as a router (deterministic actions)."""

    name = "ppo"
    external = False

    def __init__(self, model: Any, slots: int, mean_handle: dict[str, float]) -> None:
        self.model = model
        self.slots = slots
        self.mean_handle = mean_handle
        self.engine: Any = None

    def bind(self, engine: Any) -> None:
        self.engine = engine

    def pick_contact(self, agent: Agent, waiting: list[Contact], now: float) -> int:
        obs, mask = build_observation(self.engine, agent, waiting, self.slots, self.mean_handle)
        action, _ = self.model.predict(obs, action_masks=mask, deterministic=True)
        return int(action)

    def pick_agent(self, contact: Contact, free: list[Agent], now: float) -> int:
        return best_skilled_agent(contact, free)


def routing_settings() -> dict[str, Any]:
    """``workforce.routing`` section of ``configs/agents.yaml``."""
    return load_yaml("agents")["workforce"]["routing"]


def load_skill_weights(policy_dir: Path = POLICY_DIR) -> dict[str, float]:
    """Optimized skill-score weights, or the configured defaults."""
    path = policy_dir / SKILL_WEIGHTS_FILE
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))["weights"]
    return dict(load_yaml("agents")["workforce"]["routing"]["skill_score"]["default_weights"])


def ppo_available(policy_dir: Path = POLICY_DIR) -> bool:
    """True when a trained routing policy is on disk."""
    return (policy_dir / PPO_MODEL_FILE).exists()


_ppo_cache: dict[str, Any] = {}


def make_router(kind: str, mean_handle: dict[str, float], policy_dir: Path = POLICY_DIR):
    """Router by name: ``fifo`` (baseline), ``skill_score`` (backup) or ``ppo`` (main)."""
    if kind == "fifo":
        return FifoRouter()
    if kind == "skill_score":
        return SkillScoreRouter(mean_handle, load_skill_weights(policy_dir))
    if kind == "ppo":
        path = policy_dir / PPO_MODEL_FILE
        if not path.exists():
            raise FileNotFoundError(f"{path} not found. Run `callverse train-rl` first.")
        key = str(path)
        if key not in _ppo_cache:
            from sb3_contrib import MaskablePPO

            _ppo_cache[key] = MaskablePPO.load(str(path), device="cpu")
        return PPORouter(_ppo_cache[key], int(routing_settings()["queue_slots"]), mean_handle)
    raise ValueError(f"Unknown router '{kind}' (fifo, skill_score, ppo).")
