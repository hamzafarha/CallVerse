"""Baseline forecasts the main model must beat (DSO4 rule: "same day last week").

All functions return 7 non-negative values for the 7 days after ``origin``.
"""

import logging
import warnings

import numpy as np
import pandas as pd

from callverse.forecasting.features import HORIZON


def target_days(origin: pd.Timestamp, horizon: int = HORIZON) -> pd.DatetimeIndex:
    """The ``horizon`` days after the forecast origin."""
    return pd.date_range(origin + pd.Timedelta(days=1), periods=horizon)


def seasonal_naive(series: pd.DataFrame, origin: pd.Timestamp, group: str) -> np.ndarray:
    """Same day last week (the naive baseline of the DSO document)."""
    days = target_days(origin)
    return series.loc[days - pd.Timedelta(days=7), group].to_numpy(dtype=float)


def weekday_mean_4w(series: pd.DataFrame, origin: pd.Timestamp, group: str) -> np.ndarray:
    """Mean of the same weekday over the last 4 weeks."""
    days = target_days(origin)
    past = [series.loc[days - pd.Timedelta(days=7 * k), group].to_numpy(dtype=float) for k in range(1, 5)]
    return np.mean(past, axis=0)


def sarima(
    series: pd.DataFrame, origin: pd.Timestamp, group: str, problems: dict[str, int] | None = None
) -> np.ndarray:
    """SARIMA(1,1,1)(0,1,1,7) on the history up to the origin.

    Falls back to the seasonal naive forecast if the fit fails (counted in ``problems``).
    """
    from statsmodels.tsa.statespace.sarimax import SARIMAX

    problems = problems if problems is not None else {}
    history = series.loc[:origin, group].astype(float)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            model = SARIMAX(
                history.to_numpy(),
                order=(1, 1, 1),
                seasonal_order=(0, 1, 1, 7),
                enforce_stationarity=False,
                enforce_invertibility=False,
            )
            forecast = model.fit(disp=False, maxiter=200).forecast(HORIZON)
        except Exception:
            problems["failed"] = problems.get("failed", 0) + 1
            return seasonal_naive(series, origin, group)
    if any("converge" in str(w.message).lower() for w in caught):
        problems["not_converged"] = problems.get("not_converged", 0) + 1
    return np.clip(forecast, 0, None)


def prophet_holidays(daily_calendar: pd.DataFrame) -> pd.DataFrame:
    """Public holidays and promo windows as Prophet holiday rows."""
    rows = []
    for row in daily_calendar.itertuples():
        if row.is_public_holiday:
            rows.append({"ds": row.date, "holiday": "public_holiday"})
        if row.in_promo_window:
            rows.append({"ds": row.date, "holiday": str(row.promo_group)})
    return pd.DataFrame(rows)


def prophet(series: pd.DataFrame, origin: pd.Timestamp, group: str, holidays: pd.DataFrame) -> np.ndarray:
    """Prophet with weekly seasonality and the holiday/promo calendar."""
    from prophet import Prophet

    logging.getLogger("prophet").setLevel(logging.WARNING)
    logging.getLogger("cmdstanpy").setLevel(logging.WARNING)
    history = pd.DataFrame({"ds": series.loc[:origin].index, "y": series.loc[:origin, group].to_numpy()})
    model = Prophet(
        weekly_seasonality=True,
        yearly_seasonality=False,
        daily_seasonality=False,
        holidays=holidays,
    )
    model.fit(history)
    future = pd.DataFrame({"ds": target_days(origin)})
    return np.clip(model.predict(future)["yhat"].to_numpy(), 0, None)
