"""Client agent: plays the customer in the twin (small, cheap LLM).

It opens with a real customer message, answers the advisor's questions (order
number), reacts to the answer according to its persona, may ask for a supervisor,
and fills a 1-5 satisfaction survey at the end (simulated CSAT).

Tool: like a real customer, it can open its own "My orders" page
(``view_my_order_page``) to check what the advisor says, and flags a mismatch.
It only sees what a customer sees (information asymmetry): never the advisor's
tools, tickets or decisions.

Without an LLM, a rule-based customer gives the same protocol (backup).
"""

import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import numpy as np

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
{page_note}
Reply with a JSON object: {{"message": "<your next chat message, 1-2 short sentences>",
"end": <true if your problem is handled or you want to leave>, "csat": <your satisfaction 1-5 if
end is true, else null>, "mismatch": <true if something the advisor said contradicts your order
page, false if it matches, null if you have not seen the page>}}.
If the advisor gives a clear answer with a next step, thank them and end. If the answer is vague,
wrong or you are {persona} and unhappy, say so (you may ask for a supervisor once)."""

PAGE_NOTE_OFFERED = """You can open your own "My orders" page with the tool view_my_order_page: it shows what
the store's app shows you (status, dates, amount paid). The advisor just told you something about your
order: if you want to check it, open the page before you answer. If the page says something different,
point it out politely in your message.
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
    r"deliver|ship|carrier|arriv|dispatch|transit|status|track|paid|payment|charge|amount|"
    r"cancel|refund|estimat|\b\d{4}-\d{2}-\d{2}\b|"
    r"\b\d{1,2} (?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)",
    re.I,
)
MAX_PAGE_CHECKS = 2  # a real customer looks once or twice per chat, not after every message


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
        return meta


def page_checks(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Order pages the customer already opened in this chat (from the transcript)."""
    return [
        call
        for m in messages
        if m["speaker"] == "customer"
        for call in (m.get("meta") or {}).get("tools", [])
        if call.get("name") == ORDER_PAGE_TOOL
    ]


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
    ) -> ClientTurn:
        """Answer the advisor's last message. ``on_event("tool", ...)`` reports each
        tool call as it runs (live UI)."""
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
                turn = self._llm_turn(profile, messages, on_event)
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

    def _llm_turn(
        self,
        profile: CustomerProfile,
        messages: list[dict[str, Any]],
        on_event: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> ClientTurn:
        """Reason -> (optional) act with the order page -> answer in JSON."""
        assert self.llm is not None
        offered = self.offers_page(profile, messages)
        seen = [c for c in page_checks(messages) if c.get("ok")]
        note = PAGE_NOTE_OFFERED if offered else (PAGE_NOTE_SEEN if seen else "")
        chat: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": CLIENT_SYSTEM.format(
                    situation=profile.situation_text(),
                    opening=profile.opening_message,
                    order_id=profile.order_id,
                    persona=profile.persona,
                    tone=profile.tone,
                    page_note=note,
                ),
            }
        ]
        for message in messages:  # roles are swapped: the model plays the customer
            if message["speaker"] == "customer":  # pages it opened before this message (its memory)
                for call in (message.get("meta") or {}).get("tools", []):
                    if call.get("name") == ORDER_PAGE_TOOL and call.get("ok"):
                        chat.extend(self._page_exchange(call["result"]))
            role = "assistant" if message["speaker"] == "customer" else "user"
            chat.append({"role": role, "content": str(message["text"])})

        responses, calls = [], []
        if offered:  # Reason: the LLM decides whether to open its page (tool_choice "auto")
            if on_event is not None:
                on_event("offer", {"offered": [ORDER_PAGE_TOOL], "model": self.llm.resolve_model("client")})
            first = self.llm.chat("client", chat, tools=[ORDER_PAGE_SCHEMA], agent="client", temperature=0.7)
            responses.append(first)
            if any(c["name"] == ORDER_PAGE_TOOL for c in first.tool_calls):
                call = self._open_page(profile, first.tool_calls[0].get("arguments") or {})
                calls.append(call)
                if on_event is not None:
                    on_event("tool", {k: v for k, v in call.items() if k != "result"})
                chat.extend(self._page_exchange(call["result"]))
        if not responses or calls or not self._parses(responses[-1]):
            # Answer (after reading the page, or when the first answer was not JSON)
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
        mismatch = data.get("mismatch")
        mismatch = bool(mismatch) if (calls or seen) and isinstance(mismatch, bool) else None
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
    def _page_exchange(page: dict[str, Any]) -> list[dict[str, Any]]:
        """The tool call and its result, in the chat format of the LLM layer."""
        call = {"function": {"name": ORDER_PAGE_TOOL, "arguments": {}}}
        return [
            {"role": "assistant", "content": "", "tool_calls": [call]},
            {"role": "tool", "content": json.dumps(page), "tool_name": ORDER_PAGE_TOOL},
        ]

    @staticmethod
    def _open_page(profile: CustomerProfile, arguments: dict[str, Any]) -> dict[str, Any]:
        """Run the tool. It always opens the customer's own order (arguments are ignored:
        the customer cannot look at someone else's order)."""
        started = time.perf_counter()
        page = my_order_page(profile.order_id, profile.contact_timestamp)
        result = page if page is not None else {"error": "order not found"}
        return {
            "name": ORDER_PAGE_TOOL,
            "arguments": dict(arguments),
            "ok": page is not None,
            "result": result,
            "caller": "llm",
            "summary": summarize_page(page),
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
        }
