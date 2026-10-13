"""Service model protocol defining service duration and interaction dynamics."""

import math
from typing import Any, Protocol

import numpy as np

from callverse.simulation.scenarios import ServiceTimeSpec


class ServiceModel(Protocol):
    """Protocol defining service duration and execution models."""

    def sample_service_time(self, *args: Any, **kwargs: Any) -> float:
        """Sample or calculate service duration in seconds."""
        ...


class LognormalServiceModel:
    """Lognormal handle times per intent group, given by mean and CV."""

    def __init__(self, specs: dict[str, ServiceTimeSpec]) -> None:
        self.specs = specs

    def mean_seconds(self, intent_group: str) -> float:
        """Mean handle time of an intent group."""
        return self.specs[intent_group].mean_seconds

    def sample_service_time(
        self, intent_group: str, rng: np.random.Generator, size: int = 1
    ) -> np.ndarray:
        """Draw ``size`` handle times (seconds) for an intent group."""
        spec = self.specs[intent_group]
        sigma_squared = math.log(1 + spec.cv**2)
        mu = math.log(spec.mean_seconds) - sigma_squared / 2
        return rng.lognormal(mu, math.sqrt(sigma_squared), size)
