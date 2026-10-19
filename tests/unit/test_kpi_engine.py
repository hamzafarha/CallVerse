"""KPI engine statistics and judge-agreement metrics."""

import numpy as np
import pandas as pd
import pytest

from callverse.agents.quality.reviewer import QualityReviewer, lexicon_sentiment
from callverse.agents.quality.validation import agreement
from callverse.evaluation.business_kpis import mean_ci, paired_difference, summarize_runs


def test_mean_ci_contains_mean():
    stats = mean_ci(pd.Series([1.0, 2.0, 3.0, 4.0]))
    assert stats["mean"] == 2.5
    assert stats["ci_low"] < 2.5 < stats["ci_high"]


def test_paired_difference_detects_a_real_gain():
    runs = pd.DataFrame(
        {
            "router": ["fifo"] * 5 + ["ppo"] * 5,
            "seed": list(range(5)) * 2,
            "mean_wait_seconds": [30, 32, 31, 29, 33, 25, 27, 26, 24, 28],
        }
    )
    diff = paired_difference(runs, "router", "fifo", ["mean_wait_seconds"], ["seed"]).iloc[0]
    assert diff["difference"] == pytest.approx(-5)
    assert diff["significant"]


def test_summarize_runs_long_table():
    runs = pd.DataFrame({"plan": ["a", "a", "b", "b"], "service_level": [0.8, 0.9, 0.7, 0.75]})
    table = summarize_runs(runs, ["plan"], ["service_level"])
    assert list(table["plan"]) == ["a", "b"]


def test_quadratic_kappa_perfect_and_chance():
    perfect = agreement(pd.Series([1, 2, 3, 4, 5]), pd.Series([1, 2, 3, 4, 5]))
    assert perfect["quadratic_kappa"] == pytest.approx(1.0)
    rng = np.random.default_rng(0)
    noise = agreement(pd.Series(rng.integers(1, 6, 500)), pd.Series(rng.integers(1, 6, 500)))
    assert abs(noise["quadratic_kappa"]) < 0.15


def test_rule_reviewer_rewards_a_compliant_answer():
    messages = [
        {"speaker": "customer", "text": "where is my order"},
        {"speaker": "advisor", "text": "Could you give me your order number and e-mail?"},
        {"speaker": "customer", "text": "abc"},
        {"speaker": "advisor", "text": "Your order is with the carrier."},
        {"speaker": "customer", "text": "Great, thanks!"},
    ]
    meta = {
        "sources": ["order_status_and_tracking__s02"],
        "tools": [{"name": "lookup_order", "ok": True}],
        "outcome": "tracking_shared",
    }
    card = QualityReviewer(None, "rules").review(
        messages, {"outcome": "tracking_shared", "kb_chunk_id": "order_status_and_tracking__s02"}, meta
    )
    assert card.correct is True
    assert card.scores["compliance"] == 5
    assert lexicon_sentiment("This is unacceptable, I want a supervisor!") < 3
