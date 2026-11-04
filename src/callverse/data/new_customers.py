"""Brand-new customers, created from the customer portal instead of picked from the history.

Two ways to give the new customer an order:

- ``real``: CallVerse picks a historical contact with the chosen problem and reuses its real Olist order and
  its date. The order really was in that situation that day, so every tool and the rules engine stay truthful.
- ``invented``: the visitor types the order (category, value, dates, how far it got). It is saved as a new
  row of the ``orders`` and ``customers`` tables, so the advisor's tools find it like any other order.

Each new customer is one row of the ``new_customers`` table (contact ids NC000001, NC000002, ...).
`callverse data` rebuilds the store from scratch, which removes them.
"""

# How to read this file: create_with_real_order() and create_with_invented_order() write one customer;
# get/list/delete read or remove them. Every function takes an optional db_path (the tests use a small
# temporary database) and an optional contacts table (the history to pick real orders from).
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from callverse.config import database_path, load_yaml
from callverse.data import loaders
from callverse.data.database import connect

TABLE = "new_customers"
PERSONAS = ("impatient", "normal", "patient")
PAYMENT_TYPES = ("credit_card", "boleto", "debit_card", "voucher")
# How far the invented order got: the final status stored in the orders table.
PROGRESS = ("processing", "shipped", "delivered", "canceled")
CONTACT_HOUR = 14  # the new customer writes at 14:00 (the centre is open from 08:00 to 22:00)

COLUMNS = {
    "contact_id": "TEXT PRIMARY KEY",
    "name": "TEXT NOT NULL",
    "persona": "TEXT NOT NULL",
    "intent": "TEXT NOT NULL",
    "intent_group": "TEXT NOT NULL",
    "message_text": "TEXT NOT NULL",
    "order_id": "TEXT NOT NULL",
    "customer_unique_id": "TEXT NOT NULL",
    "contact_timestamp": "TEXT NOT NULL",
    "generator_situation": "TEXT",
    "order_source": "TEXT NOT NULL",  # real | invented
    "created_at": "TEXT NOT NULL",
}


@dataclass(frozen=True)
class InventedOrder:
    """The order a visitor types in. Dates are days; times are filled in by the code."""

    category: str
    value_brl: float
    items: int
    payment_type: str
    city: str
    state: str
    purchased_at: pd.Timestamp
    estimated_delivery: pd.Timestamp
    progress: str
    shipped_at: pd.Timestamp | None = None
    delivered_at: pd.Timestamp | None = None


def intent_groups() -> dict[str, str]:
    """Intent -> problem group (wismo, cancel_refund, post_delivery, order_admin), from configs/data.yaml."""
    groups = load_yaml("data")["generation"]["contacts"]["intent_groups"]
    return {intent: group for group, intents in groups.items() for intent in intents}


def chat_contacts(contacts: pd.DataFrame | None = None) -> pd.DataFrame:
    """The history usable in chats: no offensive messages (Bitext tag W)."""
    contacts = loaders.contacts() if contacts is None else contacts
    if "bitext_tags" in contacts:
        contacts = contacts[~contacts["bitext_tags"].fillna("").str.contains("W")]
    return contacts


def example_message(intent: str, contacts: pd.DataFrame | None = None, seed: int = 0) -> str:
    """A real customer message (Bitext) for this problem, to start the chat with."""
    pool = chat_contacts(contacts)
    pool = pool[pool["intent"] == intent]
    if pool.empty:
        return "Hello, I have a question about my order."
    return str(pool.sample(1, random_state=seed).iloc[0]["message_text"])


def contact_date_range(contacts: pd.DataFrame | None = None) -> tuple[pd.Timestamp, pd.Timestamp]:
    """First and last day of the history: a new contact must fall inside it (the twin replays those days)."""
    stamps = pd.to_datetime(chat_contacts(contacts)["contact_timestamp"])
    return stamps.min().normalize(), stamps.max().normalize()


# ------------------------------------------------------------------- storage
def _ensure_table(connection: sqlite3.Connection) -> None:
    body = ", ".join(f'"{name}" {kind}' for name, kind in COLUMNS.items())
    connection.execute(f'CREATE TABLE IF NOT EXISTS "{TABLE}" ({body})')


def _next_contact_id(connection: sqlite3.Connection) -> str:
    # NC + 6 digits, one more than the highest id still saved.
    row = connection.execute(f'SELECT MAX(contact_id) FROM "{TABLE}"').fetchone()
    last = int(row[0][2:]) if row and row[0] else 0
    return f"NC{last + 1:06d}"


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')}


def _insert(connection: sqlite3.Connection, table: str, row: dict[str, Any]) -> None:
    """Insert the values whose column exists in the table (the placeholders keep values out of the SQL)."""
    present = _columns(connection, table)
    data = {k: v for k, v in row.items() if k in present}
    names = ", ".join(f'"{k}"' for k in data)
    marks = ", ".join("?" for _ in data)
    connection.execute(f'INSERT INTO "{table}" ({names}) VALUES ({marks})', list(data.values()))


def _save(
    record: dict[str, Any], db_path: Path, extra: list[tuple[str, dict[str, Any]]] = ()
) -> dict[str, Any]:
    """Write the customer (and its invented order rows, parents first) in one transaction."""
    connection = connect(db_path, read_only=False)
    try:
        _ensure_table(connection)
        record = {**record, "contact_id": _next_contact_id(connection)}
        for table, row in extra:
            _insert(connection, table, row)
        _insert(connection, TABLE, record)
        connection.commit()
    finally:
        connection.close()
    return record


def _check_common(name: str, persona: str, intent: str) -> str:
    """Validate the fields both options share; returns the problem group of the intent."""
    if not name.strip():
        raise ValueError("The customer needs a name.")
    if persona not in PERSONAS:
        raise ValueError(f"Unknown persona '{persona}'.")
    group = intent_groups().get(intent)
    if group is None:
        raise ValueError(f"Unknown problem '{intent}'.")
    return group


# ------------------------------------------------------------- the two options
def create_with_real_order(
    name: str,
    persona: str,
    intent: str,
    message: str | None = None,
    seed: int | None = None,
    db_path: Path | None = None,
    contacts: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """New customer on a real order: a historical contact with this problem lends its order and its date."""
    group = _check_common(name, persona, intent)
    pool = chat_contacts(contacts)
    pool = pool[pool["intent"] == intent]
    if pool.empty:
        raise ValueError(f"No real order with the problem '{intent}' in the history.")
    picked = pool.sample(1, random_state=seed).iloc[0]
    record = {
        "name": name.strip(),
        "persona": persona,
        "intent": intent,
        "intent_group": group,
        "message_text": (message or "").strip() or str(picked["message_text"]),
        "order_id": str(picked["order_id"]),
        "customer_unique_id": str(picked["customer_unique_id"]),
        "contact_timestamp": str(pd.Timestamp(picked["contact_timestamp"])),
        "generator_situation": str(picked.get("generator_situation", "") or ""),
        "order_source": "real",
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    return _save(record, Path(db_path or database_path()))


def guess_situation(group: str, order: InventedOrder, contact_at: pd.Timestamp) -> str:
    """The hidden situation of an invented order (what the Client agent is told happened)."""
    late = contact_at.normalize() > order.estimated_delivery.normalize()
    delivered = (
        order.progress == "delivered" and order.delivered_at is not None and order.delivered_at <= contact_at
    )
    if order.progress == "canceled":
        return "canceled_or_unavailable"
    if group == "post_delivery":
        return "post_delivery_problem"
    if group == "order_admin":
        return "invoice_request" if delivered else "change_before_shipping"
    if group == "cancel_refund":
        return "change_before_shipping" if order.progress == "processing" else "canceled_or_unavailable"
    if delivered:
        return (
            "delivered_late"
            if order.delivered_at.normalize() > order.estimated_delivery.normalize()
            else "on_time_tracking_check"
        )
    return "overdue_never_delivered" if late else "on_time_tracking_check"


def check_invented_order(
    order: InventedOrder, contact_at: pd.Timestamp, contacts: pd.DataFrame | None = None
) -> None:
    """Refuse an order whose dates cannot be true (the twin replays real days: dates stay in the history)."""
    first, last = contact_date_range(contacts)
    if not first <= contact_at.normalize() <= last:
        raise ValueError(f"The contact date must be between {first.date()} and {last.date()} (the history).")
    if order.progress not in PROGRESS:
        raise ValueError(f"Unknown order progress '{order.progress}'.")
    if order.payment_type not in PAYMENT_TYPES:
        raise ValueError(f"Unknown payment type '{order.payment_type}'.")
    if not 0 < order.value_brl <= 20000 or not 1 <= order.items <= 20:
        raise ValueError("The order value must be between 0 and 20,000 reais, with 1 to 20 items.")
    if order.purchased_at > contact_at:
        raise ValueError("The customer cannot write before buying: the purchase date must come first.")
    if order.estimated_delivery < order.purchased_at:
        raise ValueError("The estimated delivery cannot be before the purchase.")
    if order.progress in ("shipped", "delivered"):
        if order.shipped_at is None or order.shipped_at < order.purchased_at:
            raise ValueError("A shipped order needs a shipping date after the purchase.")
    if order.progress == "delivered":
        if order.delivered_at is None or order.shipped_at is None or order.delivered_at < order.shipped_at:
            raise ValueError("A delivered order needs a delivery date after the shipping date.")


def create_with_invented_order(
    name: str,
    persona: str,
    intent: str,
    order: InventedOrder,
    contact_at: pd.Timestamp,
    message: str | None = None,
    db_path: Path | None = None,
    contacts: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """New customer on an order the visitor typed: saved in the orders and customers tables too."""
    group = _check_common(name, persona, intent)
    contact_at = pd.Timestamp(contact_at).normalize() + pd.Timedelta(hours=CONTACT_HOUR)
    check_invented_order(order, contact_at, contacts)
    # New ids in the same 32-character style as the Olist ones.
    order_id, customer_id, customer_unique_id = (uuid.uuid4().hex for _ in range(3))
    purchased = order.purchased_at.normalize() + pd.Timedelta(hours=10)

    def stamp(value: pd.Timestamp | None, hours: int = 12) -> str | None:
        return None if value is None else str(pd.Timestamp(value).normalize() + pd.Timedelta(hours=hours))

    shipped = order.progress in ("shipped", "delivered")
    order_row = {
        "order_id": order_id,
        "customer_id": customer_id,
        "customer_unique_id": customer_unique_id,
        "order_status": order.progress,
        "order_purchase_timestamp": str(purchased),
        "order_approved_at": str(purchased + pd.Timedelta(hours=1)),
        "order_delivered_carrier_date": stamp(order.shipped_at) if shipped else None,
        "order_delivered_customer_date": stamp(order.delivered_at, 16)
        if order.progress == "delivered"
        else None,
        "order_estimated_delivery_date": stamp(order.estimated_delivery, 0),
        "latest_shipping_limit_date": str(purchased + pd.Timedelta(days=6)),
        "customer_city": order.city.strip().lower(),
        "customer_state": order.state.strip().upper(),
        "item_count": float(order.items),
        "distinct_sellers": 1.0,
        "items_price_total": float(order.value_brl),
        "items_freight_total": 0.0,
        "order_value": float(order.value_brl),
        "payment_count": 1.0,
        "payment_total": float(order.value_brl),
        "max_installments": 1.0,
        "uses_voucher": int(order.payment_type == "voucher"),
        "primary_payment_type": order.payment_type,
        "primary_category_english": order.category.strip().lower().replace(" ", "_"),
    }
    customer_row = {
        "customer_id": customer_id,
        "customer_unique_id": customer_unique_id,
        "customer_city": order_row["customer_city"],
        "customer_state": order_row["customer_state"],
    }
    record = {
        "name": name.strip(),
        "persona": persona,
        "intent": intent,
        "intent_group": group,
        "message_text": (message or "").strip() or example_message(intent, contacts),
        "order_id": order_id,
        "customer_unique_id": customer_unique_id,
        "contact_timestamp": str(contact_at),
        "generator_situation": guess_situation(group, order, contact_at),
        "order_source": "invented",
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    # Parents first: the customer, then the order that points to it (foreign key), then the new customer.
    return _save(
        record, Path(db_path or database_path()), [("customers", customer_row), ("orders", order_row)]
    )


# -------------------------------------------------------------- read / delete
def _read(query: str, params: tuple, db_path: Path | None) -> list[dict[str, Any]]:
    path = Path(db_path or database_path())
    if not path.exists():
        return []
    connection = connect(path)
    try:
        connection.row_factory = sqlite3.Row
        return [dict(row) for row in connection.execute(query, params)]
    except sqlite3.OperationalError:  # no new customer created yet: the table does not exist
        return []
    finally:
        connection.close()


def get_new_customer(contact_id: str, db_path: Path | None = None) -> dict[str, Any] | None:
    """One new customer, or None."""
    rows = _read(f'SELECT * FROM "{TABLE}" WHERE contact_id = ?', (contact_id,), db_path)
    return rows[0] if rows else None


def list_new_customers(db_path: Path | None = None) -> list[dict[str, Any]]:
    """Every new customer, newest first."""
    return _read(f'SELECT * FROM "{TABLE}" ORDER BY contact_id DESC', (), db_path)


def delete_new_customer(contact_id: str, db_path: Path | None = None) -> bool:
    """Remove a new customer; an invented order (and its customer row) goes with it. Real orders stay."""
    record = get_new_customer(contact_id, db_path)
    if record is None:
        return False
    connection = connect(Path(db_path or database_path()), read_only=False)
    try:
        connection.execute(f'DELETE FROM "{TABLE}" WHERE contact_id = ?', (contact_id,))
        if record["order_source"] == "invented":
            row = connection.execute(
                "SELECT customer_id FROM orders WHERE order_id = ?", (record["order_id"],)
            ).fetchone()
            connection.execute("DELETE FROM orders WHERE order_id = ?", (record["order_id"],))
            if row:
                connection.execute("DELETE FROM customers WHERE customer_id = ?", (row[0],))
        connection.commit()
    finally:
        connection.close()
    return True
