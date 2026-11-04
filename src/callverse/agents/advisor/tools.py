"""Business tools the advisor can call (DSO2): they read the SQLite store.

The twin replays history, so every tool answers "as of" the moment the customer
writes (``as_of``): the order status is the one known at that time, and only
earlier tickets are visible. Every call is logged with success/failure, which
gives the DSO2 metric "% of tool uses that work", and with who called it: the
LLM (its own choice), the code (a fixed pipeline step) or a safety net (a step the
LLM forgot).

Tool kinds: data (order lookup, ticket history, customer history, knowledge base),
rules (refund eligibility, rules engine), external API (bank code check, BrasilAPI),
actions (open a ticket, escalate to a human) and a reflection check of every draft.
"""

# How to read this file:
# - ToolCall: the record of one tool execution (name, arguments, ok, result, time, caller).
# - AdvisorTools: the tools as Python methods. Each one reads the SQLite store "as of" the chat date and
#   records its call with _record().
# - execute(): runs a tool the LLM asked for (by name, with its JSON arguments).
# - The JSON schemas at the bottom describe each tool to the LLM (name, description, parameters). The LLM
#   reads these descriptions to decide which tool to call. The CallVerse MCP server (callverse/mcp/server.py)
#   publishes these same descriptions.
# - agentic_tool_names(): gating, i.e. which tools the agentic advisor sees at each stage.
# - DirectToolbox: the LLM's tools called as plain Python. The other toolbox, McpToolbox
#   (callverse/mcp/client.py), reaches the same tools through the MCP server.
import json
import re
import sqlite3
import time
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from callverse.agents.advisor.bank_directory import BankDirectory, BankDirectoryUnavailable, bank_directory
from callverse.agents.advisor.draft_check import Sources, check_draft
from callverse.config import config_path, database_path, load_yaml
from callverse.data import TICKET_ORDER_COLUMNS, add_contact_facts, connect, load_ticket_config
from callverse.data.conversations import SUPERVISOR_PROMISE

# Every problem type (intent) the rules engine knows, read from configs/data.yaml.
PROBLEM_TYPES = [
    intent
    for intents in load_yaml("data")["generation"]["contacts"]["intent_groups"].values()
    for intent in intents
]

# Date columns of the orders table (SQLite stores them as text; we turn them back into dates).
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
    caller: str = "code"  # "llm" (the model chose it), "code" (pipeline step) or "safety_net"
    via: str = "direct"  # "mcp" (through the CallVerse MCP server) or "direct" (a plain Python call)

    @property
    def summary(self) -> str:
        """What the call found, in one line (for the UI)."""
        return summarize_tool_call(self.name, self.ok, self.result)


def summarize_tool_call(name: str, ok: bool, result: dict[str, Any]) -> str:
    """One plain line saying what a tool call found."""
    # A failed call shows its error message.
    if not ok or "error" in result:
        return str(result.get("error", "failed"))
    if name == "lookup_order":
        estimate = result.get("estimated_delivery")
        return f"status {result.get('status_now')}" + (f", estimated {estimate}" if estimate else "")
    if name == "get_ticket_history":
        count = len(result.get("previous_tickets", []))
        return f"{count} earlier ticket(s) on this order" if count else "no earlier ticket on this order"
    if name == "get_customer_history":
        return str(result.get("summary", ""))
    if name == "check_refund_eligibility":
        return f"option: {str(result.get('option', '')).replace('_', ' ')}"
    if name == "recommend_resolution":
        action = str(result.get("recommended_action", "")).replace("_", " ")
        return f"action: {action}, hand over to {result.get('hand_over_to') or 'nobody'}"
    if name == "validate_bank_code":
        code = result.get("bank_code")
        return f"{code} = {result.get('bank_name')}" if result.get("valid") else f"{code} is not a bank code"
    if name in {"open_ticket", "escalate_to_human"}:
        prefix = "already escalated: " if result.get("already_escalated") else ""
        return f"{prefix}{result.get('ticket_id')} handed to {result.get('handed_to')}"
    if name == "search_knowledge_base":
        hits = result.get("results", [])
        return f"{len(hits)} policy section(s), best: {hits[0]['section']}" if hits else "no policy section"
    if name == "check_draft_reply":
        if result.get("passed"):
            return f"draft OK, {sum(result.get('checked', {}).values())} fact(s) checked"
        problems = result.get("problems") or ["unknown problem"]
        return f"draft rejected: {problems[0]}"
    return ""


@dataclass
class AdvisorTools:
    """Order lookup, ticket and customer history, refund eligibility, tickets, KB search,
    bank code check, escalation and the draft check."""

    # as_of: the moment the customer writes (history is replayed: the tools only see the past). calls: every
    # tool call of the chat (the success metric is computed from it). opened_tickets: the tickets created
    # during the chat.
    as_of: pd.Timestamp
    db_path: Path = field(default_factory=database_path)
    retriever: Any = None
    calls: list[ToolCall] = field(default_factory=list)
    opened_tickets: list[dict[str, Any]] = field(default_factory=list)
    # Called after every tool execution (live UI shows tools as they run)
    listener: Callable[[ToolCall], None] | None = field(default=None, repr=False, compare=False)
    # External bank list (None: the one configured in configs/agents.yaml)
    banks: BankDirectory | None = field(default=None, repr=False, compare=False)
    escalation: dict[str, Any] | None = None
    current_caller: str = field(default="code", init=False, repr=False, compare=False)
    current_via: str = field(default="direct", init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        # Investigation thresholds from configs/data.yaml (how late before the carrier must investigate).
        config = load_ticket_config(config_path("data"))
        self._late_days = config.investigation_after_days_late
        self._transit_days = config.investigation_transit_days

    # ----------------------------------------------------------------- helpers
    def _connection(self) -> sqlite3.Connection:
        """A connection to the SQLite store."""
        return connect(self.db_path)

    def _order_row(self, order_id: str) -> pd.DataFrame:
        # Read one order row with plain SQL. The "?" placeholder keeps the order number out of the SQL text,
        # which prevents SQL injection.
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
        # SQLite stores dates as text: convert them back into real dates.
        for column in DATE_COLUMNS:
            if column in frame:
                frame[column] = pd.to_datetime(frame[column], errors="coerce")
        # A gap between the amount paid and the order value hints at a payment problem.
        if not frame.empty:
            frame["payment_minus_order_value"] = frame["payment_total"] - frame["order_value"]
        return frame

    def order_facts(self, order_id: str, intent: str | None = None) -> dict[str, Any] | None:
        """Order record + facts at ``as_of`` (status, lateness, investigation)."""
        frame = self._order_row(order_id)
        if frame.empty:
            return None
        # add_contact_facts() computes the status AT the chat date, the days late and whether the carrier must
        # investigate (the same rules that built the ticket history).
        frame["opened_at"] = self.as_of
        frame["intent"] = intent or ""
        frame = add_contact_facts(frame, self._late_days, self._transit_days)
        return frame.iloc[0].to_dict()

    def _record(
        self, name: str, arguments: dict[str, Any], started: float, ok: bool, result: dict[str, Any]
    ) -> dict[str, Any]:
        # Every tool ends here: the call is stored with its result, its duration, who called it and how (MCP
        # or direct), and the live UI is notified (listener).
        call = ToolCall(
            name,
            arguments,
            ok,
            result,
            (time.perf_counter() - started) * 1000,
            self.current_caller,
            self.current_via,
        )
        self.calls.append(call)
        if self.listener is not None:
            self.listener(call)
        return result

    @contextmanager
    def called_by(self, caller: str) -> Iterator[None]:
        """Label the tool calls made inside the block: ``llm``, ``code`` or ``safety_net``."""
        # Usage: `with tools.called_by("safety_net"): tools.lookup_order(...)`.
        previous, self.current_caller = self.current_caller, caller
        try:
            yield
        finally:
            self.current_caller = previous

    def _new_ticket(self, order_id: str, reason: str, handed_to: str) -> dict[str, Any]:
        # Tickets opened during a chat stay in memory, with ids NEW-001, NEW-002, ...
        ticket = {
            "ticket_id": f"NEW-{len(self.opened_tickets) + 1:03d}",
            "order_id": order_id,
            "reason": reason,
            "handed_to": handed_to,
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
        self.opened_tickets.append(ticket)
        return ticket

    # ------------------------------------------------------------------- tools
    # Each tool follows the same pattern: start a timer, compute the result, return self._record(...).
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

        # Only what the advisor needs, in simple types (text, numbers, true/false) the LLM reads as JSON.
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
        # Tickets opened BEFORE the chat date only (the advisor cannot see the future).
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
        # Refund rules (policy): canceled -> automatic refund; not shipped -> free cancellation; shipped ->
        # refuse the delivery or return it; delivered up to 7 days ago -> free return (the Brazilian right of
        # withdrawal); up to 30 days -> return if defective, or exchange; later -> no standard return.
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
            # Boleto (bank slip) payments are refunded by bank transfer, so the bank details are needed.
            "refund_channel": "bank_transfer_needs_bank_details"
            if facts["primary_payment_type"] == "boleto"
            else "same_payment_method",
        }
        return self._record("check_refund_eligibility", {"order_id": order_id}, started, True, result)

    def open_ticket(self, order_id: str, reason: str, handed_to: str = "back_office") -> dict[str, Any]:
        """Open a follow-up case (carrier, seller, payments team, supervisor)."""
        started = time.perf_counter()
        # Validation: the team must be one of a fixed list (an LLM could invent a team name).
        allowed = {"carrier", "seller", "payments_team", "supervisor", "back_office"}
        if handed_to not in allowed:
            return self._record(
                "open_ticket",
                {"order_id": order_id, "handed_to": handed_to},
                started,
                False,
                {"error": f"handed_to must be one of {sorted(allowed)}"},
            )
        ticket = self._new_ticket(order_id, reason, handed_to)
        return self._record(
            "open_ticket",
            {"order_id": order_id, "reason": reason, "handed_to": handed_to},
            started,
            True,
            ticket,
        )

    def escalate_to_human(self, reason: str, order_id: str = "", urgency: str = "normal") -> dict[str, Any]:
        """Hand the conversation to a human supervisor (playbook: "When to escalate")."""
        started = time.perf_counter()
        arguments = {"order_id": order_id, "reason": reason, "urgency": urgency}
        # Validation: urgency must be "normal" or "high".
        if urgency not in {"normal", "high"}:
            return self._record(
                "escalate_to_human", arguments, started, False, {"error": "urgency: 'normal' or 'high'"}
            )
        if self.escalation is not None:  # one escalation per chat
            return self._record(
                "escalate_to_human", arguments, started, True, {**self.escalation, "already_escalated": True}
            )
        ticket = self._new_ticket(order_id or "unknown", reason, "supervisor")
        self.escalation = {**ticket, "urgency": urgency, "tell_customer": SUPERVISOR_PROMISE}
        return self._record("escalate_to_human", arguments, started, True, self.escalation)

    def get_customer_history(self, order_id: str) -> dict[str, Any]:
        """The same customer's other orders and tickets, before now (long-term memory)."""
        from callverse.data.tickets import order_status_at

        started = time.perf_counter()
        arguments = {"order_id": order_id}
        # Long-term memory: the same customer's earlier orders and tickets, before the chat date.
        order_id, now = str(order_id).strip(), self.as_of.isoformat(sep=" ")
        with self._connection() as connection:
            owner = connection.execute(
                "SELECT customer_unique_id, customer_city, customer_state FROM orders WHERE order_id = ?",
                (order_id,),
            ).fetchone()
            if owner is None:
                return self._record(
                    "get_customer_history", arguments, started, False, {"error": f"No order {order_id}."}
                )
            orders = pd.read_sql_query(
                "SELECT order_id, order_status, order_purchase_timestamp, order_approved_at, "
                "order_delivered_carrier_date, order_delivered_customer_date, customer_city, "
                "customer_state FROM orders WHERE customer_unique_id = ? AND order_id <> ? "
                "AND order_purchase_timestamp < ? ORDER BY order_purchase_timestamp DESC LIMIT 10",
                connection,
                params=(owner[0], order_id, now),
            )
            tickets = pd.read_sql_query(
                "SELECT order_id, intent, opened_at, outcome, handed_to FROM tickets "
                "WHERE customer_unique_id = ? AND order_id <> ? AND opened_at < ? "
                "ORDER BY opened_at DESC LIMIT 10",
                connection,
                params=(owner[0], order_id, now),
            )
        previous_orders = []
        if not orders.empty:
            for column in DATE_COLUMNS[:4]:
                orders[column] = pd.to_datetime(orders[column], errors="coerce")
            orders["status_now"] = order_status_at(orders, pd.Series(self.as_of, index=orders.index))
            previous_orders = [
                {
                    "order_id": row.order_id,
                    "purchased_on": row.order_purchase_timestamp.strftime("%Y-%m-%d"),
                    "status_now": row.status_now,
                    "delivery_city": f"{row.customer_city} ({row.customer_state})",
                }
                for row in orders.itertuples()
            ]
        previous_tickets = [
            {
                "order_id": row.order_id,
                "problem_type": row.intent,
                "opened_on": str(row.opened_at)[:10],
                "outcome": row.outcome,
                "handed_to": row.handed_to,
            }
            for row in tickets.itertuples()
        ]
        # A fraud sign from the playbook: many orders sent to different addresses.
        cities = {(owner[1], owner[2])}
        cities |= {(row.customer_city, row.customer_state) for row in orders.itertuples()}
        signals = []
        if previous_tickets:
            signals.append(
                f"{len(previous_tickets)} earlier ticket(s) on other orders: check for a repeat problem."
            )
        if len(cities) >= 3:
            signals.append(
                f"Orders went to {len(cities)} different cities; the playbook lists many orders to "
                "different addresses as a fraud sign."
            )
        result = {
            "order_id": order_id,
            "summary": (
                f"{len(previous_orders)} earlier order(s), {len(previous_tickets)} earlier ticket(s)."
                if previous_orders or previous_tickets
                else "First order of this customer, no earlier tickets."
            ),
            "previous_orders": previous_orders,
            "previous_tickets": previous_tickets,
            "delivery_cities": len(cities),
            "signals": signals,
        }
        return self._record("get_customer_history", arguments, started, True, result)

    def validate_bank_code(self, bank_code: str) -> dict[str, Any]:
        """Check a Brazilian bank code against the BrasilAPI list (cached). Only the 3-digit
        code is ever looked up: account numbers stay out of the chat (sent by e-mail)."""
        started = time.perf_counter()
        arguments = {"bank_code": bank_code}
        # Keep only the digits. A Brazilian bank code has 1 to 3 digits (e.g. 341 = Itau).
        digits = re.sub(r"\D", "", str(bank_code))
        if not 1 <= len(digits) <= 3:
            result = {
                "bank_code": str(bank_code),
                "valid": False,
                "reason": "Brazilian bank codes have 3 digits. Ask the customer to check the code.",
            }
            return self._record("validate_bank_code", arguments, started, True, result)
        # zfill(3): "1" -> "001".
        code = digits.zfill(3)
        try:
            # Look the code up in the BrasilAPI bank list (downloaded once, then cached on disk).
            bank = (self.banks or bank_directory()).lookup(code)
        except BankDirectoryUnavailable as error:
            return self._record("validate_bank_code", arguments, started, False, {"error": str(error)})
        if bank is None:
            result = {
                "bank_code": code,
                "valid": False,
                "reason": f"No Brazilian bank has code {code}. Ask the customer to check it.",
            }
        else:
            result = {
                "bank_code": code,
                "valid": True,
                "bank_name": bank.get("full_name") or bank["name"],
                "next_step": "The customer sends the branch, account number and CPF by e-mail "
                "(refund policy). Never ask for them in the chat.",
            }
        return self._record("validate_bank_code", arguments, started, True, result)

    def check_draft_reply(
        self,
        draft: str,
        approved_answer: str = "",
        policy_texts: Iterable[str] = (),
        order_id: str | None = None,
    ) -> dict[str, Any]:
        """Reflection check (always run by code): every date, amount, timing and order number
        of the draft must come from a tool result, the approved answer or the policy."""
        started = time.perf_counter()
        # The "sources of truth": the results of the tools that worked, the approved answer, the policy texts
        # and today's date. Every fact of the draft must appear in one of them.
        sources = Sources.collect(
            (c.result for c in self.calls if c.ok and c.name != "check_draft_reply"),
            [approved_answer, *policy_texts, self.as_of.strftime("%Y-%m-%d")],
            order_id,
        )
        check = check_draft(draft, sources)
        result = {"passed": check.passed, "problems": check.problems, "checked": check.checked}
        return self._record("check_draft_reply", {"draft": draft[:300]}, started, True, result)

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
        # The 3 best policy sections from the retriever (bge-m3 vectors or TF-IDF keywords).
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
        # Validation: the problem type must be one the rules engine knows.
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
        # decide_outcome() = the company rules (data/tickets.py); answer_and_summary() = the approved text for
        # that outcome (data/conversations.py).
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
    def execute(self, name: str, arguments: dict[str, Any], via: str = "direct") -> str:
        """Run a tool requested by the LLM; returns JSON for the tool message."""
        # The result goes back to the LLM as JSON text (a "tool" message).
        return json.dumps(self.call(name, arguments, via), default=str)

    def call(self, name: str, arguments: dict[str, Any], via: str = "direct") -> dict[str, Any]:
        """Run a tool requested by an LLM and return its result. ``via``: "direct" (a Python call) or "mcp"
        (the request came through the CallVerse MCP server)."""
        # The tools an LLM may call, by name (LLM_TOOL_NAMES). check_draft_reply is not one: only code
        # runs it.
        functions = {
            "lookup_order": self.lookup_order,
            "get_ticket_history": self.get_ticket_history,
            "get_customer_history": self.get_customer_history,
            "recommend_resolution": self.recommend_resolution,
            "check_refund_eligibility": self.check_refund_eligibility,
            "validate_bank_code": self.validate_bank_code,
            "open_ticket": self.open_ticket,
            "escalate_to_human": self.escalate_to_human,
            "search_knowledge_base": self.search_knowledge_base,
        }
        started = time.perf_counter()
        # Everything run here is labelled caller="llm" (the model chose it), with the route it took.
        previous_via, self.current_via = self.current_via, via
        try:
            with self.called_by("llm"):
                if name not in functions:
                    return self._record(name, arguments, started, False, {"error": f"unknown tool {name}"})
                try:
                    # **arguments passes the LLM's JSON arguments as Python keyword arguments; a wrong
                    # argument name raises TypeError, caught below.
                    return functions[name](**arguments)
                except TypeError as error:
                    return self._record(name, arguments, started, False, {"error": f"bad arguments: {error}"})
        finally:
            self.current_via = previous_via

    def success_rate(self) -> float | None:
        """Share of tool calls that worked (None if no call)."""
        if not self.calls:
            return None
        return sum(call.ok for call in self.calls) / len(self.calls)


def _schema(name: str, description: str, properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    """A tool description in the OpenAI "function calling" format: name, description and a JSON Schema of
    its parameters.
    """
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": properties, "required": required},
        },
    }


# The tools of the "rag" variant. The descriptions matter: the LLM chooses from them.
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

# The rules engine as a tool (the rag_policy and agentic variants).
POLICY_TOOL = _schema(
    "recommend_resolution",
    "Company rules engine: returns the policy-approved action, the approved answer and who to "
    "hand over to, for an order and a problem type. Use it before answering.",
    {"order_id": {"type": "string"}, "problem_type": {"type": "string", "enum": PROBLEM_TYPES}},
    ["order_id", "problem_type"],
)


# Three of the four tools added for agentic tool calling: escalation (action), bank code check (external API)
# and customer history (memory). The fourth, check_draft_reply, has no schema:
# only code runs it.
ESCALATE_TOOL = _schema(
    "escalate_to_human",
    "Hand the chat to a human supervisor. Use it when the playbook says to escalate: the customer "
    "asks for a supervisor after your answer, threatens legal action (lawyer, PROCON, the press), "
    "the case needs more than your authority, a refund or investigation is overdue, or you see "
    "signs of fraud.",
    {
        "reason": {"type": "string", "description": "Why, in a few words"},
        "order_id": {"type": "string"},
        "urgency": {"type": "string", "enum": ["normal", "high"]},
    },
    ["reason"],
)
BANK_TOOL = _schema(
    "validate_bank_code",
    "Check that the bank code the customer gave exists (Brazilian banks, 3 digits) before a boleto "
    "refund by bank transfer. Never ask for the account number in the chat.",
    {"bank_code": {"type": "string", "description": "The code the customer wrote, e.g. 341"}},
    ["bank_code"],
)
HISTORY_TOOL = _schema(
    "get_customer_history",
    "Earlier orders and support tickets of the same customer (other orders), to spot a repeat "
    "problem or signs of fraud.",
    {"order_id": {"type": "string"}},
    ["order_id"],
)
# Look up a schema by tool name.
SCHEMAS_BY_NAME = {
    schema["function"]["name"]: schema
    for schema in [*TOOL_SCHEMAS, POLICY_TOOL, ESCALATE_TOOL, BANK_TOOL, HISTORY_TOOL]
}

# Agentic variant, tool gating: a small model picks the wrong tool when it sees many, so
# it only sees the ones that make sense now (at most 5), by stage and predicted problem.
INVESTIGATE_EXTRAS = {
    "wismo": ["get_ticket_history", "get_customer_history"],
    "cancel_refund": ["check_refund_eligibility", "get_customer_history"],
    "post_delivery": ["get_ticket_history", "get_customer_history"],
    "order_admin": ["get_customer_history"],
}


def agentic_tool_names(
    stage: str, intent_group: str | None = None, paid_by_boleto: bool = False
) -> list[str]:
    """Tools offered at a stage: ``verify`` (no order number yet), ``investigate`` (order
    known, not answered yet) or ``follow_up`` (after the answer)."""
    # verify: only search and escalation (no order tools without an order number, so the LLM cannot invent
    # one).
    if stage == "verify":
        return ["search_knowledge_base", "escalate_to_human"]
    # investigate: open the order first (lookup_order), plus the extras useful for this problem group.
    if stage == "investigate":
        extras = INVESTIGATE_EXTRAS.get(intent_group or "", ["get_ticket_history", "get_customer_history"])
        return ["lookup_order", *extras, "search_knowledge_base", "escalate_to_human"]
    # follow_up: after the answer. The bank check only for boleto payments.
    if stage == "follow_up":
        bank = ["validate_bank_code"] if paid_by_boleto else []
        return ["search_knowledge_base", "open_ticket", "escalate_to_human", *bank]
    raise ValueError(f"Unknown stage '{stage}' (verify, investigate, follow_up).")


def agentic_tool_schemas(
    stage: str, intent_group: str | None = None, paid_by_boleto: bool = False
) -> list[dict[str, Any]]:
    """JSON schemas of the gated tools (see ``agentic_tool_names``)."""
    return [SCHEMAS_BY_NAME[name] for name in agentic_tool_names(stage, intent_group, paid_by_boleto)]


def tool_schemas(variant: str = "rag_policy") -> list[dict[str, Any]]:
    """Tools offered to the LLM: ``rag`` (pure agentic RAG) or ``rag_policy`` (+ rules engine)."""
    return TOOL_SCHEMAS + ([POLICY_TOOL] if variant == "rag_policy" else [])


def tool_names(variant: str = "rag_policy") -> list[str]:
    """Names of the tools of ``tool_schemas`` (same order)."""
    return [schema["function"]["name"] for schema in tool_schemas(variant)]


# Every tool an LLM may call (the ones AdvisorTools.call accepts), in a fixed order. The CallVerse MCP server
# publishes exactly these.
LLM_TOOL_NAMES = list(SCHEMAS_BY_NAME)


class DirectToolbox:
    """The LLM's tools as plain Python calls: the "direct" transport.

    The Advisor uses a toolbox for two things: the descriptions of the tools it offers the LLM
    (``schemas``) and running the tool the LLM chose (``execute``). McpToolbox (callverse/mcp/client.py)
    offers the same two methods but goes through the CallVerse MCP server.
    """

    transport = "direct"

    def __init__(self, tools: AdvisorTools) -> None:
        self.tools = tools

    def schemas(self, names: Iterable[str]) -> list[dict[str, Any]]:
        """The descriptions of these tools, in the order given."""
        return [SCHEMAS_BY_NAME[name] for name in names]

    def execute(self, name: str, arguments: dict[str, Any]) -> str:
        """Run the tool the LLM chose; returns its result as JSON text."""
        return self.tools.execute(name, arguments)

    def close(self) -> None:
        """Nothing to close (no connection)."""
