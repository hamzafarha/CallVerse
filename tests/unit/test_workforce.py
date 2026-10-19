"""Workforce agent: CP-SAT planning, baselines, labour rules, RL environment."""

import numpy as np
import pandas as pd
import pytest

from callverse.agents.workforce.scheduling import (
    cpsat_schedule,
    fixed_schedule,
    load_scheduling_rules,
    roster_compliance,
    rule_schedule,
)
from callverse.simulation import load_twin_settings


@pytest.fixture
def requirement() -> np.ndarray:
    need = np.zeros((7, 24), dtype=int)
    for day in range(7):
        need[day, 8:22] = 3
        need[day, 11:14] = 5  # lunch peak
        need[day, 18:21] = 4
    need[5:, 8:22] = 2  # quieter weekend
    return need


def test_cpsat_covers_requirement_and_respects_rules(requirement):
    rules = load_scheduling_rules()
    plan = cpsat_schedule(requirement, rules, 8, 22, 12.0, 1.5)
    assert (plan.regular + plan.overtime >= requirement).all()
    assert all(roster_compliance(plan.roster, rules).values())
    cost = plan.planned_cost(12.0, 1.5)
    assert cost["planned_shortfall_agent_hours"] == 0


def test_cpsat_is_cheaper_than_peak_sized_fixed_schedule(requirement):
    rules = load_scheduling_rules()
    cpsat = cpsat_schedule(requirement, rules, 8, 22, 12.0, 1.5).planned_cost(12.0, 1.5)
    fixed = fixed_schedule(requirement, rules, 8, 22).planned_cost(12.0, 1.5)
    assert cpsat["planned_cost_eur"] < fixed["planned_cost_eur"]


def test_rule_schedule_covers_with_two_templates(requirement):
    plan = rule_schedule(requirement, load_scheduling_rules())
    assert plan.realtime_overtime
    assert (plan.regular[:, 8:22] >= requirement[:, 8:22]).all()


def test_duty_matrices_shapes(requirement):
    rules = load_scheduling_rules()
    plan = cpsat_schedule(requirement, rules, 8, 22, 12.0, 1.5)
    regular, overtime = plan.duty_matrices(drain_days=1)
    assert regular.shape == (plan.headcount, 8 * 24)
    assert regular[:, : 7 * 24].sum() == plan.regular.sum()


def test_routing_env_follows_gymnasium_api(daily_counts, hour_shares):
    from gymnasium.utils.env_checker import check_env

    from callverse.agents.workforce.gym_wrapper import RoutingEnv

    env = RoutingEnv(
        load_twin_settings(),
        daily_counts,
        hour_shares,
        pd.date_range("2018-01-05", periods=20),
        load_range=(1.5, 2.0),
        absence_range=(0.2, 0.3),
        seed=0,
    )
    check_env(env, skip_render_check=True)
    obs, _ = env.reset(seed=1)
    done, steps = False, 0
    while not done and steps < 5000:
        mask = env.action_masks()
        obs, reward, done, _, info = env.step(int(np.flatnonzero(mask)[0]))
        assert reward <= 0
        steps += 1
    assert done and "abandon_rate" in info
