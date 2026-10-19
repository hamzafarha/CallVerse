"""Unit tests for the SQLite store (Phase 1F)."""

import sqlite3
from pathlib import Path

import pandas as pd
import pytest

from callverse.data import build_database, connect


def make_tables() -> dict[str, pd.DataFrame]:
    """The smallest consistent set of tables: one order with one chat."""
    return {
        "customers": pd.DataFrame(
            {"customer_id": ["c1"], "customer_unique_id": ["u1"]}
        ),
        "sellers": pd.DataFrame({"seller_id": ["s1"]}),
        "products": pd.DataFrame({"product_id": ["p1"]}),
        "orders": pd.DataFrame(
            {
                "order_id": ["o1"],
                "customer_id": ["c1"],
                "customer_unique_id": ["u1"],
                "order_status": ["delivered"],
                "order_purchase_timestamp": [pd.Timestamp("2017-01-02 10:00:00")],
                "order_value": [99.9],
            }
        ),
        "order_items": pd.DataFrame(
            {
                "order_id": ["o1"],
                "order_item_id": [1],
                "product_id": ["p1"],
                "seller_id": ["s1"],
            }
        ),
        "payments": pd.DataFrame(
            {"order_id": ["o1"], "payment_sequential": [1], "payment_value": [99.9]}
        ),
        "contacts": pd.DataFrame(
            {
                "contact_id": ["SC1"],
                "order_id": ["o1"],
                "customer_unique_id": ["u1"],
                "contact_timestamp": [pd.Timestamp("2017-01-05 09:00:00")],
            }
        ),
        "tickets": pd.DataFrame(
            {
                "ticket_id": ["TK1"],
                "contact_id": ["SC1"],
                "order_id": ["o1"],
                "customer_unique_id": ["u1"],
                "opened_at": [pd.Timestamp("2017-01-05 09:00")],
                "outcome": ["invoice_sent"],
                "first_contact_resolution": [True],
                "csat_score": pd.array([pd.NA], dtype="Int64"),
            }
        ),
        "chat_messages": pd.DataFrame(
            {
                "message_id": ["TK1-01"],
                "ticket_id": ["TK1"],
                "turn": [1],
                "text": ["hello"],
            }
        ),
    }


def test_build_and_query(tmp_path: Path) -> None:
    path = tmp_path / "store.db"
    counts = build_database(make_tables(), path)
    assert counts["orders"] == 1 and counts["chat_messages"] == 1
    assert not path.with_suffix(".building").exists()

    connection = connect(path)
    row = connection.execute(
        "SELECT o.order_purchase_timestamp, t.first_contact_resolution, t.csat_score "
        "FROM tickets t JOIN orders o USING (order_id)"
    ).fetchone()
    assert row == ("2017-01-02 10:00:00", 1, None)
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        connection.execute("DELETE FROM tickets")
    connection.close()


def test_foreign_key_violation_is_rejected(tmp_path: Path) -> None:
    tables = make_tables()
    tables["tickets"].loc[0, "order_id"] = "missing_order"
    with pytest.raises(ValueError, match="foreign-key"):
        build_database(tables, tmp_path / "store.db")
    assert not (tmp_path / "store.db").exists()


def test_duplicate_primary_key_is_rejected(tmp_path: Path) -> None:
    tables = make_tables()
    tables["sellers"] = pd.DataFrame({"seller_id": ["s1", "s1"]})
    with pytest.raises(ValueError, match="Duplicate primary keys"):
        build_database(tables, tmp_path / "store.db")


def test_writable_connection_enforces_foreign_keys(tmp_path: Path) -> None:
    path = tmp_path / "store.db"
    build_database(make_tables(), path)
    connection = connect(path, read_only=False)
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO chat_messages (message_id, ticket_id) VALUES ('x', 'nope')"
        )
    connection.close()
