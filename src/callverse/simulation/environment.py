"""SimPy simulation environment and execution coordinator."""

from collections.abc import Generator
from typing import Any

import numpy as np
import pandas as pd
import simpy

from callverse.simulation.customers import SECONDS_PER_HOUR, Contact


def _arrival_process(
    env: simpy.Environment, contacts: list[Contact], queue: simpy.Store
) -> Generator[Any, Any, None]:
    """Release each contact into the FIFO queue at its arrival time."""
    for contact in contacts:
        yield env.timeout(contact.arrival - env.now)
        queue.put(contact)
        if contact.abandon_at is not None:
            env.process(_patience_process(env, contact))


def _patience_process(
    env: simpy.Environment, contact: Contact
) -> Generator[Any, Any, None]:
    """Mark the contact as abandoned if no agent has started it by its deadline."""
    assert contact.abandon_at is not None
    yield env.timeout(contact.abandon_at - env.now)
    if contact.start is None:
        contact.abandoned = True


def _agent_process(
    env: simpy.Environment, agent_index: int, staffing: np.ndarray, queue: simpy.Store
) -> Generator[Any, Any, None]:
    """One agent: works while scheduled, takes contacts first-come-first-served.

    The agent is on shift in hour ``h`` when ``agent_index < staffing[h]``. A
    contact already started is always finished, even after the shift ends.
    """
    while True:
        hour = int(env.now // SECONDS_PER_HOUR)
        if hour >= len(staffing):
            return
        next_boundary = (hour + 1) * SECONDS_PER_HOUR
        if agent_index >= staffing[hour]:
            yield env.timeout(next_boundary - env.now)
            continue

        request = queue.get()
        yield request | env.timeout(next_boundary - env.now)
        if not request.triggered:
            request.cancel()  # shift hour ended while waiting for work
            continue
        contact: Contact = request.value
        if contact.abandoned:
            continue  # customer already hung up; take the next one
        contact.start = env.now
        yield env.timeout(contact.service_seconds)
        contact.end = env.now


def run_simulation(contacts: list[Contact], staffing: np.ndarray) -> pd.DataFrame:
    """Simulate the contact center and return one row per contact.

    ``staffing`` gives the number of agents per hour, starting at time 0. The
    simulation stops when the staffing plan ends; contacts not started by then
    are reported as unfinished (``start`` is missing and ``abandoned`` False).
    """
    if any(b.arrival < a.arrival for a, b in zip(contacts, contacts[1:])):
        raise ValueError("Contacts must be sorted by arrival time.")
    for contact in contacts:  # each run starts from fresh contact state
        contact.start, contact.end, contact.abandoned = None, None, False

    env = simpy.Environment()
    queue = simpy.Store(env)
    env.process(_arrival_process(env, contacts, queue))
    for agent_index in range(int(staffing.max(initial=0))):
        env.process(_agent_process(env, agent_index, staffing, queue))
    env.run(until=len(staffing) * SECONDS_PER_HOUR)

    records = pd.DataFrame(
        {
            "contact_id": [c.contact_id for c in contacts],
            "arrival": [c.arrival for c in contacts],
            "intent_group": [c.intent_group for c in contacts],
            "is_live": [c.is_live for c in contacts],
            "service_seconds": [c.service_seconds for c in contacts],
            "abandon_at": [c.abandon_at for c in contacts],
            "start": [c.start for c in contacts],
            "end": [c.end for c in contacts],
            "abandoned": [c.abandoned for c in contacts],
        }
    )
    records["wait"] = records["start"] - records["arrival"]
    return records
