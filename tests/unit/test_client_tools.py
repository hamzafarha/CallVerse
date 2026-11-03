"""Client agent tools: the customer's own "My orders" page (view_my_order_page) and
its chat timer (check_my_waiting_time).

A scripted LLM plays the customer, so each test controls what the "LLM" chooses and
checks what the code does around it: gating (when a tool is offered), running the
tools on the customer's own data only, the mismatch flag, the waiting-time arithmetic,
the KPIs and the customer's memory of tools it used earlier.
"""

import json
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import pytest

from callverse.agents.client.chat_clock import (
    ChatClock,
    persona_patience,
    queue_wait_from_twin,
    summarize_clock,
)
from callverse.agents.client.evidence import (
    BOX_DAMAGE,
    DAMAGE,
    EVIDENCE_KINDS,
    attachments_text,
    make_evidence,
)
from callverse.agents.client.order_page import STATUS_LABEL, my_order_page, summarize_page
from callverse.agents.client.simulator import (
    CLOCK_TOOL,
    EVIDENCE_TOOL,
    MAX_PAGE_CHECKS,
    ORDER_PAGE_TOOL,
    ClientAgent,
    page_checks,
)
from callverse.llm import LLMResponse
from tests.conftest import requires_data

pytestmark = requires_data

TRACK_ORDER = "SC000014"  # track_order: "where is my order?"
DAMAGED = "SC002632"  # damaged_delivery, delivered, paid by boleto
WRONG_ITEM = "SC008360"  # wrong_item, delivered
PAYMENT = "SC000004"  # payment_issue, not shipped yet
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
    schemas: list[list[dict[str, Any]]] = field(default_factory=list)
    json_mode: list[bool] = field(default_factory=list)
    choices: list[str | None] = field(default_factory=list)
    chats: list[list[dict[str, Any]]] = field(default_factory=list)

    def available(self) -> bool:
        return True

    def resolve_model(self, role: str) -> str:
        return "scripted/customer"

    def chat(self, role: str, messages: list[dict[str, Any]], tools=None, **options: Any) -> LLMResponse:
        self.offered.append([t["function"]["name"] for t in tools or []])
        self.schemas.append(list(tools or []))
        self.json_mode.append(bool(options.get("json_mode")))
        self.choices.append(options.get("tool_choice"))
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


# ------------------------------------------------------------------ waiting time
class FakeTime:
    """A wall clock the test moves by hand."""

    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


def test_chat_clock_adds_up_all_the_waiting() -> None:
    now = FakeTime()
    clock = ChatClock(patience_seconds=180, queue_wait_seconds=120, now=now)
    now.t += 10
    clock.answer_arrived()  # first answer after 10 s
    clock.customer_wrote()
    now.t += 60
    clock.answer_arrived()  # then the advisor took a minute
    reading = clock.reading()
    assert reading["waited_in_queue_seconds"] == 120 and reading["waited_for_last_answer_seconds"] == 60
    assert reading["total_wait_seconds"] == 190 and reading["over_my_patience"]
    assert "3 min 10 s in all" in reading["clock"]
    assert summarize_clock(reading) == "waited 3 min 10 s in all, patience 3 min 00 s: over my patience"


def test_patience_is_the_twins_persona_patience() -> None:
    normal = persona_patience("normal")
    assert persona_patience("impatient") == normal / 2 and persona_patience("patient") == normal * 2


def test_twin_queue_wait_is_the_erlang_c_wait() -> None:
    assert queue_wait_from_twin({"is_live": True, "expected_wait_seconds": 16.4}) == 16.4
    # Centre closed: like in the twin (no abandonment while closed), it uses no patience
    assert queue_wait_from_twin({"is_live": False, "expected_wait_seconds": None}) == 0.0


def test_timer_is_not_offered_while_the_wait_is_short(profile) -> None:
    now = FakeTime()
    patience = persona_patience(profile.persona)
    clock = ChatClock(patience, queue_wait_seconds=0.2 * patience, now=now)
    llm = ScriptedCustomerLLM([answer("Okay, thank you.")])
    messages = chat_until(profile, "Thank you for waiting, I am here to help.")
    ClientAgent(llm, "llm").respond(profile, messages, 2, clock=clock)
    assert llm.offered == [[]]
    assert clock.last_customer_at == now.t and len(clock.answer_waits) == 1  # the clock still runs


def test_customer_checks_its_timer_and_leaves_out_of_patience(profile) -> None:
    now = FakeTime()
    patience = persona_patience(profile.persona)
    clock = ChatClock(patience, queue_wait_seconds=0.8 * patience, now=now)
    now.t += 0.4 * patience  # and the advisor is slow to answer
    events: list[tuple[str, dict]] = []
    llm = ScriptedCustomerLLM([[(CLOCK_TOOL, {})], answer("I have waited far too long, goodbye.", end=True)])
    messages = chat_until(profile, "Thank you for waiting, I am here to help.")
    turn = ClientAgent(llm, "llm").respond(
        profile, messages, 2, on_event=lambda s, d: events.append((s, d)), clock=clock
    )
    assert llm.offered == [[CLOCK_TOOL], []]
    assert llm.choices[0] == "required"  # patience just ran out: it must look at the timer
    assert CLOCK_TOOL in llm.chats[0][0]["content"]  # the system prompt explains the tool
    [call] = turn.tool_calls
    assert call["name"] == CLOCK_TOOL and call["ok"] and call["caller"] == "llm"
    assert call["result"]["over_my_patience"] and call["result"]["total_wait_seconds"] == round(
        1.2 * patience
    )
    assert turn.end and turn.meta()["end"] is True and turn.mismatch is None
    assert [step for step, _ in events] == ["offer", "tool"] and events[0][1]["offered"] == [CLOCK_TOOL]
    assert events[0][1]["tool_choice"] == "required"


def test_timer_is_optional_before_patience_runs_out_and_required_only_once(profile) -> None:
    now = FakeTime()
    patience = persona_patience(profile.persona)
    messages = chat_until(profile, "Thank you for waiting, I am here to help.")
    # Between half and all of its patience: offered, the LLM may ignore it
    clock = ChatClock(patience, queue_wait_seconds=0.6 * patience, now=now)
    llm = ScriptedCustomerLLM([answer("Okay.")])
    ClientAgent(llm, "llm").respond(profile, messages, 2, clock=clock)
    assert llm.offered == [[CLOCK_TOOL]] and llm.choices == [None]
    # Past its patience but it already looked once: offered again, not required
    seen = {"name": CLOCK_TOOL, "ok": True, "result": {"over_my_patience": True}, "caller": "llm"}
    looked = {"speaker": "customer", "text": "Still waiting!", "meta": {"mode": "llm", "tools": [seen]}}
    clock = ChatClock(patience, queue_wait_seconds=2 * patience, now=now)
    llm = ScriptedCustomerLLM([answer("Okay.")])
    ClientAgent(llm, "llm").respond(profile, [*messages[:3], looked, messages[3]], 3, clock=clock)
    assert llm.offered == [[CLOCK_TOOL]] and llm.choices == [None]


def test_both_tools_can_be_offered_in_the_same_turn(profile) -> None:
    patience = persona_patience(profile.persona)
    clock = ChatClock(patience, queue_wait_seconds=patience, now=FakeTime())
    llm = ScriptedCustomerLLM(
        [
            [(ORDER_PAGE_TOOL, {}), (CLOCK_TOOL, {}), (CLOCK_TOOL, {})],  # asks the timer twice
            answer("Finally! But my page does not say that.", mismatch=True),
        ]
    )
    messages = chat_until(profile, "Your order was delivered on 2 March 2017.")
    turn = ClientAgent(llm, "llm").respond(profile, messages, 2, clock=clock)
    assert llm.offered[0] == [ORDER_PAGE_TOOL, CLOCK_TOOL] and llm.choices[0] == "required"
    assert [c["name"] for c in turn.tool_calls] == [ORDER_PAGE_TOOL, CLOCK_TOOL]  # each tool once per turn
    assert sum(m["role"] == "tool" for m in llm.chats[1]) == 2 and turn.mismatch is True


def test_kpis_count_timer_checks_and_customers_who_left_waiting(profile) -> None:
    from callverse.orchestration.graph import kpi_row

    timer = {"name": CLOCK_TOOL, "ok": True, "result": {"over_my_patience": True}, "caller": "llm"}
    left = {
        "speaker": "customer",
        "text": "Too slow, bye.",
        "meta": {"mode": "llm", "tools": [timer], "end": True},
    }
    messages = [*chat_until(profile, "Thank you for waiting."), left]
    session = SimpleNamespace(profile=profile, memory=SimpleNamespace(handed_to=None, outcome=None))
    card = {"judge": "rules", "resolved": False, "scores": {"compliance": 5}, "correct": False}
    row = kpi_row(session, messages, {}, card, 1, {})
    assert row["customer_wait_checks"] == 1 and row["customer_left_waiting"] is True
    assert row["customer_page_checks"] == 0 and row["customer_evidence_sent"] == 0


# ------------------------------------------------------------------ evidence
def customer(contact_id: str):
    from callverse.agents.client.profiles import profile_by_contact_id
    from callverse.data import loaders

    return profile_by_contact_id(loaders.contacts(), contact_id)


def enum_offered(llm: ScriptedCustomerLLM, call: int = 0) -> list[str]:
    schema = next(t for t in llm.schemas[call] if t["function"]["name"] == EVIDENCE_TOOL)
    return schema["function"]["parameters"]["properties"]["kinds"]["items"]["enum"]


def test_evidence_matches_the_customers_real_order() -> None:
    damaged = customer(DAMAGED)
    photo = make_evidence("product_photo", damaged)
    assert photo["label"] == EVIDENCE_KINDS["product_photo"] and photo["simulated"]
    assert any(d in photo["description"] for d in DAMAGE)  # its real problem: a damaged item
    assert any(d in make_evidence("packaging_photo", damaged)["description"] for d in BOX_DAMAGE)
    assert damaged.order_id[:8] in make_evidence("shipping_label_photo", damaged)["description"]
    assert make_evidence("payment_statement", damaged)["description"].startswith("boleto of R$ 94.31")
    wrong = make_evidence("product_photo", customer(WRONG_ITEM))
    assert "different product" in wrong["description"]
    assert make_evidence("product_photo", damaged) == photo  # same customer, same file


def test_evidence_that_cannot_exist_is_refused() -> None:
    not_delivered = customer(TRACK_ORDER)
    assert "not received" in make_evidence("product_photo", not_delivered)["error"]
    assert "not been shipped" in make_evidence("shipping_label_photo", customer(PAYMENT))["error"]
    assert "unknown kind" in make_evidence("selfie", not_delivered)["error"]


def test_evidence_is_offered_only_when_the_advisor_asks_for_proof() -> None:
    damaged = customer(DAMAGED)
    llm = ScriptedCustomerLLM([answer("Okay, thank you.")])
    ClientAgent(llm, "llm").respond(damaged, chat_until(damaged, "I am sorry about this."), 2)
    assert llm.offered == [[]]


def test_customer_sends_the_photos_it_was_asked_for() -> None:
    damaged = customer(DAMAGED)
    events: list[tuple[str, dict]] = []
    # One call selects several files, like a phone's photo picker (the same file twice: sent once)
    files = ["product_photo", "packaging_photo", "shipping_label_photo", "product_photo"]
    llm = ScriptedCustomerLLM(
        [
            [(EVIDENCE_TOOL, {"kinds": files})],
            answer("Here are the photos of the product, the box and the label."),
        ]
    )
    ask = "Please reply with photos of the product, the packaging and the shipping label."
    messages = chat_until(damaged, ask)
    turn = ClientAgent(llm, "llm").respond(damaged, messages, 2, on_event=lambda s, d: events.append((s, d)))
    assert llm.offered == [[EVIDENCE_TOOL], []] and enum_offered(llm) == list(EVIDENCE_KINDS)
    assert [a["kind"] for a in turn.attachments] == files[:3]
    assert turn.meta()["attachments"] == turn.attachments
    assert sum(m["role"] == "tool" for m in llm.chats[1]) == 1  # it read what was attached
    assert [step for step, _ in events] == ["offer", "tool"]
    assert events[1][1]["summary"] == "sent 3 files (product, packaging, shipping label)"

    # Next request: only the file not sent yet is offered; a file sent before is refused
    sent = {"speaker": "customer", "text": turn.text, "meta": turn.meta()}
    statement = "Thanks! Could you also send a screenshot of the statement line?"
    messages += [sent, {"speaker": "advisor", "text": statement}]
    kinds = ["product_photo", "payment_statement"]
    llm = ScriptedCustomerLLM([[(EVIDENCE_TOOL, {"kinds": kinds})], answer("Here is the screenshot.")])
    turn = ClientAgent(llm, "llm").respond(damaged, messages, 3)
    assert enum_offered(llm) == ["payment_statement"]
    [call] = turn.tool_calls
    assert (
        call["ok"] and call["result"]["refused"][0]["error"] == "you already sent your photo of the product"
    )
    assert [a["kind"] for a in turn.attachments] == ["payment_statement"]


def test_a_file_that_cannot_exist_is_refused_in_the_tool_result() -> None:
    not_delivered = customer(TRACK_ORDER)
    llm = ScriptedCustomerLLM(
        [[(EVIDENCE_TOOL, {"kinds": ["product_photo"]})], answer("I have not received it.")]
    )
    messages = chat_until(not_delivered, "Could you send a photo of the product?")
    turn = ClientAgent(llm, "llm").respond(not_delivered, messages, 2)
    [call] = turn.tool_calls
    assert not call["ok"] and turn.attachments == [] and "attachments" not in turn.meta()
    assert (
        "not received"
        in json.loads(next(m for m in llm.chats[1] if m["role"] == "tool")["content"])["refused"][0]["error"]
    )  # the LLM read why, so it can tell the advisor


def test_advisor_and_judge_read_the_attachments_and_the_template_thanks() -> None:
    from callverse.orchestration.graph import advisor_message, kpi_row, make_session
    from callverse.orchestration.runtime import AgentRuntime

    damaged = customer(DAMAGED)
    files = [make_evidence("product_photo", damaged), make_evidence("packaging_photo", damaged)]
    sent = {"speaker": "customer", "text": "Here you are.", "meta": {"mode": "llm", "attachments": files}}
    seen = attachments_text(sent)  # what the advisor's LLM and the judge read
    assert seen.startswith("Here you are.\n[Attached photo of the product (IMG_")
    assert files[1]["description"] in seen

    session = make_session(damaged, mode="template", runtime=AgentRuntime(retriever_kind="keyword"))
    messages = [
        {"speaker": "customer", "text": damaged.opening_message},
        {"speaker": "advisor", "text": "Could you give me your order number, please?"},
        {"speaker": "customer", "text": f"Sure, it is {damaged.order_id}."},
    ]
    messages.append(advisor_message(session.advisor.reply(messages, session.memory, session.tools)))
    messages.append(sent)
    thanks = session.advisor.reply(messages, session.memory, session.tools)  # offline backup advisor
    assert thanks.stage == "evidence"
    assert "received your photo of the product and photo of the packaging" in thanks.text

    card = {"judge": "rules", "resolved": True, "scores": {"compliance": 5}, "correct": True}
    assert kpi_row(session, messages, {}, card, 4, {})["customer_evidence_sent"] == 2
