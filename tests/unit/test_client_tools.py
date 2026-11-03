"""Client agent tool: the customer's own "My orders" page (view_my_order_page).

A scripted LLM plays the customer, so each test controls what the "LLM" chooses and
checks what the code does around it: gating (when the page is offered), running the
tool on the customer's own order only, the mismatch flag and the customer's memory of
pages it opened earlier.
"""

import json
from dataclasses import dataclass, field
from typing import Any

import pytest

from callverse.agents.client.order_page import STATUS_LABEL, my_order_page, summarize_page
from callverse.agents.client.simulator import MAX_PAGE_CHECKS, ORDER_PAGE_TOOL, ClientAgent, page_checks
from callverse.llm import LLMResponse
from tests.conftest import requires_data

pytestmark = requires_data

TRACK_ORDER = "SC000014"  # track_order: "where is my order?"
CUSTOMER_FIELDS = {
    "order_id", "today", "status", "estimated_delivery", "delivered_on", "steps", "items",
    "amount_paid_brl", "payment",
}  # fmt: skip


@dataclass
class ScriptedCustomerLLM:
    """Plays a script: a step is a reply text or a list of (tool name, arguments) calls.
    Records what each call was offered, whether JSON was forced, and the chat it saw."""

    script: list[Any] = field(default_factory=list)
    offered: list[list[str]] = field(default_factory=list)
    json_mode: list[bool] = field(default_factory=list)
    chats: list[list[dict[str, Any]]] = field(default_factory=list)

    def available(self) -> bool:
        return True

    def resolve_model(self, role: str) -> str:
        return "scripted/customer"

    def chat(self, role: str, messages: list[dict[str, Any]], tools=None, **options: Any) -> LLMResponse:
        self.offered.append([t["function"]["name"] for t in tools or []])
        self.json_mode.append(bool(options.get("json_mode")))
        self.chats.append(list(messages))
        step = self.script.pop(0)
        if isinstance(step, str):
            return LLMResponse(step, [], "scripted/customer")
        return LLMResponse("", [{"name": n, "arguments": a} for n, a in step], "scripted/customer")


def answer(message: str, mismatch: bool | None = None, end: bool = False) -> str:
    return json.dumps({"message": message, "end": end, "csat": 4 if end else None, "mismatch": mismatch})


@pytest.fixture(scope="module")
def profile():
    from callverse.agents.client.profiles import profile_by_contact_id
    from callverse.data import loaders

    return profile_by_contact_id(loaders.contacts(), TRACK_ORDER)


def chat_until(profile, advisor_says: str) -> list[dict[str, Any]]:
    return [
        {"speaker": "customer", "text": profile.opening_message},
        {"speaker": "advisor", "text": "Could you give me your order number, please?"},
        {"speaker": "customer", "text": f"Sure, it is {profile.order_id}."},
        {"speaker": "advisor", "text": advisor_says},
    ]


# ------------------------------------------------------------------ the page itself
def test_order_page_shows_only_what_a_customer_sees(profile) -> None:
    page = my_order_page(profile.order_id, profile.contact_timestamp)
    assert page is not None and set(page) == CUSTOMER_FIELDS  # no internal flags or decisions
    assert page["order_id"] == profile.order_id and page["status"] in STATUS_LABEL.values()
    assert [s["step"] for s in page["steps"]][:2] == ["Order placed", "Payment approved"]
    assert page["today"] == profile.contact_timestamp.strftime("%Y-%m-%d")
    assert summarize_page(page).startswith(f"status: {page['status']}")


def test_unknown_order_has_no_page(profile) -> None:
    assert my_order_page("0" * 32, profile.contact_timestamp) is None
    assert summarize_page(None) == "order not found"


# ------------------------------------------------------------------ gating and tool use
def test_page_is_not_offered_when_the_advisor_states_nothing_checkable(profile) -> None:
    llm = ScriptedCustomerLLM([answer("Okay, thank you.")])
    messages = chat_until(profile, "Thank you for waiting, I am here to help.")
    turn = ClientAgent(llm, "llm").respond(profile, messages, 2)
    assert llm.offered == [[]] and llm.json_mode == [True]  # one plain JSON call, no tool
    assert turn.tool_calls == [] and turn.mismatch is None


def test_customer_opens_its_page_and_flags_a_mismatch(profile) -> None:
    events: list[tuple[str, dict]] = []
    llm = ScriptedCustomerLLM(
        [
            [(ORDER_PAGE_TOOL, {"order_id": "someone-else"})],  # Act: it opens the page
            answer("My order page does not say that, it is still with the carrier.", mismatch=True),
        ]
    )
    messages = chat_until(profile, "Your order was delivered on 2 March 2017.")
    turn = ClientAgent(llm, "llm").respond(profile, messages, 2, on_event=lambda s, d: events.append((s, d)))
    assert llm.offered == [[ORDER_PAGE_TOOL], []]  # offered first, then the answer is forced to JSON
    assert llm.json_mode == [False, True]
    [call] = turn.tool_calls
    assert call["name"] == ORDER_PAGE_TOOL and call["ok"] and call["caller"] == "llm"
    assert call["result"]["order_id"] == profile.order_id  # always its OWN order, whatever it asked
    assert turn.mismatch is True and turn.meta()["mismatch"] is True
    # The page reached the LLM as a tool result before it wrote its answer
    tool_messages = [m for m in llm.chats[1] if m["role"] == "tool"]
    assert len(tool_messages) == 1
    assert json.loads(tool_messages[0]["content"])["order_id"] == profile.order_id
    assert [step for step, _ in events] == ["offer", "tool"]
    assert "result" not in events[1][1] and events[1][1]["summary"].startswith("status:")


def test_customer_may_answer_without_opening_the_page(profile) -> None:
    llm = ScriptedCustomerLLM([answer("Great, thanks a lot!", end=True)])
    messages = chat_until(profile, "Your order is with the carrier, estimated delivery 13 March 2017.")
    turn = ClientAgent(llm, "llm").respond(profile, messages, 2)
    assert llm.offered == [[ORDER_PAGE_TOOL]]  # offered, not used: one call only
    assert turn.tool_calls == [] and turn.mismatch is None and turn.end and turn.csat == 4


def test_a_non_json_first_answer_is_asked_again_in_json(profile) -> None:
    llm = ScriptedCustomerLLM(["Okay thanks", answer("Okay, thanks.")])
    messages = chat_until(profile, "Your order is with the carrier.")
    turn = ClientAgent(llm, "llm").respond(profile, messages, 2)
    assert llm.json_mode == [False, True] and turn.text == "Okay, thanks."


def test_customer_remembers_its_page_and_stops_checking(profile) -> None:
    page = my_order_page(profile.order_id, profile.contact_timestamp)
    seen = {"name": ORDER_PAGE_TOOL, "arguments": {}, "ok": True, "result": page, "caller": "llm"}
    messages = chat_until(profile, "Your order is with the carrier.")
    for _ in range(MAX_PAGE_CHECKS):  # it already looked twice in this chat
        checked = {"speaker": "customer", "text": "Let me check.", "meta": {"mode": "llm", "tools": [seen]}}
        messages.insert(2, checked)
    assert len(page_checks(messages)) == MAX_PAGE_CHECKS
    llm = ScriptedCustomerLLM([answer("That matches my page, thanks.", mismatch=False)])
    turn = ClientAgent(llm, "llm").respond(profile, messages, 3)
    assert llm.offered == [[]]  # no third check
    assert sum(m["role"] == "tool" for m in llm.chats[0]) == MAX_PAGE_CHECKS  # but it remembers them
    assert "already opened" in llm.chats[0][0]["content"]
    assert turn.mismatch is False and "tools" not in turn.meta()
