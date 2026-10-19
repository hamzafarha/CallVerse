"""Shared fixtures: synthetic inputs so unit tests never need the real data."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from callverse.config import PROCESSED_DIR, database_path

GROUPS = ["wismo", "cancel_refund", "post_delivery", "order_admin"]

requires_data = pytest.mark.skipif(
    not (PROCESSED_DIR / "synthetic_contacts.parquet").exists() or not database_path().exists(),
    reason="processed data not built (run `callverse data`)",
)


@pytest.fixture
def daily_counts() -> pd.DataFrame:
    """60 days x 4 groups of Poisson daily contacts with a weekly pattern."""
    rng = np.random.default_rng(0)
    days = pd.date_range("2018-01-01", periods=60)
    rows = []
    for day in days:
        for group, base in zip(GROUPS, [12, 3, 5, 2]):
            level = base * (1.3 if day.dayofweek < 2 else 1.0)
            rows.append({"date": day, "intent_group": group, "contacts": int(rng.poisson(level))})
    return pd.DataFrame(rows)


@pytest.fixture
def hour_shares() -> np.ndarray:
    shares = np.ones(24)
    shares[:7] = 0.2
    return shares / shares.sum()


@pytest.fixture
def project_root() -> Path:
    return Path(__file__).resolve().parents[1]
