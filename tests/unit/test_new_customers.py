"""Brand-new customers created on the portal (data/new_customers.py)."""
# Tests data/new_customers.py and the profile lookup on a tiny temporary store: real data is never touched.

from pathlib import Path

import pandas as pd
import pytest

from callverse.agents.advisor.tools import AdvisorTools
from callverse.agents.client.profiles import profile_from_record
from callverse.data import build_database
from callverse.data import new_customers as nc
from callverse.data.database import ORDER_COLUMNS

T = pd.Timestamp


def make_store(tmp_path: Path) -> Path:
    """A store with one real order (o1, shipped on 2018-05-03, due 2018-05-15)."""
    order = {column: None for column in ORDER_COLUMNS}
    order.update(
        order_id="o1", customer_id="c1", customer_unique_id="u1", order_status="shipped",
        order_purchase_timestamp=T("2018-05-01 10:00"), order_approved_at=T("2018-05-01 11:00"),
        order_delivered_carrier_date=T("2018-05-03 12:00"), order_delivered_customer_date=pd.NaT,
        order_estimated_delivery_date=T("2018-05-15"), latest_shipping_limit_date=T("2018-05-07"),
        customer_city="sao paulo", customer_state="SP", item_count=1.0, distinct_sellers=1.0,
        items_price_total=50.0, items_freight_total=10.0, order_value=60.0, payment_count=1.0,
        payment_total=60.0, max_installments=1.0, uses_voucher=0, primary_payment_type="credit_card",
        primary_category_english="toys",
    )  # fmt: skip
    tables = {
        "customers": pd.DataFrame(
            {
                "customer_id": ["c1"],
                "customer_unique_id": ["u1"],
                "customer_zip_code_prefix": ["01000"],
                "customer_city": ["sao paulo"],
                "customer_state": ["SP"],
            }
        ),  # fmt: skip
        "sellers": pd.DataFrame({"seller_id": ["s1"]}),
        "products": pd.DataFrame({"product_id": ["p1"]}),
        "orders": pd.DataFrame([order]),
        "order_items": pd.DataFrame(
            {"order_id": ["o1"], "order_item_id": [1], "product_id": ["p1"], "seller_id": ["s1"]}
        ),
        "payments": pd.DataFrame({"order_id": ["o1"], "payment_sequential": [1], "payment_value": [60.0]}),
        "contacts": pd.DataFrame(
            {
                "contact_id": ["SC1"],
                "order_id": ["o1"],
                "customer_unique_id": ["u1"],
                "contact_timestamp": [T("2018-05-20 09:00")],
            }
        ),
        "tickets": pd.DataFrame(
            {
                "ticket_id": ["TK1"],
                "contact_id": ["SC1"],
                "order_id": ["o1"],
                "customer_unique_id": ["u1"],
                "opened_at": [T("2018-05-20 09:00")],
                "outcome": ["carrier_investigation"],
            }
        ),  # fmt: skip
        "chat_messages": pd.DataFrame(
            {"message_id": ["TK1-01"], "ticket_id": ["TK1"], "turn": [1], "text": ["hi"]}
        ),
    }
    path = tmp_path / "store.db"
    build_database(tables, path)
    return path


@pytest.fixture
def history() -> pd.DataFrame:
    """The history the real orders are picked from: one late-parcel contact (order o1)."""
    return pd.DataFrame(
        {
            "contact_id": ["SC1"],
            "order_id": ["o1"],
            "customer_unique_id": ["u1"],
            "contact_timestamp": [T("2018-05-20 09:00")],
            "intent": ["track_order"],
            "intent_group": ["wismo"],
            "message_text": ["Where is my order?"],
            "generator_situation": ["overdue_never_delivered"],
            "bitext_tags": [""],
        }
    )


def invented(**changes) -> nc.InventedOrder:
    """A typed order: shipped on 2018-05-03, due on 2018-05-10, never delivered."""
    fields = dict(
        category="toys", value_brl=120.0, items=2, payment_type="boleto", city="Recife", state="pe",
        purchased_at=T("2018-05-01"), estimated_delivery=T("2018-05-10"), progress="shipped",
        shipped_at=T("2018-05-03"), delivered_at=None,
    )  # fmt: skip
    fields.update(changes)
    return nc.InventedOrder(**fields)


def test_real_order_customer_reuses_a_historical_order_and_its_date(tmp_path, history):
    """Option "real order": the new customer gets the order and the day of a contact with that problem."""
    db = make_store(tmp_path)
    first = nc.create_with_real_order(
        "Amira B.", "patient", "track_order", None, seed=0, db_path=db, contacts=history
    )
    second = nc.create_with_real_order(
        "Youssef K.", "normal", "track_order", "Hi!", seed=0, db_path=db, contacts=history
    )
    assert (first["contact_id"], second["contact_id"]) == ("NC000001", "NC000002")
    assert first["order_id"] == "o1" and first["contact_timestamp"].startswith("2018-05-20")
    assert first["message_text"] == "Where is my order?" and second["message_text"] == "Hi!"
    assert [r["contact_id"] for r in nc.list_new_customers(db)] == ["NC000002", "NC000001"]
    with pytest.raises(ValueError):
        nc.create_with_real_order("Sara", "normal", "request_invoice", db_path=db, contacts=history)


def test_invented_order_is_saved_and_the_tools_read_it_like_any_order(tmp_path, history):
    """Option "invent my order": the order is a real row of the store, seen as of the contact day."""
    db = make_store(tmp_path)
    record = nc.create_with_invented_order(
        "Lina M.", "impatient", "track_order", invented(), T("2018-05-20"), db_path=db, contacts=history
    )
    assert record["order_source"] == "invented" and record["generator_situation"] == "overdue_never_delivered"
    facts = AdvisorTools(as_of=T(record["contact_timestamp"]), db_path=db).order_facts(record["order_id"])
    assert facts["order_status_at_contact"] == "shipped"
    assert facts["days_past_estimate"] == 10 and bool(facts["needs_investigation"])  # 10 days late > 7
    assert facts["customer_state"] == "PE" and facts["primary_payment_type"] == "boleto"


@pytest.mark.parametrize(
    "order, contact",
    [
        (invented(progress="delivered", delivered_at=None), "2018-05-20"),  # delivered but no delivery date
        (invented(purchased_at=T("2018-05-25")), "2018-05-20"),  # writes before buying
        (invented(shipped_at=T("2018-04-01")), "2018-05-20"),  # shipped before the purchase
        (invented(), "2019-01-01"),  # outside the history the twin replays
    ],
)
def test_impossible_invented_orders_are_refused(tmp_path, history, order, contact):
    """An order whose dates cannot be true is refused with a clear message."""
    db = make_store(tmp_path)
    with pytest.raises(ValueError):
        nc.create_with_invented_order(
            "Ali", "normal", "track_order", order, T(contact), db_path=db, contacts=history
        )


def test_delete_removes_the_customer_and_its_invented_order(tmp_path, history):
    """Deleting a new customer also removes its invented order; real orders are never removed."""
    db = make_store(tmp_path)
    record = nc.create_with_invented_order(
        "Lina", "normal", "track_order", invented(), T("2018-05-20"), db_path=db, contacts=history
    )
    real = nc.create_with_real_order("Amira", "normal", "track_order", seed=0, db_path=db, contacts=history)
    assert nc.delete_new_customer(record["contact_id"], db) and nc.delete_new_customer(real["contact_id"], db)
    assert nc.get_new_customer(record["contact_id"], db) is None
    assert AdvisorTools(as_of=T("2018-05-20"), db_path=db).order_facts(record["order_id"]) is None
    assert AdvisorTools(as_of=T("2018-05-20"), db_path=db).order_facts("o1") is not None
    assert not nc.delete_new_customer("NC999999", db)


def test_profile_of_a_new_customer_keeps_the_chosen_persona(tmp_path, history):
    """The Client agent and the advisor see a new customer like any profile, with the persona chosen."""
    db = make_store(tmp_path)
    record = nc.create_with_real_order(
        "Amira", "patient", "track_order", seed=0, db_path=db, contacts=history
    )
    profile = profile_from_record(record)
    assert profile.contact_id == "NC000001" and profile.persona == "patient"
    assert profile.contact_timestamp == T("2018-05-20 09:00") and profile.order_id == "o1"
