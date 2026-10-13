"""Agent desks, skill tiers, and resource allocation models.

Version 1 sizes one agent pool per hour with the Erlang C formula.
"""

import math

import numpy as np


def erlang_c_wait_probability(agents: int, offered_load: float) -> float:
    """Probability that a contact has to wait (Erlang C).

    ``offered_load`` is the traffic in Erlangs: arrival rate x mean handle time.
    Uses the numerically stable Erlang B recursion.
    """
    if offered_load <= 0:
        return 0.0
    if agents <= offered_load:
        return 1.0  # unstable queue: every contact waits
    erlang_b = 1.0
    for servers in range(1, agents + 1):
        erlang_b = offered_load * erlang_b / (servers + offered_load * erlang_b)
    return agents * erlang_b / (agents - offered_load * (1 - erlang_b))


def erlang_c_service_level(
    agents: int,
    arrivals_per_hour: float,
    mean_service_seconds: float,
    threshold_seconds: float,
) -> float:
    """Share of contacts answered within ``threshold_seconds`` (Erlang C)."""
    offered_load = arrivals_per_hour * mean_service_seconds / 3600
    if offered_load <= 0:
        return 1.0
    if agents <= offered_load:
        return 0.0
    wait_probability = erlang_c_wait_probability(agents, offered_load)
    decay = (agents - offered_load) * threshold_seconds / mean_service_seconds
    return 1 - wait_probability * math.exp(-decay)


def erlang_c_mean_wait(
    agents: int, arrivals_per_hour: float, mean_service_seconds: float
) -> float:
    """Average waiting time in seconds over all contacts (Erlang C)."""
    offered_load = arrivals_per_hour * mean_service_seconds / 3600
    if offered_load <= 0:
        return 0.0
    if agents <= offered_load:
        return math.inf
    wait_probability = erlang_c_wait_probability(agents, offered_load)
    return wait_probability * mean_service_seconds / (agents - offered_load)


def required_agents(
    arrivals_per_hour: float,
    mean_service_seconds: float,
    service_level_target: float,
    threshold_seconds: float,
    max_occupancy: float,
    min_agents: int,
) -> int:
    """Smallest number of agents meeting the service level and occupancy limits."""
    offered_load = arrivals_per_hour * mean_service_seconds / 3600
    agents = max(min_agents, math.ceil(offered_load / max_occupancy))
    while (
        erlang_c_service_level(
            agents, arrivals_per_hour, mean_service_seconds, threshold_seconds
        )
        < service_level_target
    ):
        agents += 1
    return agents


def plan_hourly_staffing(
    arrivals_per_hour: np.ndarray,
    mean_service_seconds: np.ndarray,
    open_mask: np.ndarray,
    service_level_target: float,
    threshold_seconds: float,
    max_occupancy: float,
    min_agents: int,
) -> np.ndarray:
    """Agents per hour: Erlang C sizing when open, zero when closed.

    All arrays have one value per hour of the simulated horizon.
    """
    plan = np.zeros(len(arrivals_per_hour), dtype=int)
    for hour, is_open in enumerate(open_mask):
        if is_open:
            plan[hour] = required_agents(
                float(arrivals_per_hour[hour]),
                float(mean_service_seconds[hour]),
                service_level_target,
                threshold_seconds,
                max_occupancy,
                min_agents,
            )
    return plan
