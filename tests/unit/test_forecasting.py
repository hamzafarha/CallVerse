"""Forecast features (no leakage), metrics and the rolling backtest."""

import numpy as np
import pandas as pd
import pytest

from callverse.forecasting import accuracy, build_panel, run_backtest
from callverse.forecasting.baselines import seasonal_naive, weekday_mean_4w


@pytest.fixture
def series() -> pd.DataFrame:
    rng = np.random.default_rng(0)
    days = pd.date_range("2017-01-01", "2017-06-30")
    weekly = 1 + 0.4 * (days.dayofweek < 2)
    return pd.DataFrame(
        {"wismo": rng.poisson(20 * weekly), "order_admin": rng.poisson(3 * weekly)}, index=days
    ).rename_axis("date")


@pytest.fixture
def date_features(series) -> pd.DataFrame:
    features = pd.DataFrame(index=series.index)
    features["day_of_week"] = series.index.dayofweek
    features["is_weekend"] = (series.index.dayofweek >= 5).astype(int)
    return features


def test_lag_features_are_at_least_seven_days_old(series, date_features):
    fs = build_panel(series, date_features)
    row = fs.panel[(fs.panel["intent_group"] == "wismo") & (fs.panel["date"] == "2017-03-15")]
    assert row["lag_7"].iloc[0] == series.loc["2017-03-08", "wismo"]
    assert row["mean7_lag7"].iloc[0] == pytest.approx(series.loc["2017-03-02":"2017-03-08", "wismo"].mean())


def test_accuracy_metrics():
    table = pd.DataFrame({"forecast": [10.0, 12.0, 8.0], "actual": [10.0, 10.0, 10.0]})
    metrics = accuracy(table)
    assert metrics["wMAPE_percent"] == pytest.approx(4 / 30 * 100)
    assert metrics["bias_percent"] == pytest.approx(0.0)
    assert metrics["RMSE"] == pytest.approx(np.sqrt(8 / 3))


def test_baselines_use_only_the_past(series):
    origin = pd.Timestamp("2017-05-07")
    naive = seasonal_naive(series, origin, "wismo")
    assert list(naive) == list(series.loc["2017-05-01":"2017-05-07", "wismo"])
    assert len(weekday_mean_4w(series, origin, "wismo")) == 7


def test_backtest_beats_nothing_but_runs(series, date_features):
    """Fast models on synthetic data: complete table, no negative forecasts."""
    fs = build_panel(series, date_features)
    origins = pd.date_range("2017-05-07", periods=4, freq="W-SUN")
    calendar = pd.DataFrame(
        {"date": series.index, "is_public_holiday": False, "in_promo_window": False, "promo_group": None}
    )
    import callverse.forecasting.backtest as backtest

    original = backtest.fit_lightgbm
    backtest.fit_lightgbm = lambda fset, train_end: original(fset, train_end, pd.Timestamp("2017-02-05"))
    try:
        result = run_backtest(series, fs, calendar, ["seasonal_naive", "lightgbm"], origins)
    finally:
        backtest.fit_lightgbm = original
    by_group = result.predictions[result.predictions["intent_group"] != "total"]
    assert len(by_group) == 4 * 7 * 2 * 2
    assert (by_group["forecast"] >= 0).all()
    assert set(result.wmape_table().index) == {"wismo", "order_admin", "total"}
