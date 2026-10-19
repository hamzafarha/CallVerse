"""Forecast products used by the twin: weekly plans and the next-week forecast."""

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from callverse.config import FORECAST_DIR
from callverse.forecasting.demand_model import fit_lightgbm, predict_days
from callverse.forecasting.features import (
    EVAL_END,
    HORIZON,
    build_date_features,
    build_panel,
    contact_series,
)

BACKTEST_FILE = "contact_forecast_backtest_predictions.parquet"
METRICS_FILE = "contact_forecast_backtest_metrics.csv"
MODEL_FILE = "lightgbm_contact_forecast.txt"
NEXT_WEEK_FILE = "contact_forecast_next_week.csv"


@dataclass(frozen=True)
class ForecastInputs:
    """Processed tables the forecast needs."""

    daily_group: pd.DataFrame
    daily_activity: pd.DataFrame
    orders: pd.DataFrame
    daily_calendar: pd.DataFrame
    events: pd.DataFrame


def load_backtest(forecast_dir: Path = FORECAST_DIR) -> pd.DataFrame:
    """Saved backtest predictions (all models and levels)."""
    path = forecast_dir / BACKTEST_FILE
    if not path.exists():
        raise FileNotFoundError(f"{path} not found. Run `callverse forecast` first.")
    return pd.read_parquet(path)


def weekly_forecast(
    week_start: pd.Timestamp,
    days: int = 7,
    model: str = "lightgbm",
    forecast_dir: Path = FORECAST_DIR,
) -> pd.DataFrame:
    """Out-of-sample forecast of a week (from the backtest: origin = the Sunday before).

    Returns ``date, intent_group, contacts`` for ``days`` days. Days beyond the
    first 7 are taken from the next origin, so each day is still forecast 1-7 days
    ahead.
    """
    backtest = load_backtest(forecast_dir)
    rows = backtest[(backtest["model"] == model) & (backtest["intent_group"] != "total")]
    wanted = pd.date_range(week_start, periods=days)
    picked = []
    for day in wanted:
        origin = day - pd.Timedelta(days=((day.dayofweek + 1) % 7) or 7)
        part = rows[(rows["date"] == day) & (rows["origin"] == origin)]
        if part.empty:
            raise ValueError(f"No backtest forecast for {day.date()} (origin {origin.date()}).")
        picked.append(part)
    result = pd.concat(picked)[["date", "intent_group", "forecast"]]
    return result.rename(columns={"forecast": "contacts"}).reset_index(drop=True)


def forecast_next_week(inputs: ForecastInputs, origin: pd.Timestamp = EVAL_END) -> pd.DataFrame:
    """Train on all history up to ``origin`` and forecast the 7 following days."""
    series = contact_series(inputs.daily_group, end=origin)
    future_days = pd.date_range(origin + pd.Timedelta(days=1), periods=HORIZON)
    extended = series.reindex(series.index.append(future_days))
    date_features = build_date_features(
        inputs.daily_activity, inputs.orders, inputs.daily_calendar, inputs.events
    )
    feature_set = build_panel(extended, date_features)
    model = fit_lightgbm(feature_set, train_end=origin)
    result = predict_days(model, feature_set, future_days)
    return result.rename(columns={"forecast": "contacts"})
