"""Unit tests for synthetic tickets and chat logs (Phase 1F)."""

import re
from pathlib import Path

import pandas as pd
import pytest

from callverse.agents.advisor import load_chunks
from callverse.data import (
    conversations,
    decide_outcome,
    generate_chat_messages,
    generate_tickets,
    load_ticket_config,
    order_status_at,
    tickets,
)
from callverse.data.conversations import answer_and_summary
from callverse.data.tickets import add_business_days

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG = load_ticket_config(PROJECT_ROOT / "configs" / "data.yaml")
SERVICE_TIMES = {
    "wismo": (180.0, 0.6),
    "order_admin": (240.0, 0.6),
    "cancel_refund": (360.0, 0.6),
    "post_delivery": (420.0, 0.6),
}
T = pd.Timestamp


def make_orders() -> pd.DataFrame:
    """Orders: late in transit, canceled boleto, delivered multi-seller, new."""
    return pd.DataFrame(
        {
            "order_id": ["o_late", "o_canceled", "o_delivered", "o_new"],
            "order_status": ["delivered", "canceled", "delivered", "approved"],
            "order_purchase_timestamp": [T("2017-01-02 10:00")] * 4,
            "order_approved_at": [T("2017-01-02 11:00")] * 4,
            "order_delivered_carrier_date": [
                T("2017-01-04"),
                pd.NaT,
                T("2017-01-04"),
                pd.NaT,
            ],
            "order_delivered_customer_date": [
                T("2017-03-01"),
                pd.NaT,
                T("2017-01-10"),
                pd.NaT,
            ],
            "order_estimated_delivery_date": [T("2017-01-25")] * 4,
            "latest_shipping_limit_date": [T("2017-01-06")] * 3 + [T("2017-03-01")],
            "primary_payment_type": ["credit_card", "boleto", "credit_card", "voucher"],
            "payment_minus_order_value": [0.0, 0.0, 0.0, 0.0],
            "max_installments": [1, 1, 1, 1],
            "uses_voucher": [False, False, False, True],
            "distinct_sellers": [1, 1, 2, 1],
        }
    )


def make_contacts() -> pd.DataFrame:
    rows = [
        ("SC000001", "o_late", "track_order", "wismo", T("2017-02-01 09:00")),
        (
            "SC000002",
            "o_canceled",
            "request_refund",
            "cancel_refund",
            T("2017-01-05 15:30"),
        ),
        (
            "SC000003",
            "o_delivered",
            "missing_item",
            "post_delivery",
            T("2017-01-12 18:00"),
        ),
        ("SC000004", "o_new", "change_order", "order_admin", T("2017-01-03 08:15")),
        (
            "SC000005",
            "o_delivered",
            "request_invoice",
            "order_admin",
            T("2017-01-14 12:00"),
        ),
    ]
    contacts = pd.DataFrame(
        rows,
        columns=[
            "contact_id",
            "order_id",
            "intent",
            "intent_group",
            "contact_timestamp",
        ],
    )
    contacts["customer_unique_id"] = "c1"
    contacts["message_text"] = "customer message " + contacts["contact_id"]
    return contacts


def test_order_status_at_follows_the_timeline() -> None:
    orders = make_orders()
    at = pd.Series([T("2017-01-03"), T("2017-01-03"), T("2017-01-05"), T("2017-01-02")])
    assert order_status_at(orders, at).tolist() == [
        "approved",
        "canceled",
        "shipped",
        "created",
    ]
    later = pd.Series([T("2017-03-02")] * 4)
    assert order_status_at(orders, later).tolist() == [
        "delivered",
        "canceled",
        "delivered",
        "approved",
    ]


def test_outcome_rules() -> None:
    tickets_ = generate_tickets(make_contacts(), make_orders(), CONFIG, SERVICE_TIMES)
    outcomes = dict(zip(tickets_["contact_id"], tickets_["outcome"]))
    # 7 days past the estimate and 28 days in transit (> 25): investigation
    assert outcomes["SC000001"] == "carrier_investigation"
    assert outcomes["SC000002"] == "bank_details_requested"
    assert outcomes["SC000003"] == "separate_parcels_explained"
    assert outcomes["SC000004"] == "cancel_and_reorder_advised"
    assert outcomes["SC000005"] == "invoice_sent"


def test_payment_rules() -> None:
    row = pd.Series(
        {
            "intent": "payment_issue",
            "order_status_at_contact": "approved",
            "primary_payment_type": "not_defined",
            "payment_minus_order_value": 0.0,
            "max_installments": 1,
            "uses_voucher": False,
        }
    )
    assert decide_outcome(row)[0] == "escalated_payments"
    row["primary_payment_type"] = "credit_card"
    row["payment_minus_order_value"] = 50.0
    row["max_installments"] = 6
    assert decide_outcome(row)[0] == "installments_explained"


def test_add_business_days_skips_weekends() -> None:
    friday = pd.Series([T("2017-01-06 16:00"), T("2017-01-07 10:00")])  # Fri, Sat
    shifted = add_business_days(friday, pd.Series([1, 0]))
    assert shifted.tolist() == [T("2017-01-09 16:00"), T("2017-01-07 10:00")]


def test_tickets_are_reproducible_and_consistent() -> None:
    contacts, orders = make_contacts(), make_orders()
    first = generate_tickets(contacts, orders, CONFIG, SERVICE_TIMES)
    pd.testing.assert_frame_equal(
        first, generate_tickets(contacts, orders, CONFIG, SERVICE_TIMES)
    )
    assert first["ticket_id"].is_unique and len(first) == len(contacts)
    assert (first["chat_closed_at"] > first["opened_at"]).all()
    assert (first["resolved_at"] >= first["chat_closed_at"]).all()
    assert (
        first["first_contact_resolution"]
        .eq(first["outcome_class"].eq("resolved_in_chat"))
        .all()
    )
    assert first["csat_score"].dropna().between(1, 5).all()


def test_chat_messages_fit_the_ticket() -> None:
    contacts, orders = make_contacts(), make_orders()
    tickets_ = generate_tickets(contacts, orders, CONFIG, SERVICE_TIMES)
    messages = generate_chat_messages(tickets_, contacts, orders, seed := 1)
    pd.testing.assert_frame_equal(
        messages, generate_chat_messages(tickets_, contacts, orders, seed)
    )
    assert messages["message_id"].is_unique
    for ticket in tickets_.itertuples():
        chat = messages[messages["ticket_id"] == ticket.ticket_id]
        assert chat["turn"].tolist() == list(range(1, len(chat) + 1))
        assert chat["sent_at"].is_monotonic_increasing
        assert chat["sent_at"].iloc[0] == ticket.opened_at
        assert chat["sent_at"].iloc[-1] == ticket.chat_closed_at
        first = chat.iloc[0]
        assert first.speaker == "customer"
        assert first.text == f"customer message {ticket.contact_id}"
        assert ticket.kb_chunk_id in chat["kb_chunk_id"].tolist()
        assert ticket.order_id in chat["text"].iloc[2]


def outcomes_in_rules() -> set[str]:
    source = Path(tickets.__file__).read_text(encoding="utf-8")
    return set(re.findall(r'"([a-z_]+)",\s*"[a-z_]+__s\d\d"', source))


@pytest.mark.parametrize("outcome", sorted(outcomes_in_rules()))
def test_every_outcome_has_a_chat_template(outcome: str) -> None:
    ticket = pd.Series(
        {
            "outcome": outcome,
            "order_status_at_contact": "shipped",
            "order_estimated_delivery_date": T("2017-01-25"),
            "order_delivered_customer_date": T("2017-01-20"),
            "primary_payment_type": "credit_card",
            "days_past_estimate": 3,
            "distinct_sellers": 2,
        }
    )
    answer, summary = answer_and_summary(ticket)
    assert answer and summary and "{" not in answer + summary


def test_follow_up_config_names_real_outcomes() -> None:
    known = outcomes_in_rules() | {"supervisor_callback"}
    assert set(CONFIG.follow_up_business_days) <= known


def test_referenced_kb_chunks_exist() -> None:
    sources = [
        Path(m.__file__).read_text(encoding="utf-8") for m in (tickets, conversations)
    ]
    referenced = {c for s in sources for c in re.findall(r"[a-z_]+__s\d\d", s)}
    chunks = load_chunks(PROJECT_ROOT / "data" / "knowledge_base" / "docs", 1500)
    assert referenced and referenced <= {c.chunk_id for c in chunks}
