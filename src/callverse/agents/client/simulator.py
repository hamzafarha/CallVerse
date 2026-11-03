"""Client agent: plays the customer in the twin (small, cheap LLM).

It opens with a real customer message, answers the advisor's questions (order
number), reacts to the answer according to its persona, may ask for a supervisor,
and fills a 1-5 satisfaction survey at the end (simulated CSAT).

Tools: like a real customer, it can open its own "My orders" page
(``view_my_order_page``) to check what the advisor says, and flag a mismatch; and
look at its chat timer (``check_my_waiting_time``) when the wait gets long, to react
like its persona (complain, leave); and attach photos or a statement screenshot
(``send_evidence``) when the advisor asks for proof. It only sees what a customer sees
(information asymmetry): never the advisor's tools, tickets or decisions.

Without an LLM, a rule-based customer gives the same protocol (backup).
"""

import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from callverse.agents.client.chat_clock import ChatClock, summarize_clock
from callverse.agents.client.evidence import EVIDENCE_KINDS, send_files, summarize_evidence
from callverse.agents.client.order_page import my_order_page, summarize_page
from callverse.agents.client.profiles import CustomerProfile
from callverse.data.conversations import (
    BANK_CODE_CORRECTIONS,
    BANK_CODE_QUESTIONS,
    GOODBYES,
    REACTIONS,
    SUPERVISOR_REQUESTS,
    VERIFY_REPLIES,
)
from callverse.llm import LLMClient, LLMUnavailableError

ASKS_FOR_ORDER = re.compile(r"order (number|id|no)|which order|order #|confirm your order", re.I)
# Boleto refund: the advisor asks for bank details (sent by e-mail), or rejects a bank code
ASKS_FOR_BANK = re.compile(r"bank details|bank, branch|bank code|bank account details", re.I)
BANK_CODE_PROBLEM = re.compile(
    r"could not find|couldn't find|not (?:a )?valid|invalid|not found|does ?n[o']t exist|"
    r"check (?:the|your|that|this) (?:bank )?code|3 digits|three digits",
    re.I,
)
ASKS_ANYTHING_ELSE = re.compile(r"anything else|help you with anything|can i help", re.I)
NEGATIVE = re.compile(
    r"sorry|unfortunately|cannot|can't|unable|no longer|late|investigation|"
    r"passed|not (yet )?arrived|delay",
    re.I,
)

# Phrases only an advisor would write (role-swap guardrail of the simulated customer)
ADVISOR_VOICE = re.compile(
    r"(how (can|may) i (help|assist)|anything else i can|assist you|i can help you|"
    r"feel free to (ask|reach)|let me (check|look)|happy to help)",
    re.I,
)

CLIENT_SYSTEM = """You are role-playing a CUSTOMER chatting with an online store's support advisor.
Stay in character. Never act as the advisor. Always write in English.
Talk TO the advisor in the first person ("I", "you"), never about "the advisor" or "the customer".

Your situation: {situation}
Your original request was: "{opening}"
Your order number is {order_id} (give it when asked).
Your personality: {persona} - {tone}.

Reply with a JSON object: {{"message": "<your next chat message, 1-2 short sentences>",
"end": <true if your problem is handled or you want to leave>, "csat": <your satisfaction 1-5 if
end is true, else null>, "mismatch": <true if something the advisor said contradicts your order
page, false if it matches, null if you have not seen the page>}}.
If the advisor gives a clear answer with a next step, thank them and end. If the answer is vague,
wrong or you are {persona} and unhappy, say so (you may ask for a supervisor once).
{tool_notes}"""

PAGE_NOTE_OFFERED = """You can open your own "My orders" page with the tool view_my_order_page: it shows what
the store's app shows you (status, dates, amount paid). The advisor just told you something about your
order: if you want to check it, open the page before you answer. If the page says something different,
tell the advisor politely, for example: "My order page says ..., but you told me ...".
"""
PAGE_NOTE_SEEN = """You already opened your "My orders" page in this chat (see the tool result). If the
advisor says something different from it, point it out politely in your message.
"""

# The Client agent's tool: no arguments, it can only open *its own* order page
ORDER_PAGE_TOOL = "view_my_order_page"
ORDER_PAGE_SCHEMA = {
    "type": "function",
    "function": {
        "name": ORDER_PAGE_TOOL,
        "description": (
            "Open your own 'My orders' page in the store's app: order status, the steps (placed, "
            "paid, shipped, delivered) with their dates, the estimated delivery date and the amount "
            "you paid. Use it to check what the advisor tells you about your order."
        ),
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}
# Gating: the page is offered only when the advisor just said something it can confirm
CHECKABLE = re.compile(
    r"deliver|ship(?!ping label)|carrier|arriv|dispatch|transit|status|track|paid|payment|charge|amount|"
    r"cancel|refund|estimat|\b\d{4}-\d{2}-\d{2}\b|"
    r"\b\d{1,2} (?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)",
    re.I,
)
MAX_PAGE_CHECKS = 2  # a real customer looks once or twice per chat, not after every message

CLOCK_NOTE_OFFERED = """This chat feels long: you have been waiting a lot. Before you answer, check how long
exactly with the tool check_my_waiting_time (the timer of your chat, with your own patience). If you
waited longer than your patience, say it in your message (for example: "I have been waiting for 5
minutes!") and react as your personality would: complain, or leave the chat (end=true) if you are fed up.
Never quote your patience as a number.
"""

# Second tool: the timer of the chat window (waits from the digital twin or the real clock)
CLOCK_TOOL = "check_my_waiting_time"
CLOCK_SCHEMA = {
    "type": "function",
    "function": {
        "name": CLOCK_TOOL,
        "description": (
            "Look at the timer of your chat window: how long you waited in the queue and for the "
            "advisor's answer, compared with your own patience."
        ),
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}
CLOCK_GATE = 0.5  # gating: offered once the wait reaches half the customer's patience
MAX_CLOCK_CHECKS = 2

EVIDENCE_NOTE_OFFERED = """The advisor asked you for proof. You can attach files to your message with the tool
send_evidence: select in ONE call every file the advisor asked for (for example the product, the
packaging and the label), like choosing several photos on your phone. Then say in your message only
what was really attached. If a file was refused, tell the advisor why.
"""

# Third tool: attach a photo or a statement screenshot (content built from the real order)
EVIDENCE_TOOL = "send_evidence"
# Gating: offered when the advisor asks for photos, a screenshot or a receipt
ASKS_FOR_EVIDENCE = re.compile(
    r"\b(photos?|pictures?|images?|screenshots?|receipts?|proof|attach\w*|videos?)\b"
    r"|shipping label|statement line",
    re.I,
)


def evidence_schema(kinds: list[str]) -> dict[str, Any]:
    """The tool, offering only the files not sent yet (the list shrinks as files go)."""
    return {
        "type": "function",
        "function": {
            "name": EVIDENCE_TOOL,
            "description": (
                "Attach photos or a screenshot from your phone to your next message. Select every "
                "file you want to send in one call: product_photo (the product as you received it), "
                "packaging_photo (the box), shipping_label_photo (the label on the parcel), "
                "payment_statement (the line on your bank or card statement)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "kinds": {
                        "type": "array",
                        "items": {"type": "string", "enum": kinds},
                        "description": "The files to attach",
                    }
                },
                "required": ["kinds"],
            },
        },
    }


CUSTOMER_TOOLS = {ORDER_PAGE_TOOL, CLOCK_TOOL, EVIDENCE_TOOL}


@dataclass
class ClientTurn:
    """One customer message (or the end of the chat)."""

    text: str
    end: bool
    csat: int | None
    mode: str
    model: str | None = None
    latency_ms: float = 0.0
    tokens: int = 0
    # Tools the customer used this turn (same fields as the advisor's, for the UI and KPIs)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    # True: the advisor said something its order page contradicts (None: page not seen)
    mismatch: bool | None = None

    def meta(self) -> dict[str, Any]:
        """Message metadata for the transcript."""
        meta: dict[str, Any] = {"mode": self.mode}
        if self.tool_calls:
            meta["tools"] = self.tool_calls
        if self.mismatch is not None:
            meta["mismatch"] = self.mismatch
        if self.attachments:
            meta["attachments"] = self.attachments
        if self.end:
            meta["end"] = True  # the customer left (KPI: did it leave out of patience?)
        return meta

    @property
    def attachments(self) -> list[dict[str, Any]]:
        """Files sent with this message (by its send_evidence calls)."""
        return [
            f for c in self.tool_calls if c["name"] == EVIDENCE_TOOL for f in c["result"].get("attached", [])
        ]


def tool_checks(messages: list[dict[str, Any]], name: str) -> list[dict[str, Any]]:
    """Calls of one customer tool earlier in this chat (from the transcript)."""
    return [
        call
        for m in messages
        if m["speaker"] == "customer"
        for call in (m.get("meta") or {}).get("tools", [])
        if call.get("name") == name
    ]


def page_checks(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Order pages the customer already opened in this chat."""
    return tool_checks(messages, ORDER_PAGE_TOOL)


def sent_evidence(messages: list[dict[str, Any]]) -> set[str]:
    """Kinds of files the customer already sent in this chat."""
    calls = tool_checks(messages, EVIDENCE_TOOL)
    return {f["kind"] for c in calls for f in (c.get("result") or {}).get("attached", [])}


def advisor_answers(messages: list[dict[str, Any]]) -> int:
    return sum(m["speaker"] == "advisor" for m in messages)


class ClientAgent:
    """Simulated customer (LLM with rule-based fallback)."""

    def __init__(
        self, llm: LLMClient | None = None, mode: str = "auto", seed: int = 0, max_turns: int = 4
    ) -> None:
        self.llm = llm
        self.mode = mode
        self.rng = np.random.default_rng(seed)
        self.max_turns = max_turns

    def use_llm(self) -> bool:
        if self.mode == "template" or self.llm is None:
            return False
        return self.mode == "llm" or self.llm.available()

    def opening(self, profile: CustomerProfile) -> ClientTurn:
        """First message: the real customer message of the contact."""
        return ClientTurn(profile.opening_message, False, None, "history")

    def respond(
        self,
        profile: CustomerProfile,
        messages: list[dict[str, Any]],
        customer_turns: int,
        on_event: Callable[[str, dict[str, Any]], None] | None = None,
        clock: ChatClock | None = None,
    ) -> ClientTurn:
        """Answer the advisor's last message. ``on_event("tool", ...)`` reports each
        tool call as it runs (live UI); ``clock`` times the chat (waiting-time tool)."""
        if clock is not None:
            clock.answer_arrived()
        turn = self._respond(profile, messages, customer_turns, on_event, clock)
        if clock is not None:
            clock.customer_wrote()
        return turn

    def _respond(
        self,
        profile: CustomerProfile,
        messages: list[dict[str, Any]],
        customer_turns: int,
        on_event: Callable[[str, dict[str, Any]], None] | None,
        clock: ChatClock | None,
    ) -> ClientTurn:
        if customer_turns >= self.max_turns:
            return ClientTurn(self._pick(GOODBYES), True, self._survey(profile, messages), "rule")
        given = profile.order_id in " ".join(str(m["text"]) for m in messages if m["speaker"] == "customer")
        if not given and ASKS_FOR_ORDER.search(str(messages[-1]["text"])):
            # Guardrail: verification data is always given deterministically (small models
            # sometimes swap roles and ask the advisor for *its* order number).
            reply = self._pick(VERIFY_REPLIES).format(order_id=profile.order_id)
            return ClientTurn(reply, False, None, "rule")
        bank_turn = self._bank_turn(profile, messages)
        if bank_turn is not None:
            return bank_turn
        if self.use_llm():
            try:
                turn = self._llm_turn(profile, messages, on_event, clock)
                if ADVISOR_VOICE.search(turn.text):
                    # Guardrail: a small model sometimes starts speaking as the advisor.
                    raise ValueError("role swap")
                return turn
            except (LLMUnavailableError, ValueError):
                pass
        return self._rule_turn(profile, messages)

    def _bank_turn(self, profile: CustomerProfile, messages: list[dict[str, Any]]) -> ClientTurn | None:
        """Guardrail: bank codes are given deterministically, like the order number. The
        customer checks the code in the chat (the rest goes by e-mail) and corrects a typo
        when the advisor says the code does not exist."""
        if not profile.bank_code:
            return None
        last = str(messages[-1]["text"])
        said = " ".join(str(m["text"]) for m in messages if m["speaker"] == "customer")
        if ASKS_FOR_BANK.search(last) and not re.search(rf"\b{profile.bank_code_typed}\b", said):
            text = self._pick(BANK_CODE_QUESTIONS).format(code=profile.bank_code_typed)
            return ClientTurn(text, False, None, "rule")
        if (
            profile.bank_code_typed != profile.bank_code
            and BANK_CODE_PROBLEM.search(last)
            and not re.search(rf"\b{profile.bank_code}\b", said)
        ):
            text = self._pick(BANK_CODE_CORRECTIONS).format(code=profile.bank_code)
            return ClientTurn(text, False, None, "rule")
        return None

    # ---------------------------------------------------------------- rule mode
    def _pick(self, options: list[str]) -> str:
        return options[int(self.rng.integers(len(options)))]

    def _rule_turn(self, profile: CustomerProfile, messages: list[dict[str, Any]]) -> ClientTurn:
        last = str(messages[-1]["text"])
        if ASKS_FOR_ORDER.search(last) and profile.order_id not in " ".join(
            str(m["text"]) for m in messages if m["speaker"] == "customer"
        ):
            return ClientTurn(
                self._pick(VERIFY_REPLIES).format(order_id=profile.order_id), False, None, "rule"
            )
        if ASKS_ANYTHING_ELSE.search(last):
            return ClientTurn(self._pick(GOODBYES), True, self._survey(profile, messages), "rule")
        bad_news = bool(NEGATIVE.search(last))
        already_asked = any(
            "supervisor" in str(m["text"]).lower() for m in messages if m["speaker"] == "customer"
        )
        if bad_news and profile.persona == "impatient" and not already_asked and self.rng.random() < 0.35:
            return ClientTurn(self._pick(SUPERVISOR_REQUESTS), False, None, "rule")
        reaction = REACTIONS["follow_up" if bad_news else "resolved_in_chat"]
        return ClientTurn(self._pick(reaction), False, None, "rule")

    def _survey(self, profile: CustomerProfile, messages: list[dict[str, Any]]) -> int:
        """Post-chat CSAT (1-5): depends on the answer and the persona."""
        advisor_text = " ".join(str(m["text"]) for m in messages if m["speaker"] == "advisor")
        escalated = "supervisor" in advisor_text.lower()
        bad_news = bool(NEGATIVE.search(advisor_text))
        base = 4.4 - 1.0 * bad_news - 1.2 * escalated
        base += {"impatient": -0.6, "normal": 0.0, "patient": 0.4}.get(profile.persona, 0.0)
        return int(np.clip(round(base + self.rng.normal(0, 0.7)), 1, 5))

    # ----------------------------------------------------------------- LLM mode
    def offers_page(self, profile: CustomerProfile, messages: list[dict[str, Any]]) -> bool:
        """Gating: the order page is offered when the advisor just said something it can
        confirm (a status, a date, an amount), at most ``MAX_PAGE_CHECKS`` times per chat."""
        last = messages[-1] if messages else {}
        return (
            bool(profile.order_id)
            and last.get("speaker") == "advisor"
            and bool(CHECKABLE.search(str(last.get("text", ""))))
            and len(page_checks(messages)) < MAX_PAGE_CHECKS
        )

    def offers_clock(self, messages: list[dict[str, Any]], clock: ChatClock | None) -> bool:
        """Gating: the timer is offered once the customer's waiting reaches half its
        patience, at most ``MAX_CLOCK_CHECKS`` times per chat."""
        return (
            clock is not None
            and bool(messages)
            and messages[-1]["speaker"] == "advisor"
            and clock.total_wait_seconds >= CLOCK_GATE * clock.patience_seconds
            and len(tool_checks(messages, CLOCK_TOOL)) < MAX_CLOCK_CHECKS
        )

    def offers_evidence(self, messages: list[dict[str, Any]]) -> list[str]:
        """Gating: the kinds of files offered (empty: tool not offered). Only when the advisor
        just asked for proof, and only files not sent yet."""
        last = messages[-1] if messages else {}
        if last.get("speaker") != "advisor" or not ASKS_FOR_EVIDENCE.search(str(last.get("text", ""))):
            return []
        sent = sent_evidence(messages)
        return [kind for kind in EVIDENCE_KINDS if kind not in sent]

    def patience_ran_out(self, messages: list[dict[str, Any]], clock: ChatClock | None) -> bool:
        """The wait just went past the customer's patience and it has not looked yet."""
        return (
            self.offers_clock(messages, clock)
            and clock is not None
            and clock.total_wait_seconds >= clock.patience_seconds
            and not tool_checks(messages, CLOCK_TOOL)
        )

    def _llm_turn(
        self,
        profile: CustomerProfile,
        messages: list[dict[str, Any]],
        on_event: Callable[[str, dict[str, Any]], None] | None = None,
        clock: ChatClock | None = None,
    ) -> ClientTurn:
        """Reason -> (optional) act with its tools -> answer in JSON."""
        assert self.llm is not None
        kinds = self.offers_evidence(messages)
        offered = (
            ([ORDER_PAGE_SCHEMA] if self.offers_page(profile, messages) else [])
            + ([CLOCK_SCHEMA] if self.offers_clock(messages, clock) else [])
            + ([evidence_schema(kinds)] if kinds else [])
        )
        names = [t["function"]["name"] for t in offered]
        seen = [c for c in page_checks(messages) if c.get("ok")]
        notes = [PAGE_NOTE_OFFERED if ORDER_PAGE_TOOL in names else (PAGE_NOTE_SEEN if seen else "")]
        notes.append(CLOCK_NOTE_OFFERED if CLOCK_TOOL in names else "")
        notes.append(EVIDENCE_NOTE_OFFERED if EVIDENCE_TOOL in names else "")
        chat: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": CLIENT_SYSTEM.format(
                    situation=profile.situation_text(),
                    opening=profile.opening_message,
                    order_id=profile.order_id,
                    persona=profile.persona,
                    tone=profile.tone,
                    tool_notes="".join(notes),
                ),
            }
        ]
        for message in messages:  # roles are swapped: the model plays the customer
            if message["speaker"] == "customer":  # tools it used before this message (its memory)
                for call in (message.get("meta") or {}).get("tools", []):
                    if call.get("name") in CUSTOMER_TOOLS and call.get("ok"):
                        chat.extend(self._tool_exchange(call["name"], call["result"]))
            role = "assistant" if message["speaker"] == "customer" else "user"
            chat.append({"role": role, "content": str(message["text"])})

        responses, calls = [], []
        if offered:  # Reason: the LLM decides which tools, if any, to use
            # A tool call is required once, when the wait first goes past the customer's patience
            # (a timer blinking red is hard to miss); the LLM still chooses which offered tool.
            # Otherwise tool_choice is "auto": the LLM may answer without any tool.
            choice = "required" if self.patience_ran_out(messages, clock) else None
            if on_event is not None:
                model = self.llm.resolve_model("client")
                on_event("offer", {"offered": names, "model": model, "tool_choice": choice})
            first = self.llm.chat(
                "client", chat, tools=offered, agent="client", temperature=0.7, tool_choice=choice
            )
            responses.append(first)
            sent = sent_evidence(messages)  # grows as files go: each file is sent once
            for request in first.tool_calls:  # Act: each tool runs at most once per turn
                if request["name"] not in names or any(c["name"] == request["name"] for c in calls):
                    continue
                arguments = dict(request.get("arguments") or {})
                call = self._run_tool(request["name"], profile, clock, arguments, sent)
                calls.append(call)
                if on_event is not None:
                    on_event("tool", {k: v for k, v in call.items() if k != "result"})
                chat.extend(self._tool_exchange(call["name"], call["result"]))
        if not responses or calls or not self._parses(responses[-1]):
            # Answer (after reading the tool results, or when the first answer was not JSON)
            responses.append(self.llm.chat("client", chat, json_mode=True, agent="client", temperature=0.7))
        data = responses[-1].json()
        text = str(data.get("message", "")).strip()
        if not text:
            raise ValueError("empty customer message")
        end = bool(data.get("end", False))
        csat = data.get("csat")
        csat = (
            int(np.clip(int(csat), 1, 5))
            if end and csat not in (None, "")
            else (self._survey(profile, messages + [{"speaker": "customer", "text": text}]) if end else None)
        )
        page_now = any(c["name"] == ORDER_PAGE_TOOL and c["ok"] for c in calls)
        mismatch = data.get("mismatch")
        mismatch = bool(mismatch) if (page_now or seen) and isinstance(mismatch, bool) else None
        return ClientTurn(
            text,
            end,
            csat,
            "llm",
            responses[-1].model,
            sum(r.latency_ms for r in responses),
            sum(r.prompt_tokens + r.completion_tokens for r in responses),
            calls,
            mismatch,
        )

    @staticmethod
    def _parses(response: Any) -> bool:
        try:
            return bool(str(response.json().get("message", "")).strip())
        except ValueError:
            return False

    @staticmethod
    def _tool_exchange(name: str, result: dict[str, Any]) -> list[dict[str, Any]]:
        """The tool call and its result, in the chat format of the LLM layer."""
        call = {"function": {"name": name, "arguments": {}}}
        return [
            {"role": "assistant", "content": "", "tool_calls": [call]},
            {"role": "tool", "content": json.dumps(result), "tool_name": name},
        ]

    @staticmethod
    def _run_tool(
        name: str,
        profile: CustomerProfile,
        clock: ChatClock | None,
        arguments: dict[str, Any],
        sent: set[str] | None = None,
    ) -> dict[str, Any]:
        """Run a customer tool. The order page and the timer take no arguments: the customer
        can only open its own (any argument the LLM invents is ignored). ``send_evidence``
        takes the kind of file; the content always comes from the customer's real order."""
        started = time.perf_counter()
        if name == ORDER_PAGE_TOOL:
            page = my_order_page(profile.order_id, profile.contact_timestamp)
            ok, result, summary = page is not None, page or {"error": "order not found"}, summarize_page(page)
        elif name == EVIDENCE_TOOL:
            kinds = arguments.get("kinds", arguments.get("kind"))
            result = send_files(kinds, profile, sent or set())
            ok, summary = bool(result["attached"]), summarize_evidence(result)
        else:
            assert clock is not None  # only offered with a clock
            result = clock.reading()
            ok, summary = True, summarize_clock(result)
        return {
            "name": name,
            "arguments": dict(arguments),
            "ok": ok,
            "result": result,
            "caller": "llm",
            "summary": summary,
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
        }
