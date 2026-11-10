"""Phone calls: one live conversation followed by several screens at once.

A customer talks from a phone (front office, page /phone); on the PC, the advisor desk sees the call in
its queue, watches it live and can take over. Both screens follow the SAME conversation:

- the phone is the customer side (it sends ``customer_message`` and ``end``);
- the desk is the advisor side (``advisor_message``, ``suggest``, ``autopilot``, ``end``).

Nothing changes for the agents: the Workforce agent routes the first message, the Advisor agent answers on
autopilot (its tool calls appear on every screen), and the Quality agent grades the call at the end.

Analogy: a conference call. The hub is the operator who keeps the call open, repeats what was already said
to anyone who joins late, and lets only one person speak at a time.
"""

# How it works: SharedCall wraps one LiveSession. Every event the agents emit goes to every subscribed screen
# (one callback per WebSocket) and is kept in a log, so a screen that joins late (or a phone that reconnects
# after its screen locked) first receives the whole story. A lock lets one message be handled at a time.
import threading
import time
import uuid
from collections.abc import Callable
from typing import Any

from callverse.agents.client.profiles import CustomerProfile
from callverse.orchestration.centre import CENTRE
from callverse.orchestration.live import LiveSession

Send = Callable[[dict[str, Any]], None]
# What each side may send.
ALLOWED = {
    "customer": {"customer_message", "end"},
    "advisor": {"advisor_message", "suggest", "autopilot", "end"},
}
KEEP_ENDED_SECONDS = 30 * 60  # an ended call stays in the desk list for 30 minutes
KEEP_IDLE_SECONDS = 2 * 3600  # a call with no activity for 2 hours is forgotten
PHONE_GRACE_SECONDS = 120  # a phone that hung up mid-call leaves the contact centre page after 2 minutes


class SharedCall:
    """One phone call: a LiveSession (customer = the human on the phone, advisor = the AI on autopilot)."""

    def __init__(
        self,
        profile: CustomerProfile,
        name: str,
        mode: str = "auto",
        seed: int = 0,
        variant: str | None = None,
    ) -> None:
        self.id = f"PH-{uuid.uuid4().hex[:8]}"
        self.name = name
        self.profile = profile
        self.variant = variant
        self.started_at = time.time()
        self.last_activity = self.started_at
        self.ended_at: float | None = None
        self.customer_connected = False
        self.events: list[dict[str, Any]] = []
        self._subscribers: dict[int, Send] = {}
        self._next_token = 0
        self._lock = threading.RLock()  # protects the event log and the subscriber list
        self._work = threading.Lock()  # one message handled at a time
        # The contact centre page (/ws/centre) follows the call too.
        self.feed = CENTRE.open("phone", name)
        self.live = LiveSession(profile, self.emit, mode, seed, variant, "human", "agent", channel="phone")

    # ------------------------------------------------------------ events
    def emit(self, kind: str, data: dict[str, Any]) -> None:
        """Send one agent event to every screen (and keep it for screens that join later)."""
        event = {"type": kind, **data}
        with self._lock:
            # Streamed words are not kept: a late screen gets the finished message instead.
            if kind != "token":
                self.events.append(event)
            if kind == "done":
                self.ended_at = time.time()
            subscribers = list(self._subscribers.values())
        for send in subscribers:
            send(event)
        self.feed.emit(kind, data)

    def close_if_abandoned(self) -> None:
        """The phone hung up (or lost its connection) and did not come back: the customer leaves the centre
        page. The call itself stays in the desk's list."""
        if not self.live.finished and not self.customer_connected:
            self.feed.close()

    def subscribe(self, send: Send) -> int:
        """Attach a screen: it first receives everything said so far, then the live events."""
        with self._lock:
            token = self._next_token
            self._next_token += 1
            for event in self.events:
                send(event)
            self._subscribers[token] = send
        return token

    def unsubscribe(self, token: int) -> None:
        with self._lock:
            self._subscribers.pop(token, None)

    # ---------------------------------------------------------- messages
    def handle(self, message: dict[str, Any], role: str) -> None:
        """One message from the phone ("customer") or the desk ("advisor")."""
        kind = message.get("type")
        if kind not in ALLOWED.get(role, set()):
            raise ValueError(f"The {role} side cannot send '{kind}'.")
        if self.live.finished:
            raise ValueError("This call has ended.")
        if kind in ("advisor_message", "suggest") and self.live.advisor == "agent":
            raise ValueError("The AI is answering: choose 'You answer' first to take over the call.")
        with self._work:
            self.live.handle(message)
        self.last_activity = time.time()

    # -------------------------------------------------------------- list
    def info(self) -> dict[str, Any]:
        """One line of the desk's "Phone calls" list."""
        live = self.live
        messages = live.messages
        routing = live.routing or {}
        customer = [m for m in messages if m["speaker"] == "customer"]
        review = next((e for e in reversed(self.events) if e["type"] == "review"), None)
        if live.finished:
            status = "ended"
        elif not customer:
            status = "ringing"
        else:
            status = "talking"
        return {
            "id": self.id,
            "contact_id": self.profile.contact_id,
            "name": self.name,
            "persona": self.profile.persona,
            "intent": self.profile.intent,
            "intent_group": self.profile.intent_group,
            "predicted_intent": routing.get("predicted_intent"),
            "desk": routing.get("assigned_desk"),
            "status": status,
            "autopilot": live.advisor == "agent",
            "variant": self.variant,
            "messages": len(messages),
            "last_message": messages[-1]["text"][:140] if messages else None,
            "started_at": self.started_at,
            "seconds": round((self.ended_at or time.time()) - self.started_at),
            "customer_connected": self.customer_connected,
            "watchers": max(0, len(self._subscribers) - int(self.customer_connected)),
            "quality": review["scorecard"].get("overall") if review else None,
        }


class CallHub:
    """Every phone call of the server, by id."""

    def __init__(self) -> None:
        self._calls: dict[str, SharedCall] = {}
        self._lock = threading.Lock()

    def open(
        self,
        profile: CustomerProfile,
        name: str,
        mode: str = "auto",
        seed: int = 0,
        variant: str | None = None,
    ) -> SharedCall:
        """A new call (the phone pressed "Call")."""
        call = SharedCall(profile, name, mode, seed, variant)
        with self._lock:
            self._calls[call.id] = call
        return call

    def get(self, call_id: str | None) -> SharedCall | None:
        with self._lock:
            return self._calls.get(call_id or "")

    def calls(self) -> list[dict[str, Any]]:
        """The calls for the desk, newest first; old ended or idle calls are forgotten."""
        now = time.time()
        with self._lock:
            for call_id, call in list(self._calls.items()):
                ended_long_ago = call.ended_at is not None and now - call.ended_at > KEEP_ENDED_SECONDS
                if ended_long_ago or now - call.last_activity > KEEP_IDLE_SECONDS:
                    del self._calls[call_id]
            calls = list(self._calls.values())
        return [call.info() for call in sorted(calls, key=lambda c: -c.started_at)]


# One hub for the whole server (the API's WebSockets share it).
HUB = CallHub()
