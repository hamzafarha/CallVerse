"""Discrete-event queueing simulation engine using SimPy."""

from callverse.simulation.customers import Contact, generate_contacts
from callverse.simulation.environment import run_simulation
from callverse.simulation.metrics import contact_kpis, summarize_replications
from callverse.simulation.resources import (
    erlang_c_mean_wait,
    erlang_c_service_level,
    erlang_c_wait_probability,
    plan_hourly_staffing,
    required_agents,
)
from callverse.simulation.scenarios import (
    ServiceTimeSpec,
    SimulationConfig,
    load_simulation_config,
)
from callverse.simulation.service import LognormalServiceModel

__all__ = [
    "Contact",
    "LognormalServiceModel",
    "ServiceTimeSpec",
    "SimulationConfig",
    "contact_kpis",
    "erlang_c_mean_wait",
    "erlang_c_service_level",
    "erlang_c_wait_probability",
    "generate_contacts",
    "load_simulation_config",
    "plan_hourly_staffing",
    "required_agents",
    "run_simulation",
    "summarize_replications",
]
