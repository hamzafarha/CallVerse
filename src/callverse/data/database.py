"""SQLite store of orders, contacts, tickets and chat messages."""

import os
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class TableSpec:
    """Primary key, foreign keys (column, parent table, parent column) and indexes."""

    name: str
    primary_key: list[str]
    foreign_keys: list[tuple[str, str, str]] = field(default_factory=list)
    indexes: list[list[str]] = field(default_factory=list)


# Parents before children, so the load order respects foreign keys.
TABLES = [
    TableSpec("customers", ["customer_id"], indexes=[["customer_unique_id"]]),
    TableSpec("sellers", ["seller_id"]),
    TableSpec("products", ["product_id"]),
    TableSpec(
        "orders",
        ["order_id"],
        [("customer_id", "customers", "customer_id")],
        [["customer_unique_id"], ["order_status"]],
    ),
    TableSpec(
        "order_items",
        ["order_id", "order_item_id"],
        [
            ("order_id", "orders", "order_id"),
            ("product_id", "products", "product_id"),
            ("seller_id", "sellers", "seller_id"),
        ],
        [["product_id"], ["seller_id"]],
    ),
    TableSpec(
        "payments",
        ["order_id", "payment_sequential"],
        [("order_id", "orders", "order_id")],
    ),
    TableSpec(
        "contacts",
        ["contact_id"],
        [("order_id", "orders", "order_id")],
        [["order_id"], ["customer_unique_id"], ["contact_timestamp"]],
    ),
    TableSpec(
        "tickets",
        ["ticket_id"],
        [("contact_id", "contacts", "contact_id"), ("order_id", "orders", "order_id")],
        [["order_id"], ["customer_unique_id"], ["opened_at"], ["outcome"]],
    ),
    TableSpec(
        "chat_messages",
        ["message_id"],
        [("ticket_id", "tickets", "ticket_id")],
        [["ticket_id", "turn"]],
    ),
]

# Order columns useful to look up an order; the rest stay in the analytical Parquet.
ORDER_COLUMNS = [
    "order_id",
    "customer_id",
    "customer_unique_id",
    "order_status",
    "order_purchase_timestamp",
    "order_approved_at",
    "order_delivered_carrier_date",
    "order_delivered_customer_date",
    "order_estimated_delivery_date",
    "latest_shipping_limit_date",
    "customer_city",
    "customer_state",
    "item_count",
    "distinct_sellers",
    "items_price_total",
    "items_freight_total",
    "order_value",
    "payment_count",
    "payment_total",
    "max_installments",
    "uses_voucher",
    "primary_payment_type",
    "primary_category_english",
]


def sqlite_type(dtype: object) -> str:
    """SQLite column type for a pandas dtype (timestamps are stored as ISO text)."""
    if pd.api.types.is_bool_dtype(dtype) or pd.api.types.is_integer_dtype(dtype):
        return "INTEGER"
    if pd.api.types.is_float_dtype(dtype):
        return "REAL"
    return "TEXT"


def create_table_sql(spec: TableSpec, frame: pd.DataFrame) -> str:
    """CREATE TABLE statement with types, NOT NULL keys, primary and foreign keys."""
    lines = []
    for column, dtype in frame.dtypes.items():
        not_null = " NOT NULL" if column in spec.primary_key else ""
        lines.append(f'"{column}" {sqlite_type(dtype)}{not_null}')
    keys = ", ".join(f'"{c}"' for c in spec.primary_key)
    lines.append(f"PRIMARY KEY ({keys})")
    for column, parent, parent_column in spec.foreign_keys:
        lines.append(
            f'FOREIGN KEY ("{column}") REFERENCES "{parent}" ("{parent_column}")'
        )
    body = ",\n    ".join(lines)
    return f'CREATE TABLE "{spec.name}" (\n    {body}\n)'


def build_database(tables: dict[str, pd.DataFrame], path: str | Path) -> dict[str, int]:
    """Write every table of ``TABLES`` to a new SQLite file; returns the row counts.

    The file is built under a temporary name and only replaces ``path`` once every
    table is loaded and the foreign-key check passes.
    """
    missing = [spec.name for spec in TABLES if spec.name not in tables]
    if missing:
        raise ValueError(f"Missing tables: {missing}.")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".building")
    temporary.unlink(missing_ok=True)

    connection = sqlite3.connect(temporary)
    try:
        for spec in TABLES:
            frame = tables[spec.name]
            if frame.duplicated(spec.primary_key).any():
                raise ValueError(f"Duplicate primary keys in table '{spec.name}'.")
            connection.execute(create_table_sql(spec, frame))
            frame.to_sql(spec.name, connection, if_exists="append", index=False)
            for columns in spec.indexes:
                name = f"idx_{spec.name}_{'_'.join(columns)}"
                quoted = ", ".join(f'"{c}"' for c in columns)
                connection.execute(f'CREATE INDEX "{name}" ON "{spec.name}" ({quoted})')
        connection.commit()
        violations = connection.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise ValueError(
                f"{len(violations)} foreign-key violations, e.g. {violations[:3]}."
            )
        counts = {
            spec.name: connection.execute(
                f'SELECT COUNT(*) FROM "{spec.name}"'
            ).fetchone()[0]
            for spec in TABLES
        }
    finally:
        connection.close()
    os.replace(temporary, path)
    return counts


def connect(path: str | Path, read_only: bool = True) -> sqlite3.Connection:
    """Open the store; read-only by default, with foreign keys enforced on writes."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"No database at {path}. Run scripts/build_database.py."
        )
    if read_only:
        connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    else:
        connection = sqlite3.connect(path)
    connection.execute("PRAGMA foreign_keys = ON")
    return connection
