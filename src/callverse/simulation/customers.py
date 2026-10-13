"""Customer entity, patience distribution, and interaction processes."""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from callverse.simulation.scenarios import SimulationConfig
from callverse.simulation.service import LognormalServiceModel

SECONDS_PER_HOUR = 3600
SECONDS_PER_DAY = 24 * SECONDS_PER_HOUR


@dataclass
class Contact:
    """One customer contact flowing through the simulated contact center.

    Times are seconds since the start of the simulation. ``abandon_at`` is None
    when the contact cannot abandon (it arrived while closed, or its patience
    would only run out after closing time; it then waits as backlog).
    """

    contact_id: int
    arrival: float
    intent_group: str
    service_seconds: float
    is_live: bool
    abandon_at: float | None
    start: float | None = None
    end: float | None = None
    abandoned: bool = False


def generate_contacts(
    daily_counts: pd.DataFrame,
    hour_shares: np.ndarray,
    simulation_start: pd.Timestamp,
    config: SimulationConfig,
    service_model: LognormalServiceModel,
    rng: np.random.Generator,
) -> list[Contact]:
    """Draw scaled Poisson arrivals from daily expected contacts per intent group.

    ``daily_counts`` has columns ``date``, ``intent_group`` and ``contacts`` (the
    expected or observed number of contacts that day). Each day and group is
    spread over the 24 hours with ``hour_shares``; within an hour, arrival times
    are uniform. This is a piecewise-constant non-homogeneous Poisson process.
    """
    if not np.isclose(hour_shares.sum(), 1.0) or len(hour_shares) != 24:
        raise ValueError("hour_shares must have 24 values adding up to 1.")

    rows = daily_counts.sort_values(["date", "intent_group"])
    arrivals: list[tuple[float, str]] = []
    for row in rows.itertuples():
        day_offset = (pd.Timestamp(row.date) - simulation_start).days
        if day_offset < 0:
            raise ValueError("daily_counts contains days before the simulation start.")
        hourly_rates = row.contacts * config.scale_factor * hour_shares
        hourly_counts = rng.poisson(hourly_rates)
        for hour, count in enumerate(hourly_counts):
            if count == 0:
                continue
            hour_start = day_offset * SECONDS_PER_DAY + hour * SECONDS_PER_HOUR
            times = hour_start + rng.uniform(0, SECONDS_PER_HOUR, count)
            arrivals.extend((float(time), row.intent_group) for time in times)

    arrivals.sort()
    contacts = []
    for contact_id, (arrival, intent_group) in enumerate(arrivals, start=1):
        hour_of_day = int(arrival % SECONDS_PER_DAY // SECONDS_PER_HOUR)
        is_live = config.is_open(hour_of_day)
        abandon_at = None
        if is_live:
            day_start = arrival - arrival % SECONDS_PER_DAY
            closing_time = day_start + config.close_hour * SECONDS_PER_HOUR
            deadline = arrival + rng.exponential(config.patience_mean_seconds)
            if deadline < closing_time:
                abandon_at = deadline
        service_seconds = float(
            service_model.sample_service_time(intent_group, rng, 1)[0]
        )
        contacts.append(
            Contact(
                contact_id, arrival, intent_group, service_seconds, is_live, abandon_at
            )
        )
    return contacts
