"""Simulation policy protocol, state, and action definitions."""

from dataclasses import dataclass
from typing import Protocol


@dataclass
class State:
    """Simulation state representation."""

    pass


@dataclass
class Action:
    """Simulation action representation."""

    pass


class Policy(Protocol):
    """Protocol for simulation decision policies."""

    def act(self, state: State) -> Action:
        """Select an action given the current simulation state."""
        ...
