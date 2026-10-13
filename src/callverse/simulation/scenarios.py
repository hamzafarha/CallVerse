"""Simulation scenario definitions for normal, surge, and degraded states."""

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class ServiceTimeSpec:
    """Handle-time distribution parameters of one intent group."""

    mean_seconds: float
    cv: float


@dataclass(frozen=True)
class SimulationConfig:
    """All simulation assumptions, loaded from ``configs/simulation.yaml``."""

    random_seed: int
    replications: int
    confidence_level: float
    scale_factor: float
    open_hour: int
    close_hour: int
    service_level_target: float
    service_level_threshold_seconds: float
    max_occupancy: float
    min_agents: int
    backlog_spread_hours: int
    patience_mean_seconds: float
    backlog_abandons: bool
    service_times: dict[str, ServiceTimeSpec]

    def is_open(self, hour_of_day: int) -> bool:
        """Return True when the contact center is open at this hour of the day."""
        return self.open_hour <= hour_of_day < self.close_hour


def load_simulation_config(path: str | Path) -> SimulationConfig:
    """Read the simulation assumptions from a YAML file."""
    with open(path, encoding="utf-8") as config_file:
        raw = yaml.safe_load(config_file)

    hours = raw["resources"]["opening_hours"]
    staffing = raw["resources"]["staffing"]
    service = raw["service"]["by_intent_group"]
    config = SimulationConfig(
        random_seed=int(raw["engine"]["random_seed"]),
        replications=int(raw["engine"]["replications"]),
        confidence_level=float(raw["engine"]["confidence_level"]),
        scale_factor=float(raw["volume"]["scale_factor"]),
        open_hour=int(hours["open_hour"]),
        close_hour=int(hours["close_hour"]),
        service_level_target=float(staffing["service_level_target"]),
        service_level_threshold_seconds=float(
            staffing["service_level_threshold_seconds"]
        ),
        max_occupancy=float(staffing["max_occupancy"]),
        min_agents=int(staffing["min_agents"]),
        backlog_spread_hours=int(staffing["backlog_spread_hours"]),
        patience_mean_seconds=float(raw["queues"]["patience_mean_seconds"]),
        backlog_abandons=bool(raw["queues"]["backlog_abandons"]),
        service_times={
            group: ServiceTimeSpec(float(spec["mean_seconds"]), float(spec["cv"]))
            for group, spec in service.items()
        },
    )
    if not 0 <= config.open_hour < config.close_hour <= 24:
        raise ValueError("Opening hours must satisfy 0 <= open < close <= 24.")
    if config.backlog_abandons:
        raise ValueError("Version 1 supports only backlog_abandons: false.")
    return config
