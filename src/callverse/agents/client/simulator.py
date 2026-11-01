"""Client agent: plays the customer in the twin (small, cheap LLM).

It opens with a real customer message, answers the advisor's questions (order
number), reacts to the answer according to its persona, may ask for a supervisor,
and fills a 1-5 satisfaction survey at the end (simulated CSAT).

Without Ollama, a rule-based customer gives the same protocol (backup).
"""

import re
from dataclasses import dataclass
from typing import Any

import numpy as np

from callverse.agents.client.profiles import CustomerProfile
from callverse.data.conversations import GOODBYES, REACTIONS, SUPERVISOR_REQUESTS, VERIFY_REPLIES
from callverse.llm import LLMClient, LLMUnavailableError

ASKS_FOR_ORDER = re.compile(r"order (number|id|no)|which order|order #|confirm your order", re.I)
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

Your situation: {situation}
Your original request was: "{opening}"
Your order number is {order_id} (give it when asked).
Your personality: {persona} - {tone}.

Reply with a JSON object: {{"message": "<your next chat message, 1-2 short sentences>",
"end": <true if your problem is handled or you want to leave>, "csat": <your satisfaction 1-5 if
end is true, else null>}}.
If the advisor gives a clear answer with a next step, thank them and end. If the answer is vague,
wrong or you are {persona} and unhappy, say so (you may ask for a supervisor once)."""


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
        self, profile: CustomerProfile, messages: list[dict[str, Any]], customer_turns: int
    ) -> ClientTurn:
        """Answer the advisor's last message."""
        if customer_turns >= self.max_turns:
            return ClientTurn(self._pick(GOODBYES), True, self._survey(profile, messages), "rule")
        given = profile.order_id in " ".join(str(m["text"]) for m in messages if m["speaker"] == "customer")
        if not given and ASKS_FOR_ORDER.search(str(messages[-1]["text"])):
            # Guardrail: verification data is always given deterministically (small models
            # sometimes swap roles and ask the advisor for *its* order number).
            reply = self._pick(VERIFY_REPLIES).format(order_id=profile.order_id)
            return ClientTurn(reply, False, None, "rule")
        if self.use_llm():
            try:
                turn = self._llm_turn(profile, messages)
                if ADVISOR_VOICE.search(turn.text):
                    # Guardrail: a small model sometimes starts speaking as the advisor.
                    raise ValueError("role swap")
                return turn
            except (LLMUnavailableError, ValueError):
                pass
        return self._rule_turn(profile, messages)

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
    def _llm_turn(self, profile: CustomerProfile, messages: list[dict[str, Any]]) -> ClientTurn:
        assert self.llm is not None
        chat = [
            {
                "role": "system",
                "content": CLIENT_SYSTEM.format(
                    situation=profile.situation_text(),
                    opening=profile.opening_message,
                    order_id=profile.order_id,
                    persona=profile.persona,
                    tone=profile.tone,
                ),
            }
        ]
        for message in messages:  # roles are swapped: the model plays the customer
            role = "assistant" if message["speaker"] == "customer" else "user"
            chat.append({"role": role, "content": str(message["text"])})
        response = self.llm.chat("client", chat, json_mode=True, agent="client", temperature=0.7)
        data = response.json()
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
        return ClientTurn(
            text,
            end,
            csat,
            "llm",
            response.model,
            response.latency_ms,
            response.prompt_tokens + response.completion_tokens,
        )
