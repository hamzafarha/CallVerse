"""Service model protocol defining service duration and interaction dynamics."""

from typing import Any, Protocol


class ServiceModel(Protocol):
    """Protocol defining service duration and execution models."""

    def sample_service_time(self, *args: Any, **kwargs: Any) -> float:
        """Sample or calculate service duration in seconds."""
        ...
