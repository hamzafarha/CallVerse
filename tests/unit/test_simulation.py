"""Unit tests for the SimPy contact-center simulation (Phase 3)."""

import math

import numpy as np
import pandas as pd
import pytest

from callverse.simulation import (
    Contact,
    LognormalServiceModel,
    ServiceTimeSpec,
    SimulationConfig,
    contact_kpis,
    erlang_c_mean_wait,
    erlang_c_service_level,
    erlang_c_wait_probability,
    generate_contacts,
    required_agents,
    run_simulation,
    summarize_replications,
)


def textbook_erlang_c(agents: int, load: float) -> float:
    """Direct Erlang C formula, written independently of the package code."""
    top = load**agents / math.factorial(agents) * agents / (agents - load)
    bottom = sum(load**k / math.factorial(k) for k in range(agents)) + top
    return top / bottom


def make_config(**overrides: object) -> SimulationConfig:
    settings: dict[str, object] = {
        "random_seed": 1,
        "replications": 3,
        "confidence_level": 0.95,
        "scale_factor": 1.0,
        "open_hour": 8,
        "close_hour": 22,
        "service_level_target": 0.8,
        "service_level_threshold_seconds": 20.0,
        "max_occupancy": 0.9,
        "min_agents": 1,
        "backlog_spread_hours": 2,
        "patience_mean_seconds": 180.0,
        "backlog_abandons": False,
        "service_times": {"wismo": ServiceTimeSpec(180.0, 0.6)},
    }
    settings.update(overrides)
    return SimulationConfig(**settings)  # type: ignore[arg-type]


@pytest.mark.parametrize("agents,load", [(3, 2.0), (6, 4.0), (12, 9.5), (25, 20.0)])
def test_erlang_c_matches_textbook_formula(agents: int, load: float) -> None:
    assert erlang_c_wait_probability(agents, load) == pytest.approx(
        textbook_erlang_c(agents, load), rel=1e-9
    )


def test_erlang_c_unstable_and_empty_cases() -> None:
    assert erlang_c_wait_probability(4, 4.0) == 1.0
    assert erlang_c_wait_probability(4, 0.0) == 0.0
    assert erlang_c_mean_wait(4, 60, 240) == math.inf  # load 4 Erlangs on 4 agents


def test_service_level_increases_with_agents() -> None:
    levels = [erlang_c_service_level(n, 60, 240, 20) for n in range(5, 12)]
    assert all(later > earlier for earlier, later in zip(levels, levels[1:]))


def test_required_agents_is_minimal() -> None:
    agents = required_agents(60, 240, 0.8, 20, 0.9, 1)
    assert erlang_c_service_level(agents, 60, 240, 20) >= 0.8
    assert erlang_c_service_level(agents - 1, 60, 240, 20) < 0.8


def test_simulation_matches_erlang_c() -> None:
    """Constant arrivals, exponential service, no abandonment: M/M/c theory."""
    rng = np.random.default_rng(7)
    rate_per_hour, mean_service, agents, hours = 60, 240.0, 6, 300
    arrivals = np.cumsum(rng.exponential(3600 / rate_per_hour, rate_per_hour * hours))
    arrivals = arrivals[arrivals < (hours - 5) * 3600]
    services = rng.exponential(mean_service, len(arrivals))
    contacts = [
        Contact(i, float(t), "wismo", float(s), True, None)
        for i, (t, s) in enumerate(zip(arrivals, services))
    ]
    records = run_simulation(contacts, np.full(hours, agents))
    steady = records[records["arrival"] > 10 * 3600]  # skip the empty-start warm-up

    expected_wait_probability = erlang_c_wait_probability(agents, 4.0)
    assert (steady["wait"] > 1e-9).mean() == pytest.approx(
        expected_wait_probability, abs=0.04
    )
    assert steady["wait"].mean() == pytest.approx(
        erlang_c_mean_wait(agents, rate_per_hour, mean_service), rel=0.25
    )


def test_generated_contacts_follow_opening_rules() -> None:
    config = make_config(scale_factor=20.0)
    model = LognormalServiceModel(config.service_times)
    daily = pd.DataFrame(
        {
            "date": [pd.Timestamp("2018-01-01")],
            "intent_group": ["wismo"],
            "contacts": [10],
        }
    )
    shares = np.full(24, 1 / 24)
    rng = np.random.default_rng(3)
    start = pd.Timestamp("2018-01-01")
    contacts = generate_contacts(daily, shares, start, config, model, rng)
    assert contacts == sorted(contacts, key=lambda contact: contact.arrival)
    for contact in contacts:
        hour = int(contact.arrival // 3600)
        assert contact.is_live == (8 <= hour < 22)
        if not contact.is_live:
            assert contact.abandon_at is None  # night contacts are backlog
        if contact.abandon_at is not None:
            assert contact.arrival < contact.abandon_at < 22 * 3600


def test_simulation_is_reproducible_and_conserves_contacts() -> None:
    config = make_config(scale_factor=30.0)
    model = LognormalServiceModel(config.service_times)
    daily = pd.DataFrame(
        {
            "date": pd.to_datetime(["2018-01-01", "2018-01-02"]),
            "intent_group": ["wismo", "wismo"],
            "contacts": [12, 15],
        }
    )
    shares = np.full(24, 1 / 24)
    one_day = np.r_[np.zeros(8), np.full(14, 3), np.zeros(2)]  # 3 agents 08:00-22:00
    staffing = np.tile(one_day, 3).astype(int)

    def one_run(seed: int) -> pd.DataFrame:
        rng = np.random.default_rng(seed)
        contacts = generate_contacts(
            daily, shares, pd.Timestamp("2018-01-01"), config, model, rng
        )
        return run_simulation(contacts, staffing)

    first, second = one_run(11), one_run(11)
    pd.testing.assert_frame_equal(first, second)

    answered = first["start"].notna()
    unfinished = first["start"].isna() & ~first["abandoned"]
    outcomes = answered.sum() + first["abandoned"].sum() + unfinished.sum()
    assert int(outcomes) == len(first)
    assert not (answered & first["abandoned"]).any()
    assert (first.loc[answered, "wait"] >= 0).all()
    # Only live contacts (arrived during opening hours) can abandon
    assert (first.loc[first["abandoned"], "is_live"]).all()

    kpis = contact_kpis(first, staffing, 20.0, evaluation_end=2 * 86400)
    assert 0 <= kpis["service_level"] <= 1
    assert 0 <= kpis["occupancy"] <= 1


def test_lognormal_service_mean() -> None:
    model = LognormalServiceModel({"wismo": ServiceTimeSpec(240.0, 0.6)})
    samples = model.sample_service_time("wismo", np.random.default_rng(5), 200_000)
    assert samples.mean() == pytest.approx(240.0, rel=0.01)
    assert samples.std() / samples.mean() == pytest.approx(0.6, rel=0.03)


def test_summarize_replications_interval() -> None:
    runs = pd.DataFrame(
        {"scenario": ["a"] * 4, "replication": range(4), "x": [1, 2, 3, 4]}
    )
    summary = summarize_replications(runs, 0.95, ["scenario"])
    row = summary.iloc[0]
    assert row["mean"] == pytest.approx(2.5)
    assert row["ci_low"] < 2.5 < row["ci_high"]
