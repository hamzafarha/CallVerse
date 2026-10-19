"""Rolling-origin backtest of every forecast model, and the final model fit.

Every Sunday from 2017-10-01, each model forecasts the next 7 days using only data
up to that Sunday. Errors are measured per intent group and for the total
(wMAPE, MAE, RMSE, bias). The DSO4 rule: the main model must beat the seasonal
naive baseline ("same day last week").
"""

from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from callverse.forecasting import baselines
from callverse.forecasting.demand_model import (
    fit_lightgbm,
    predict_days,
)
from callverse.forecasting.features import (
    EVAL_END,
    FIRST_ORIGIN,
    HORIZON,
    FeatureSet,
)

ALL_MODELS = ["seasonal_naive", "weekday_mean_4w", "sarima", "prophet", "lightgbm"]
FAST_MODELS = ["seasonal_naive", "weekday_mean_4w", "lightgbm"]


def accuracy(table: pd.DataFrame) -> pd.Series:
    """wMAPE (%), MAE, RMSE and bias (%) of a table with forecast and actual."""
    error = table["forecast"] - table["actual"]
    total = table["actual"].sum()
    return pd.Series(
        {
            "wMAPE_percent": error.abs().sum() / total * 100 if total else np.nan,
            "MAE": error.abs().mean(),
            "RMSE": float(np.sqrt((error**2).mean())),
            "bias_percent": error.sum() / total * 100 if total else np.nan,
        }
    )


@dataclass
class BacktestResult:
    """Predictions of every model, origin, day and level, plus the error tables."""

    predictions: pd.DataFrame
    metrics: pd.DataFrame
    sarima_problems: dict[str, int] = field(default_factory=dict)

    def wmape_table(self) -> pd.DataFrame:
        """wMAPE per level (rows) and model (columns)."""
        return self.metrics.pivot(index="intent_group", columns="model", values="wMAPE_percent")

    def best_models(self) -> pd.Series:
        """Model with the lowest wMAPE at each level."""
        return self.wmape_table().idxmin(axis=1)

    def beats_naive(self, model: str = "lightgbm", level: str = "total") -> float:
        """Relative wMAPE reduction of ``model`` vs the seasonal naive (%, >0 = better)."""
        table = self.wmape_table()
        naive = table.loc[level, "seasonal_naive"]
        return float((naive - table.loc[level, model]) / naive * 100)


def backtest_origins(
    first: pd.Timestamp = FIRST_ORIGIN, last_day: pd.Timestamp = EVAL_END
) -> pd.DatetimeIndex:
    """Weekly Sunday origins whose 7-day horizon ends on or before ``last_day``."""
    return pd.date_range(first, last_day - pd.Timedelta(days=HORIZON), freq="W-SUN")


def run_backtest(
    series: pd.DataFrame,
    feature_set: FeatureSet,
    daily_calendar: pd.DataFrame,
    models: list[str] = ALL_MODELS,
    origins: pd.DatetimeIndex | None = None,
    log: Callable[[str], None] | None = None,
) -> BacktestResult:
    """Forecast every origin with every model and score against the actuals."""
    origins = backtest_origins() if origins is None else origins
    holidays = baselines.prophet_holidays(daily_calendar) if "prophet" in models else None
    problems: dict[str, int] = {}
    rows = []
    for number, origin in enumerate(origins, start=1):
        days = baselines.target_days(origin)
        for group in feature_set.groups:
            per_model: dict[str, np.ndarray] = {}
            if "seasonal_naive" in models:
                per_model["seasonal_naive"] = baselines.seasonal_naive(series, origin, group)
            if "weekday_mean_4w" in models:
                per_model["weekday_mean_4w"] = baselines.weekday_mean_4w(series, origin, group)
            if "sarima" in models:
                per_model["sarima"] = baselines.sarima(series, origin, group, problems)
            if "prophet" in models:
                per_model["prophet"] = baselines.prophet(series, origin, group, holidays)
            for model_name, values in per_model.items():
                for horizon, (day, value) in enumerate(zip(days, values), start=1):
                    rows.append((origin, day, horizon, group, model_name, float(value)))
        if "lightgbm" in models:
            model = fit_lightgbm(feature_set, train_end=origin)
            for row in predict_days(model, feature_set, days).itertuples():
                rows.append(
                    (
                        origin,
                        row.date,
                        (row.date - origin).days,
                        row.intent_group,
                        "lightgbm",
                        float(row.forecast),
                    )
                )
        if log and (number % 10 == 0 or number == len(origins)):
            log(f"  backtest origin {number}/{len(origins)} ({origin.date()})")

    predictions = pd.DataFrame(
        rows, columns=["origin", "date", "horizon", "intent_group", "model", "forecast"]
    )
    actuals = series.rename_axis(index="date", columns="intent_group").stack().rename("actual").reset_index()
    predictions = predictions.merge(actuals, on=["date", "intent_group"], how="left", validate="many_to_one")
    total = predictions.groupby(["origin", "date", "horizon", "model"], as_index=False)[
        ["forecast", "actual"]
    ].sum()
    total["intent_group"] = "total"
    all_levels = pd.concat([predictions, total], ignore_index=True)
    metrics = (
        all_levels.groupby(["intent_group", "model"])
        .apply(accuracy, include_groups=False)
        .round(3)
        .reset_index()
    )
    return BacktestResult(all_levels, metrics, problems)


def integrity_checks(result: BacktestResult, n_groups: int, n_models: int) -> pd.DataFrame:
    """Sanity checks of the backtest table (shown in the report)."""
    by_group = result.predictions[result.predictions["intent_group"] != "total"]
    n_origins = by_group["origin"].nunique()
    checks = [
        (
            "One forecast per origin, day, group and model",
            len(by_group) == n_origins * HORIZON * n_groups * n_models
            and not by_group.duplicated(["origin", "date", "intent_group", "model"]).any(),
        ),
        ("No missing forecast or actual", not by_group[["forecast", "actual"]].isna().any().any()),
        ("No negative forecast", bool((by_group["forecast"] >= 0).all())),
        (
            "Every target day within 1-7 days of its origin",
            bool(by_group["horizon"].between(1, HORIZON).all()),
        ),
    ]
    return pd.DataFrame(checks, columns=["check", "passed"])
