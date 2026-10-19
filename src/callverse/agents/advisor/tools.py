"""Business tools the advisor can call (DSO2): they read the SQLite store.

The twin replays history, so every tool answers "as of" the moment the customer
writes (``as_of``): the order status is the one known at that time, and only
earlier tickets are visible. Every call is logged with success/failure, which
gives the DSO2 metric "% of tool uses that work".
"""

import json
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from callverse.config import config_path, database_path, load_yaml
from callverse.data import TICKET_ORDER_COLUMNS, add_contact_facts, connect, load_ticket_config

PROBLEM_TYPES = [
    intent
    for intents in load_yaml("data")["generation"]["contacts"]["intent_groups"].values()
    for intent in intents
]

DATE_COLUMNS = [
    "order_purchase_timestamp",
    "order_approved_at",
    "order_delivered_carrier_date",
    "order_delivered_customer_date",
    "order_estimated_delivery_date",
    "latest_shipping_limit_date",
]


@dataclass
class ToolCall:
    """One tool execution, for traces and the tool-success metric."""

    name: str
    arguments: dict[str, Any]
    ok: bool
    result: dict[str, Any]
    latency_ms: float


@dataclass
class AdvisorTools:
    """Order lookup, ticket history, refund eligibility, ticket creation, KB search."""

    as_of: pd.Timestamp
    db_path: Path = field(default_factory=database_path)
    retriever: Any = None
    calls: list[ToolCall] = field(default_factory=list)
    opened_tickets: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        config = load_ticket_config(config_path("data"))
        self._late_days = config.investigation_after_days_late
        self._transit_days = config.investigation_transit_days

    # ----------------------------------------------------------------- helpers
    def _connection(self) -> sqlite3.Connection:
        return connect(self.db_path)

    def _order_row(self, order_id: str) -> pd.DataFrame:
        columns = ", ".join(
            f'o."{c}"'
            for c in TICKET_ORDER_COLUMNS
            if c not in {"payment_minus_order_value", "latest_shipping_limit_date"}
        )
        query = (
            f"SELECT {columns}, o.latest_shipping_limit_date, o.payment_total, o.order_value, "
            "o.item_count, o.primary_category_english, o.customer_city, o.customer_state "
            "FROM orders o WHERE o.order_id = ?"
        )
        with self._connection() as connection:
            frame = pd.read_sql_query(query, connection, params=(order_id.strip(),))
        for column in DATE_COLUMNS:
            if column in frame:
                frame[column] = pd.to_datetime(frame[column], errors="coerce")
        if not frame.empty:
            frame["payment_minus_order_value"] = frame["payment_total"] - frame["order_value"]
        return frame

    def order_facts(self, order_id: str, intent: str | None = None) -> dict[str, Any] | None:
        """Order record + facts at ``as_of`` (status, lateness, investigation)."""
        frame = self._order_row(order_id)
        if frame.empty:
            return None
        frame["opened_at"] = self.as_of
        frame["intent"] = intent or ""
        frame = add_contact_facts(frame, self._late_days, self._transit_days)
        return frame.iloc[0].to_dict()

    def _record(
        self, name: str, arguments: dict[str, Any], started: float, ok: bool, result: dict[str, Any]
    ) -> dict[str, Any]:
        self.calls.append(ToolCall(name, arguments, ok, result, (time.perf_counter() - started) * 1000))
        return result

    # ------------------------------------------------------------------- tools
    def lookup_order(self, order_id: str) -> dict[str, Any]:
        """Status, dates, amounts and items of an order, as known now."""
        started = time.perf_counter()
        facts = self.order_facts(str(order_id))
        if facts is None:
            return self._record(
                "lookup_order",
                {"order_id": order_id},
                started,
                False,
                {"error": f"No order {order_id}. Ask the customer to check the number."},
            )

        def fmt(value: Any) -> str | None:
            return None if pd.isna(value) else pd.Timestamp(value).strftime("%Y-%m-%d")

        result = {
            "order_id": facts["order_id"],
            "status_now": facts["order_status_at_contact"],
            "purchased_on": fmt(facts["order_purchase_timestamp"]),
            "estimated_delivery": fmt(facts["order_estimated_delivery_date"]),
            "handed_to_carrier_on": fmt(facts["order_delivered_carrier_date"])
            if facts["order_status_at_contact"] in {"shipped", "delivered"}
            else None,
            "delivered_on": fmt(facts["order_delivered_customer_date"])
            if facts["order_status_at_contact"] == "delivered"
            else None,
            "seller_shipping_deadline": fmt(facts["latest_shipping_limit_date"]),
            "days_past_estimated_date": int(facts["days_past_estimate"]),
            "needs_carrier_investigation": bool(facts["needs_investigation"]),
            "items": int(facts["item_count"]) if not pd.isna(facts["item_count"]) else None,
            "sellers": int(facts["distinct_sellers"]) if not pd.isna(facts["distinct_sellers"]) else None,
            "category": facts.get("primary_category_english"),
            "order_value_brl": round(float(facts["order_value"]), 2)
            if not pd.isna(facts["order_value"])
            else None,
            "payment_type": facts["primary_payment_type"],
            "installments": int(facts["max_installments"])
            if not pd.isna(facts["max_installments"])
            else None,
            "uses_voucher": bool(facts["uses_voucher"]) if not pd.isna(facts["uses_voucher"]) else False,
            "payment_differs_from_order_value": bool(abs(facts["payment_minus_order_value"]) > 1)
            if not pd.isna(facts["payment_minus_order_value"])
            else False,
        }
        return self._record("lookup_order", {"order_id": order_id}, started, True, result)

    def get_ticket_history(self, order_id: str) -> dict[str, Any]:
        """Earlier support tickets of this order (before now)."""
        started = time.perf_counter()
        with self._connection() as connection:
            frame = pd.read_sql_query(
                "SELECT ticket_id, intent, opened_at, outcome, outcome_class, resolved_at "
                "FROM tickets WHERE order_id = ? AND opened_at < ? ORDER BY opened_at",
                connection,
                params=(str(order_id).strip(), self.as_of.isoformat(sep=" ")),
            )
        result = {"order_id": order_id, "previous_tickets": frame.to_dict("records")}
        return self._record("get_ticket_history", {"order_id": order_id}, started, True, result)

    def check_refund_eligibility(self, order_id: str) -> dict[str, Any]:
        """Refund / return options from the refund and returns policies."""
        started = time.perf_counter()
        facts = self.order_facts(str(order_id))
        if facts is None:
            return self._record(
                "check_refund_eligibility",
                {"order_id": order_id},
                started,
                False,
                {"error": f"No order {order_id}."},
            )
        status = facts["order_status_at_contact"]
        delivered = facts["order_delivered_customer_date"]
        days_since_delivery = (
            int((self.as_of.normalize() - pd.Timestamp(delivered).normalize()).days)
            if status == "delivered" and not pd.isna(delivered)
            else None
        )
        if status in {"canceled", "unavailable"}:
            option = "automatic_refund"
        elif status in {"created", "approved"}:
            option = "free_cancellation"
        elif status == "shipped":
            option = "refuse_delivery_or_return_after_receipt"
        elif days_since_delivery is not None and days_since_delivery <= 7:
            option = "free_return_withdrawal_7_days"
        elif days_since_delivery is not None and days_since_delivery <= 30:
            option = "return_only_if_defective_or_exchange_30_days"
        else:
            option = "no_standard_return"
        result = {
            "order_id": order_id,
            "status_now": status,
            "option": option,
            "days_since_delivery": days_since_delivery,
            "payment_type": facts["primary_payment_type"],
            "refund_channel": "bank_transfer_needs_bank_details"
            if facts["primary_payment_type"] == "boleto"
            else "same_payment_method",
        }
        return self._record("check_refund_eligibility", {"order_id": order_id}, started, True, result)

    def open_ticket(self, order_id: str, reason: str, handed_to: str = "back_office") -> dict[str, Any]:
        """Open a follow-up case (carrier, seller, payments team, supervisor)."""
        started = time.perf_counter()
        allowed = {"carrier", "seller", "payments_team", "supervisor", "back_office"}
        if handed_to not in allowed:
            return self._record(
                "open_ticket",
                {"order_id": order_id, "handed_to": handed_to},
                started,
                False,
                {"error": f"handed_to must be one of {sorted(allowed)}"},
            )
        ticket = {
            "ticket_id": f"NEW-{len(self.opened_tickets) + 1:03d}",
            "order_id": order_id,
            "reason": reason,
            "handed_to": handed_to,
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
        self.opened_tickets.append(ticket)
        return self._record(
            "open_ticket",
            {"order_id": order_id, "reason": reason, "handed_to": handed_to},
            started,
            True,
            ticket,
        )

    def search_knowledge_base(self, query: str) -> dict[str, Any]:
        """Top policy sections for a question."""
        started = time.perf_counter()
        if self.retriever is None:
            return self._record(
                "search_knowledge_base",
                {"query": query},
                started,
                False,
                {"error": "knowledge base unavailable"},
            )
        hits = self.retriever.search(query, top_k=3)
        result = {
            "results": [
                {
                    "chunk_id": h.chunk.chunk_id,
                    "section": h.chunk.section,
                    "score": round(h.score, 3),
                    "text": h.chunk.text[:900],
                }
                for h in hits
            ]
        }
        return self._record("search_knowledge_base", {"query": query}, started, True, result)

    def recommend_resolution(self, order_id: str, problem_type: str) -> dict[str, Any]:
        """Company rules engine: the policy-approved action for this order and problem."""
        from callverse.data.conversations import answer_and_summary
        from callverse.data.tickets import decide_outcome

        started = time.perf_counter()
        arguments = {"order_id": order_id, "problem_type": problem_type}
        if problem_type not in PROBLEM_TYPES:
            return self._record(
                "recommend_resolution",
                arguments,
                started,
                False,
                {"error": f"problem_type must be one of {PROBLEM_TYPES}"},
            )
        facts = self.order_facts(str(order_id), problem_type)
        if facts is None:
            return self._record(
                "recommend_resolution", arguments, started, False, {"error": f"No order {order_id}."}
            )
        row = pd.Series({**facts, "intent": problem_type})
        outcome, chunk, handed_to = decide_outcome(row)
        row["outcome"] = outcome
        answer, summary = answer_and_summary(row)
        result = {
            "recommended_action": outcome,
            "policy_section": chunk,
            "hand_over_to": handed_to,
            "approved_answer": answer,
            "summary": summary,
        }
        return self._record("recommend_resolution", arguments, started, True, result)

    # ---------------------------------------------------------- LLM interface
    def execute(self, name: str, arguments: dict[str, Any]) -> str:
        """Run a tool requested by the LLM; returns JSON for the tool message."""
        functions = {
            "lookup_order": self.lookup_order,
            "get_ticket_history": self.get_ticket_history,
            "recommend_resolution": self.recommend_resolution,
            "check_refund_eligibility": self.check_refund_eligibility,
            "open_ticket": self.open_ticket,
            "search_knowledge_base": self.search_knowledge_base,
        }
        started = time.perf_counter()
        if name not in functions:
            result = self._record(name, arguments, started, False, {"error": f"unknown tool {name}"})
        else:
            try:
                result = functions[name](**arguments)
            except TypeError as error:
                result = self._record(name, arguments, started, False, {"error": f"bad arguments: {error}"})
        return json.dumps(result, default=str)

    def success_rate(self) -> float | None:
        """Share of tool calls that worked (None if no call)."""
        if not self.calls:
            return None
        return sum(call.ok for call in self.calls) / len(self.calls)


def _schema(name: str, description: str, properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": properties, "required": required},
        },
    }


TOOL_SCHEMAS = [
    _schema(
        "lookup_order",
        "Get the current status, dates, amounts and payment of an order.",
        {"order_id": {"type": "string", "description": "The 32-character order number"}},
        ["order_id"],
    ),
    _schema(
        "get_ticket_history",
        "List earlier support tickets of an order.",
        {"order_id": {"type": "string"}},
        ["order_id"],
    ),
    _schema(
        "check_refund_eligibility",
        "Which refund, return or cancellation option applies to an order.",
        {"order_id": {"type": "string"}},
        ["order_id"],
    ),
    _schema(
        "open_ticket",
        "Open a follow-up case with another team when the chat cannot solve it.",
        {
            "order_id": {"type": "string"},
            "reason": {"type": "string"},
            "handed_to": {
                "type": "string",
                "enum": ["carrier", "seller", "payments_team", "supervisor", "back_office"],
            },
        },
        ["order_id", "reason", "handed_to"],
    ),
    _schema(
        "search_knowledge_base",
        "Search company policies (returns, refunds, delays, payments...).",
        {"query": {"type": "string"}},
        ["query"],
    ),
]

POLICY_TOOL = _schema(
    "recommend_resolution",
    "Company rules engine: returns the policy-approved action, the approved answer and who to "
    "hand over to, for an order and a problem type. Use it before answering.",
    {"order_id": {"type": "string"}, "problem_type": {"type": "string", "enum": PROBLEM_TYPES}},
    ["order_id", "problem_type"],
)


def tool_schemas(variant: str = "rag_policy") -> list[dict[str, Any]]:
    """Tools offered to the LLM: ``rag`` (pure agentic RAG) or ``rag_policy`` (+ rules engine)."""
    return TOOL_SCHEMAS + ([POLICY_TOOL] if variant == "rag_policy" else [])
