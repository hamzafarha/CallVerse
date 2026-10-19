"""Digital-twin engine (version 2): equivalence with version 1, skills, routing, costs."""

import numpy as np
import pandas as pd
import pytest

from callverse.simulation import (
    CallCenterEngine,
    Contact,
    CostModel,
    FifoRouter,
    OvertimeRule,
    SkillScoreRouter,
    build_agent_pool,
    duty_from_counts,
    engine_kpis,
    generate_contacts,
    load_twin_settings,
    run_simulation,
    uniform_agents,
)

GROUPS = ["wismo", "cancel_refund", "post_delivery", "order_admin"]


def week_contacts(daily_counts, hour_shares, seed=0, patience=False):
    settings = load_twin_settings()
    days = pd.date_range("2018-01-01", periods=3)
    return generate_contacts(
        daily_counts[daily_counts["date"].isin(days)],
        hour_shares,
        days[0],
        settings.sim,
        settings.service_model,
        np.random.default_rng(seed),
        patience_mix=settings.patience_mix if patience else None,
    )


def test_engine_reproduces_version_one(daily_counts, hour_shares):
    contacts = week_contacts(daily_counts, hour_shares)
    staffing = np.tile(np.r_[np.zeros(8), np.full(14, 3), np.zeros(2)], 3).astype(int)
    old = run_simulation(contacts, staffing)
    engine = CallCenterEngine(contacts, uniform_agents(3, GROUPS), duty_from_counts(staffing), FifoRouter())
    new = engine.run()
    merged = old.merge(new, on="contact_id", suffixes=("_old", "_new"))
    assert np.allclose(merged["start_old"].fillna(-1), merged["start_new"].fillna(-1))
    assert (merged["abandoned_old"] == merged["abandoned_new"]).all()


def test_specialists_are_faster():
    agents = build_agent_pool(8, {g: 0.25 for g in GROUPS}, 0.75, 1.3, np.random.default_rng(1))
    assert len(agents) == 8
    assert {a.primary_group for a in agents} == set(GROUPS)
    for agent in agents:
        assert agent.speed[agent.primary_group] == 0.75
        assert sorted(agent.speed.values()).count(1.3) == 1


def test_external_router_stepping_matches_fifo(daily_counts, hour_shares):
    """Driving the engine decision by decision with 'always the oldest' equals FIFO."""
    from callverse.agents.workforce.routing import ExternalRouter

    staffing = np.tile(np.r_[np.zeros(8), np.full(14, 2), np.zeros(2)], 3).astype(int)
    contacts = week_contacts(daily_counts, hour_shares, seed=3)
    fifo = CallCenterEngine(
        contacts, uniform_agents(2, GROUPS), duty_from_counts(staffing), FifoRouter()
    ).run()
    contacts = week_contacts(daily_counts, hour_shares, seed=3)
    engine = CallCenterEngine(
        contacts, uniform_agents(2, GROUPS), duty_from_counts(staffing), ExternalRouter(), trace_interval=None
    )
    decisions = 0
    while engine.advance():
        engine.resolve(0)
        decisions += 1
    stepped = engine.records()
    assert decisions > 0
    assert np.allclose(fifo["start"].fillna(-1), stepped["start"].fillna(-1))


def test_overtime_rule_calls_agents_when_queue_is_long():
    contacts = [Contact(i, 8 * 3600 + i, "wismo", 600.0, True, None) for i in range(30)]
    duty = duty_from_counts(np.r_[np.zeros(8), np.full(4, 1)].astype(int))
    pool = build_agent_pool(
        2, {"wismo": 1.0}, 1.0, 1.0, np.random.default_rng(0), overtime=True, first_id=100
    )
    engine = CallCenterEngine(
        contacts,
        uniform_agents(1, ["wismo"]),
        duty,
        FifoRouter(),
        overtime_rule=OvertimeRule(5, 2, 8, 22),
        overtime_pool=pool,
    )
    records = engine.run()
    assert engine.dynamic_overtime_hours.sum() > 0
    assert set(records["agent_id"].dropna()) & {100, 101}
    kpis = engine_kpis(engine, records, 20, 0.8, CostModel(10, 1.5, 5))
    assert kpis["overtime_hours"] == engine.dynamic_overtime_hours.sum()
    assert kpis["labour_cost_eur"] == pytest.approx(
        10 * (kpis["regular_hours"] + 1.5 * kpis["overtime_hours"])
    )


def test_skill_score_router_prefers_short_matching_jobs():
    agents = build_agent_pool(1, {"wismo": 1.0, "post_delivery": 0.0001}, 0.75, 1.3, np.random.default_rng(0))
    agent = agents[0]
    router = SkillScoreRouter(
        {"wismo": 180, "post_delivery": 420}, {"wait": 0.0, "speed": 1.0, "short_job": 1.0, "impatient": 0.0}
    )
    waiting = [Contact(1, 0, "post_delivery", 400, True, None), Contact(2, 1, "wismo", 200, True, None)]
    assert router.pick_contact(agent, waiting, 10) == 1


def test_kpis_are_in_range(daily_counts, hour_shares):
    settings = load_twin_settings()
    contacts = week_contacts(daily_counts, hour_shares, patience=True)
    staffing = np.tile(np.r_[np.zeros(8), np.full(14, 2), np.zeros(2)], 3).astype(int)
    agents = build_agent_pool(2, {g: 0.25 for g in GROUPS}, 0.75, 1.3, np.random.default_rng(0))
    engine = CallCenterEngine(contacts, agents, duty_from_counts(staffing), FifoRouter())
    kpis = engine_kpis(engine, engine.run(), 20, 0.8, settings.costs, evaluation_end=2 * 86400)
    for key in ["service_level", "abandon_rate", "occupancy"]:
        assert 0 <= kpis[key] <= 1
    assert kpis["mean_wait_seconds"] >= 0
    assert kpis["total_cost_eur"] >= kpis["labour_cost_eur"]
