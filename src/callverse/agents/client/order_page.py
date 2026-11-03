"""The customer's own "My orders" page: what a real customer can see, nothing more.

Shared by the front office (a human customer's order page) and the Client agent's
``view_my_order_page`` tool, so the simulated customer sees exactly what a human
customer sees, as of the moment of the chat (the twin replays history). Internal
facts (carrier investigation flags, rules-engine decisions, earlier tickets, other
customers' orders) are never part of it: the customer can check what the advisor
says, not read the advisor's screen.
"""

from typing import Any

import pandas as pd

# Order status in the words of the customer's app
STATUS_LABEL = {
    "created": "Waiting for payment confirmation",
    "approved": "Paid, being prepared by the seller",
    "shipped": "With the carrier",
    "delivered": "Delivered",
    "canceled": "Canceled",
    "unavailable": "Canceled (the seller could not fulfil it)",
}


def order_timeline(facts: dict[str, Any], as_of: pd.Timestamp) -> list[dict[str, Any]]:
    """Order journey at the contact date: done, current, upcoming or late steps."""

    def stamp(key: str) -> pd.Timestamp | None:
        value = facts.get(key)
        return None if value is None or pd.isna(value) else pd.Timestamp(value)

    steps = [
        ("Order placed", stamp("order_purchase_timestamp"), None),
        ("Payment approved", stamp("order_approved_at"), None),
        ("Handed to the carrier", stamp("order_delivered_carrier_date"), stamp("latest_shipping_limit_date")),
        ("Delivered", stamp("order_delivered_customer_date"), stamp("order_estimated_delivery_date")),
    ]
    rows, current_set = [], False
    for label, done_at, due in steps:
        done = done_at is not None and done_at <= as_of
        late = not done and due is not None and as_of > due
        state = "done" if done else ("late" if late else ("current" if not current_set else "upcoming"))
        if not done:
            current_set = True
        rows.append({"label": label, "state": state, "at": done_at if done else None, "due": due})
    if facts.get("order_status") == "canceled":
        rows.append({"label": "Order canceled", "state": "late", "at": None, "due": None})
    return rows


def _day(value: Any) -> str | None:
    return None if value is None or pd.isna(value) else pd.Timestamp(value).strftime("%Y-%m-%d")


def my_order_page(order_id: str, as_of: pd.Timestamp) -> dict[str, Any] | None:
    """The customer's order page at ``as_of`` (None if the order does not exist)."""
    from callverse.agents.advisor.tools import AdvisorTools

    facts = AdvisorTools(as_of=as_of).order_facts(order_id)
    if facts is None:
        return None
    status = str(facts.get("order_status_at_contact"))
    steps = []
    for row in order_timeline(facts, as_of):
        step = {"step": row["label"], "state": row["state"], "on": _day(row["at"])}
        if row["state"] != "done" and row["due"] is not None:
            step["expected_by"] = _day(row["due"])  # the date the store promised
        steps.append(step)
    value = facts.get("order_value")
    return {
        "order_id": order_id,
        "today": _day(as_of),
        "status": STATUS_LABEL.get(status, status),
        "estimated_delivery": _day(facts.get("order_estimated_delivery_date")),
        "delivered_on": _day(facts.get("order_delivered_customer_date")) if status == "delivered" else None,
        "steps": steps,
        "items": None if pd.isna(facts.get("item_count")) else int(facts["item_count"]),
        "amount_paid_brl": None if value is None or pd.isna(value) else round(float(value), 2),
        "payment": facts.get("primary_payment_type"),
    }


def summarize_page(page: dict[str, Any] | None) -> str:
    """What the customer saw on the page, in one line (for the UI)."""
    if not page:
        return "order not found"
    late = [s["step"].lower() for s in page["steps"] if s["state"] == "late"]
    when = page.get("delivered_on") or page.get("estimated_delivery")
    label = "delivered on" if page.get("delivered_on") else "estimated"
    return (
        f"status: {page['status']}"
        + (f", {label} {when}" if when else "")
        + (f", late: {', '.join(late)}" if late else "")
    )
