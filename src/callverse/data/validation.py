"""Pandera data contracts for the tables every later layer depends on.

A contract states what downstream code assumes (keys, types, allowed values,
ranges). ``validate_processed_data`` checks all of them after the pipeline, so a
broken notebook is caught before it silently corrupts the forecast or the twin.
"""

from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import pandera.pandas as pa

from callverse.config import PROCESSED_DIR, load_yaml

INTENT_GROUPS = ["wismo", "cancel_refund", "post_delivery", "order_admin"]
ORDER_LINKED_INTENTS = [
    intent
    for intents in load_yaml("data")["generation"]["contacts"]["intent_groups"].values()
    for intent in intents
]
ORDER_STATUSES = [
    "delivered",
    "shipped",
    "canceled",
    "unavailable",
    "invoiced",
    "processing",
    "created",
    "approved",
]

CONTACTS_SCHEMA = pa.DataFrameSchema(
    {
        "contact_id": pa.Column(str, unique=True, checks=pa.Check.str_startswith("SC")),
        "contact_timestamp": pa.Column("datetime64[ns]"),
        "contact_date": pa.Column("datetime64[ns]"),
        "contact_hour": pa.Column(int, pa.Check.in_range(0, 23), coerce=True),
        "intent": pa.Column(str, pa.Check.isin(ORDER_LINKED_INTENTS)),
        "intent_group": pa.Column(str, pa.Check.isin(INTENT_GROUPS)),
        "message_text": pa.Column(str, pa.Check.str_length(min_value=1)),
        "order_id": pa.Column(str),
        "customer_unique_id": pa.Column(str),
        "in_promo_window": pa.Column(bool),
        "is_synthetic": pa.Column(bool, pa.Check.eq(True)),
    },
    checks=[
        pa.Check(
            lambda df: (df["contact_timestamp"].dt.normalize() == df["contact_date"]).all(),
            error="contact_date must be the day of contact_timestamp",
        )
    ],
    strict=False,
    coerce=False,
    name="synthetic_contacts",
)

DAILY_BY_GROUP_SCHEMA = pa.DataFrameSchema(
    {
        "date": pa.Column("datetime64[ns]"),
        "intent_group": pa.Column(str, pa.Check.isin(INTENT_GROUPS)),
        "contacts": pa.Column(int, pa.Check.ge(0), coerce=True),
    },
    unique=["date", "intent_group"],
    checks=[
        pa.Check(
            lambda df: df.groupby("date")["intent_group"].nunique().eq(4).all(),
            error="every day needs a row for each of the 4 intent groups",
        )
    ],
    name="synthetic_contacts_daily_by_group",
)

ORDERS_SCHEMA = pa.DataFrameSchema(
    {
        "order_id": pa.Column(str, unique=True),
        "customer_unique_id": pa.Column(str),
        "order_status": pa.Column(str, pa.Check.isin(ORDER_STATUSES)),
        "order_purchase_timestamp": pa.Column("datetime64[ns]"),
        "order_estimated_delivery_date": pa.Column("datetime64[ns]"),
        "order_delivered_customer_date": pa.Column("datetime64[ns]", nullable=True),
        "order_value": pa.Column(float, pa.Check.ge(0), nullable=True),
        "primary_payment_type": pa.Column(str, nullable=True),
    },
    strict=False,
    name="olist_orders_analytical",
)

CALENDAR_SCHEMA = pa.DataFrameSchema(
    {
        "date": pa.Column("datetime64[ns]", unique=True),
        "is_public_holiday": pa.Column(bool),
        "in_promo_window": pa.Column(bool),
    },
    strict=False,
    name="daily_calendar",
)

TICKETS_SCHEMA = pa.DataFrameSchema(
    {
        "ticket_id": pa.Column(str, unique=True),
        "contact_id": pa.Column(str, unique=True),
        "outcome": pa.Column(str),
        "outcome_class": pa.Column(str, pa.Check.isin(["resolved_in_chat", "follow_up", "escalated"])),
        "handle_seconds": pa.Column(int, pa.Check.gt(0), coerce=True),
        "first_contact_resolution": pa.Column(bool),
        "csat_score": pa.Column("Int64", pa.Check.in_range(1, 5), nullable=True),
    },
    strict=False,
    name="synthetic_tickets",
)

HOUR_PROFILE_SCHEMA = pa.DataFrameSchema(
    {
        "hour": pa.Column(int, pa.Check.in_range(0, 23), unique=True),
        "share": pa.Column(float, pa.Check.in_range(0, 1)),
    },
    checks=[pa.Check(lambda df: abs(df["share"].sum() - 1) < 1e-6, error="shares sum to 1")],
    name="contact_hour_profile",
)

CONTRACTS: dict[str, tuple[str, pa.DataFrameSchema]] = {
    "synthetic_contacts": ("synthetic_contacts.parquet", CONTACTS_SCHEMA),
    "synthetic_contacts_daily_by_group": (
        "synthetic_contacts_daily_by_group.parquet",
        DAILY_BY_GROUP_SCHEMA,
    ),
    "olist_orders_analytical": ("olist_orders_analytical.parquet", ORDERS_SCHEMA),
    "daily_calendar": ("daily_calendar.parquet", CALENDAR_SCHEMA),
    "synthetic_tickets": ("synthetic_tickets.parquet", TICKETS_SCHEMA),
    "contact_hour_profile": ("contact_hour_profile.csv", HOUR_PROFILE_SCHEMA),
}


@dataclass(frozen=True)
class ContractResult:
    """Outcome of one data contract."""

    table: str
    rows: int
    passed: bool
    errors: str = ""


def _read(path: Path) -> pd.DataFrame:
    if path.suffix == ".csv":
        return pd.read_csv(path)
    return pd.read_parquet(path)


def validate_processed_data(processed_dir: Path = PROCESSED_DIR) -> list[ContractResult]:
    """Check every contract; missing files fail their contract."""
    results = []
    for table, (file_name, schema) in CONTRACTS.items():
        path = processed_dir / file_name
        if not path.exists():
            results.append(ContractResult(table, 0, False, f"missing file {file_name}"))
            continue
        frame = _read(path)
        try:
            schema.validate(frame, lazy=True)
            results.append(ContractResult(table, len(frame), True))
        except pa.errors.SchemaErrors as error:
            summary = error.failure_cases[["column", "check"]].drop_duplicates().head(5)
            results.append(ContractResult(table, len(frame), False, summary.to_string(index=False)))
    return results
