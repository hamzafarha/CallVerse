"""Interactive conversations for the front office: a human can play either side.

The LangGraph run (``graph.py``) is fully automatic. Here the UI drives the same
agents one step at a time over a WebSocket:

- customer portal: a human customer chats with the Advisor agent (tokens stream);
- advisor desk: the Client agent plays the customer and a human advisor answers,
  with the Advisor agent as a copilot that drafts each reply ("autopilot" lets the
  agent answer by itself).

When the chat ends, the Quality agent grades it and the KPI row is computed with
the same helpers as the automatic graph, so live chats count like simulated ones.
"""

from collections.abc import Callable
from typing import Any

from callverse.agents.client.profiles import CustomerProfile
from callverse.config import TRACE_DIR
from callverse.orchestration.graph import (
    advisor_message,
    advisor_state,
    kpi_row,
    make_session,
    review_conversation,
    route_contact,
    save_transcript,
)

Emit = Callable[[str, dict[str, Any]], None]
SIDES = {"customer": ("human", "agent"), "advisor": ("human", "agent")}


class LiveSession:
    """One conversation driven step by step; every step reports through ``emit``."""

    def __init__(
        self,
        profile: CustomerProfile,
        emit: Emit,
        mode: str = "auto",
        seed: int = 0,
        variant: str | None = None,
        customer: str = "human",
        advisor: str = "agent",
    ) -> None:
        if customer not in SIDES["customer"] or advisor not in SIDES["advisor"]:
            raise ValueError("customer and advisor must be 'human' or 'agent'")
        if customer == "human" and advisor == "human":
            raise ValueError("at least one side must be an agent")
        self.session = make_session(profile, mode, seed, variant=variant)
        self.emit = emit
        self.customer, self.advisor = customer, advisor
        self.messages: list[dict[str, Any]] = []
        self.routing: dict[str, Any] | None = None
        self.draft: dict[str, Any] | None = None
        self.csat: int | None = None
        self.finished = False

    # ---------------------------------------------------------------- helpers
    @property
    def profile(self) -> CustomerProfile:
        return self.session.profile

    def _add(self, speaker: str, text: str, meta: dict[str, Any]) -> dict[str, Any]:
        message = {"speaker": speaker, "text": text, "meta": meta}
        self.messages.append(message)
        self.emit("message", {"message": message, "index": len(self.messages) - 1})
        return message

    def _customer_turns(self) -> int:
        return sum(m["speaker"] == "customer" for m in self.messages)

    def _run_advisor(self, kind: str) -> Any:
        """Advisor agent reply, streamed as ``token`` events (``kind``: reply or draft)."""
        self.emit("stage", {"agent": "advisor", "step": "start", "kind": kind})
        return self.session.advisor.reply(
            self.messages,
            self.session.memory,
            self.session.tools,
            on_token=lambda text: self.emit("token", {"text": text, "kind": kind}),
            on_event=lambda step, data: self.emit(
                "stage", {"agent": "advisor", "step": step, "kind": kind, **data}
            ),
        )

    # ------------------------------------------------------------------ steps
    def begin(self) -> None:
        """The Client agent opens with the contact's real message (agent customer)."""
        if self.customer == "agent":
            turn = self.session.client.opening(self.profile)
            self._add("customer", turn.text, {"mode": turn.mode})
            self._after_customer()

    def _after_customer(self) -> None:
        if self.routing is None:
            self.emit("stage", {"agent": "workforce", "step": "routing"})
            self.routing = route_contact(self.session, self.messages[0]["text"])
            self.emit("routing", {"routing": self.routing})
        self.draft = None
        if self.advisor == "agent":
            self.advisor_turn()
        else:
            self.suggest()

    def advisor_turn(self) -> None:
        self._commit_advisor(advisor_message(self._run_advisor("reply")))

    def _commit_advisor(self, message: dict[str, Any]) -> None:
        self.messages.append(message)
        self.emit("message", {"message": message, "index": len(self.messages) - 1})
        self.emit("advisor_state", {"advisor": advisor_state(self.session)})
        if self.customer == "agent":
            self.customer_turn()

    def suggest(self) -> None:
        """Copilot: the Advisor agent drafts the next reply (once per customer turn)."""
        if self.draft is None:
            self.draft = advisor_message(self._run_advisor("draft"))
        self.emit("suggestion", {"message": self.draft, "advisor": advisor_state(self.session)})

    def human_advisor(self, text: str) -> None:
        draft = self.draft or {"text": "", "meta": {}}
        meta = {
            "mode": "human",
            "copilot_draft": draft["text"] or None,
            "copilot_edited": bool(draft["text"]) and text.strip() != draft["text"].strip(),
            "sources": draft["meta"].get("sources", []),
            "tools": draft["meta"].get("tools", []),
        }
        self._add("advisor", text.strip(), meta)
        self.draft = None
        if self.customer == "agent":
            self.customer_turn()

    def human_customer(self, text: str) -> None:
        self._add("customer", text.strip(), {"mode": "human"})
        self._after_customer()

    def customer_turn(self) -> None:
        """The Client agent answers the advisor (it may leave and rate the chat)."""
        self.emit("stage", {"agent": "client", "step": "typing"})
        turns = self._customer_turns()
        turn = self.session.client.respond(self.profile, self.messages, turns)
        self._add("customer", turn.text, {"mode": turn.mode})
        if turn.end or turns + 1 > self.session.max_turns:
            self.finish(turn.csat)
        else:
            self._after_customer()

    def set_autopilot(self, on: bool) -> None:
        self.advisor = "agent" if on else "human"
        waiting = self.messages and self.messages[-1]["speaker"] == "customer"
        if on and waiting and not self.finished:
            if self.draft is not None:  # the copilot already answered this turn: send it
                draft, self.draft = self.draft, None
                self._commit_advisor(draft)
            else:
                self.advisor_turn()

    def finish(self, csat: int | None = None) -> None:
        """Quality agent review + KPI row; the transcript is saved like any other."""
        if self.finished:
            return
        self.finished = True
        self.csat = csat if csat is not None else self.csat
        if not any(m["speaker"] == "advisor" for m in self.messages):
            self.emit("done", {"reviewed": False})
            return
        self.emit("stage", {"agent": "quality", "step": "reviewing"})
        reference, card = review_conversation(self.session, self.messages)
        scorecard = card.to_dict()
        kpis = kpi_row(self.session, self.messages, self.routing or {}, scorecard, self.csat, reference)
        state = {
            "profile": self.profile.to_dict(),
            "messages": self.messages,
            "routing": self.routing,
            "advisor": advisor_state(self.session),
            "reference": reference,
            "scorecard": scorecard,
            "kpis": kpis,
            "csat": self.csat,
            "live": {"customer": self.customer, "advisor": self.advisor},
            "events": [],
        }
        # Own folder: live chats must not mix with the evaluation batches (per-variant metrics).
        save_transcript(state, TRACE_DIR / "live_sessions")  # type: ignore[arg-type]
        self.emit("review", {"scorecard": scorecard, "reference": reference, "kpis": kpis})
        self.emit("done", {"reviewed": True})

    # ------------------------------------------------------------- dispatcher
    def handle(self, message: dict[str, Any]) -> None:
        """One message from the UI."""
        kind = message.get("type")
        text = str(message.get("text", "")).strip()
        if self.finished:
            self.emit("error", {"message": "The conversation is over."})
        elif kind == "customer_message" and self.customer == "human" and text:
            self.human_customer(text)
        elif kind == "advisor_message" and self.advisor == "human" and text:
            self.human_advisor(text)
        elif kind == "suggest" and self.advisor == "human":
            self.suggest()
        elif kind == "autopilot":
            self.set_autopilot(bool(message.get("on")))
        elif kind == "end":
            csat = message.get("csat")
            self.finish(int(csat) if csat else None)
        else:
            self.emit("error", {"message": f"Unexpected message '{kind}'."})
