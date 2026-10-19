"""Leakage-safe features for daily contact volume per intent group.

Every lag-based feature is at least ``MIN_FEATURE_LAG`` days old, so a model
trained on these features can forecast 1 to 7 days ahead without seeing the
future. Calendar features (weekday, holidays, promo windows) are known in advance.

Ported from notebooks/09_contact_volume_forecasting.ipynb.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

SERIES_START = pd.Timestamp("2017-01-01")
EVAL_END = pd.Timestamp("2018-08-19")  # last day of contact history (a Sunday)
FIRST_ORIGIN = pd.Timestamp("2017-10-01")  # first backtest origin (a Sunday)
TRAIN_START = pd.Timestamp("2017-02-05")  # first day with every lag feature
HORIZON = 7
MIN_FEATURE_LAG = 7
PROMO_GROUP_CODES = {"major_sale": 1, "gift_season": 2}


@dataclass
class FeatureSet:
    """Long feature table (one row per day and group) and its feature columns."""

    panel: pd.DataFrame
    features: list[str]
    groups: list[str]


def contact_series(
    daily_group: pd.DataFrame, start: pd.Timestamp = SERIES_START, end: pd.Timestamp = EVAL_END
) -> pd.DataFrame:
    """Wide table: one column per intent group, one row per day, no gaps."""
    series = daily_group.pivot(index="date", columns="intent_group", values="contacts")
    series = series.sort_index().loc[start:end]
    if series.isna().any().any():
        raise ValueError("The contact series must have no missing values.")
    if len(series) != (series.index[-1] - series.index[0]).days + 1:
        raise ValueError("The contact series must contain every day.")
    return series


def build_date_features(
    daily_activity: pd.DataFrame,
    orders: pd.DataFrame,
    daily_calendar: pd.DataFrame,
    events: pd.DataFrame,
) -> pd.DataFrame:
    """Order drivers (lagged) and calendar features, one row per day."""
    activity = daily_activity.set_index("date")
    calendar = daily_calendar.set_index("date")
    all_days = activity.index
    features = pd.DataFrame(index=all_days)

    # Order drivers: 7-day means ending 7 days before the target day
    for column in [
        "orders_purchased",
        "orders_handed_to_carrier",
        "orders_delivered",
        "late_deliveries",
    ]:
        features[f"{column}_mean7_lag7"] = activity[column].shift(MIN_FEATURE_LAG).rolling(7).mean()

    # Orders promised for day t that were placed at least 7 days before t
    lead_days = (orders["order_estimated_delivery_date"] - orders["purchase_date"]).dt.days
    promised = orders[lead_days >= MIN_FEATURE_LAG]
    per_day = promised.groupby("order_estimated_delivery_date").size()
    features["promised_for_day"] = per_day.reindex(all_days, fill_value=0)
    features["promised_prev3_days"] = features["promised_for_day"].shift(1).rolling(3).sum()

    # Overdue backlog 7 days before: promised in the previous 30 days, not delivered
    estimate = orders["order_estimated_delivery_date"].to_numpy()
    delivered_at = orders["order_delivered_customer_date"].fillna(pd.Timestamp.max).to_numpy()
    purchased_at = orders["order_purchase_timestamp"].to_numpy()
    backlog = []
    for day in all_days:
        value = np.datetime64(day)
        recently_due = (estimate < value) & (estimate >= value - np.timedelta64(30, "D"))
        backlog.append(int((recently_due & (delivered_at > value) & (purchased_at <= value)).sum()))
    features["overdue_backlog_lag7"] = pd.Series(backlog, index=all_days).shift(MIN_FEATURE_LAG)

    # Calendar of the target day (known in advance)
    features["day_of_week"] = all_days.dayofweek
    features["is_weekend"] = (all_days.dayofweek >= 5).astype(int)
    features["is_public_holiday"] = calendar["is_public_holiday"].reindex(all_days).fillna(False).astype(int)
    features["in_promo_window"] = calendar["in_promo_window"].reindex(all_days).fillna(False).astype(int)
    features["promo_group_code"] = (
        calendar["promo_group"].reindex(all_days).map(PROMO_GROUP_CODES).fillna(0).astype(int)
    )
    features["days_to_next_event"] = (
        calendar["days_to_next_event_day"].reindex(all_days).astype("float").fillna(60).clip(upper=60)
    )
    major_days = events.loc[events["event_group"] == "major_sale", "event_day"].sort_values()
    major_days = major_days.to_numpy()
    since = []
    for day in all_days:
        past = major_days[major_days <= np.datetime64(day)]
        since.append((day - pd.Timestamp(past[-1])).days if len(past) else 90)
    features["days_since_major_sale"] = np.clip(since, None, 90)
    return features


def build_panel(series: pd.DataFrame, date_features: pd.DataFrame) -> FeatureSet:
    """Own-history features per group joined with the date features.

    ``series`` may contain future days with missing contacts (for forecasting):
    their lag features still come from observed days because every lag is >= 7.
    """
    groups = list(series.columns)
    parts = []
    for code, group in enumerate(groups):
        values = series[group]
        part = pd.DataFrame(
            {
                "date": series.index,
                "intent_group": group,
                "group_code": code,
                "contacts": values.to_numpy(),
            }
        )
        for lag in [7, 14, 21, 28]:
            part[f"lag_{lag}"] = values.shift(lag).to_numpy()
        part["same_weekday_mean_4"] = part[["lag_7", "lag_14", "lag_21", "lag_28"]].mean(axis=1)
        part["mean7_lag7"] = values.shift(MIN_FEATURE_LAG).rolling(7).mean().to_numpy()
        part["mean28_lag7"] = values.shift(MIN_FEATURE_LAG).rolling(28).mean().to_numpy()
        parts.append(part)
    panel = pd.concat(parts, ignore_index=True)
    panel = panel.merge(date_features, left_on="date", right_index=True, how="left", validate="many_to_one")
    features = [c for c in panel.columns if c not in ["date", "intent_group", "contacts"]]
    return FeatureSet(panel, features, groups)


def leakage_check(feature_set: FeatureSet, series: pd.DataFrame, day: str) -> bool:
    """True when ``lag_7`` on ``day`` equals the observed value 7 days before."""
    group = feature_set.groups[0]
    target = pd.Timestamp(day)
    row = feature_set.panel[
        (feature_set.panel["intent_group"] == group) & (feature_set.panel["date"] == target)
    ]
    expected = series.loc[target - pd.Timedelta(days=7), group]
    return float(row["lag_7"].iloc[0]) == float(expected)
