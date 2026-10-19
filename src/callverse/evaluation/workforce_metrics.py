"""Workforce agent metrics (DSO1 training, DSO3 labour-rule compliance)."""

from typing import Any

import pandas as pd

from callverse.agents.workforce.scheduling import load_scheduling_rules, roster_compliance
from callverse.config import EVALUATION_DIR


def routing_training_curve(window: int = 50) -> pd.DataFrame:
    """PPO episode rewards with a rolling mean (learning curve)."""
    path = EVALUATION_DIR / "routing_ppo_training_curve.csv"
    if not path.exists():
        return pd.DataFrame()
    curve = pd.read_csv(path)
    curve["reward_rolling"] = curve["reward"].rolling(window, min_periods=1).mean()
    return curve


def schedule_compliance(plan: Any) -> dict[str, bool]:
    """Labour-rule checks of a CP-SAT roster (max days, max hours, rest, 1 shift/day)."""
    return roster_compliance(plan.roster, load_scheduling_rules())
