"""Routing policies: who takes which customer (DSO1).

A router is asked two questions by the simulation engine:

- ``pick_contact``: an agent just became free and several customers are waiting;
  which one does the agent take?
- ``pick_agent``: a customer arrives and several agents are free; who takes it?

The baseline (DSO document) is "first come, first served, with skill matching":
the oldest customer first, and the free agent who is fastest on that customer's
problem type. The learned PPO router lives in ``callverse.agents.workforce``.
"""

from dataclasses import dataclass, field
from typing import Protocol

from callverse.simulation.customers import Contact


@dataclass(eq=False)
class Agent:
    """One advisor desk of the simulated center.

    ``speed`` multiplies the handle time per intent group (< 1 means faster).
    """

    agent_id: int
    speed: dict[str, float]
    primary_group: str = ""
    overtime: bool = False
    on_duty: bool = False
    busy: bool = False
    idle_since: float = 0.0
    busy_seconds: float = 0.0
    handled: int = 0
    leave_after_contact: bool = field(default=False, repr=False)


class Router(Protocol):
    """Routing policy plugged into the engine."""

    name: str
    external: bool  # True: decisions are made outside the engine (RL training loop)

    def pick_contact(self, agent: Agent, waiting: list[Contact], now: float) -> int:
        """Index in ``waiting`` (oldest first) of the contact the agent takes."""
        ...

    def pick_agent(self, contact: Contact, free: list[Agent], now: float) -> int:
        """Index in ``free`` of the agent who takes the arriving contact."""
        ...


def best_skilled_agent(contact: Contact, free: list[Agent]) -> int:
    """Fastest free agent for the contact's group; ties go to the longest idle."""
    return min(
        range(len(free)),
        key=lambda i: (free[i].speed.get(contact.intent_group, 1.0), free[i].idle_since),
    )


class FifoRouter:
    """Baseline: oldest customer first, with skill matching on the agent side."""

    name = "fifo"
    external = False

    def pick_contact(self, agent: Agent, waiting: list[Contact], now: float) -> int:
        return 0

    def pick_agent(self, contact: Contact, free: list[Agent], now: float) -> int:
        return best_skilled_agent(contact, free)


@dataclass
class SkillScoreRouter:
    """Backup (DSO1): priority score with tunable weights.

    score = w_wait * wait/60 + w_speed * (1 - speed) * 4
            - w_short_job * expected_handle/300 + w_impatient * is_impatient
    The waiting customer with the highest score is taken.
    """

    mean_handle: dict[str, float]
    weights: dict[str, float] = field(
        default_factory=lambda: {"wait": 1.0, "speed": 1.0, "short_job": 0.5, "impatient": 0.5}
    )
    name: str = "skill_score"
    external: bool = False

    def score(self, agent: Agent, contact: Contact, now: float) -> float:
        speed = agent.speed.get(contact.intent_group, 1.0)
        expected = self.mean_handle.get(contact.intent_group, 240.0) * speed
        w = self.weights
        return (
            w["wait"] * (now - contact.arrival) / 60
            + w["speed"] * (1 - speed) * 4
            - w["short_job"] * expected / 300
            + w["impatient"] * (contact.patience_class == "impatient")
        )

    def pick_contact(self, agent: Agent, waiting: list[Contact], now: float) -> int:
        scores = [self.score(agent, contact, now) for contact in waiting]
        return max(range(len(waiting)), key=scores.__getitem__)

    def pick_agent(self, contact: Contact, free: list[Agent], now: float) -> int:
        return best_skilled_agent(contact, free)
