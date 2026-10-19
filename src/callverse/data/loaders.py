"""Readers for the processed tables used by the forecast, the twin and the API."""

from functools import lru_cache

import numpy as np
import pandas as pd

from callverse.config import PROCESSED_DIR

INTENT_GROUPS = ["wismo", "cancel_refund", "post_delivery", "order_admin"]


@lru_cache(maxsize=1)
def daily_contacts_by_group() -> pd.DataFrame:
    """Observed (synthetic) contacts per day and intent group."""
    return pd.read_parquet(PROCESSED_DIR / "synthetic_contacts_daily_by_group.parquet")


@lru_cache(maxsize=1)
def hour_shares() -> np.ndarray:
    """Share of a day's contacts arriving in each hour (24 values summing to 1)."""
    profile = pd.read_csv(PROCESSED_DIR / "contact_hour_profile.csv").sort_values("hour")
    shares = profile["share"].to_numpy(dtype=float)
    return shares / shares.sum()


@lru_cache(maxsize=1)
def contacts() -> pd.DataFrame:
    """One row per synthetic contact (generator_* columns hold the hidden cause)."""
    return pd.read_parquet(PROCESSED_DIR / "synthetic_contacts.parquet")


@lru_cache(maxsize=1)
def tickets() -> pd.DataFrame:
    """One ticket per contact, with the rule-based outcome and CSAT."""
    return pd.read_parquet(PROCESSED_DIR / "synthetic_tickets.parquet")


@lru_cache(maxsize=1)
def chat_messages() -> pd.DataFrame:
    """Template chat logs of every ticket."""
    return pd.read_parquet(PROCESSED_DIR / "synthetic_chat_messages.parquet")


@lru_cache(maxsize=1)
def daily_calendar() -> pd.DataFrame:
    """Public holidays and promotion windows per day."""
    return pd.read_parquet(PROCESSED_DIR / "daily_calendar.parquet")


@lru_cache(maxsize=1)
def daily_activity() -> pd.DataFrame:
    """Olist order activity per day (purchases, deliveries, late deliveries...)."""
    return pd.read_parquet(PROCESSED_DIR / "olist_daily_activity.parquet")


@lru_cache(maxsize=1)
def orders_analytical() -> pd.DataFrame:
    """One row per Olist order with the engineered features."""
    return pd.read_parquet(PROCESSED_DIR / "olist_orders_analytical.parquet")


@lru_cache(maxsize=1)
def promo_events() -> pd.DataFrame:
    """Retail events of the promotion calendar."""
    return pd.read_csv(
        PROCESSED_DIR / "promo_calendar_events.csv",
        parse_dates=["event_day", "window_start", "window_end"],
    )


def clear_caches() -> None:
    """Forget cached tables (after the data pipeline rewrote them)."""
    for reader in (
        daily_contacts_by_group,
        hour_shares,
        contacts,
        tickets,
        chat_messages,
        daily_calendar,
        daily_activity,
        orders_analytical,
        promo_events,
    ):
        reader.cache_clear()
