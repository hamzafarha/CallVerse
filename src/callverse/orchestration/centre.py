"""The contact centre page (back office /centre): the live chats of the server, shown as people in an office.

Two jobs:

- ``CentreHub`` copies the events of every running chat (the same events as the Agent theater: ``ready``,
  ``message``, ``stage``, ``routing``, ``review``, ``done``) to every centre screen, through ``/ws/centre``.
  A screen that opens in the middle of a chat first receives that chat's story so far.
- ``saved_chats`` and ``advisors_summary`` read the finished chats that ``LiveSession.finish`` saved, grouped
  by the advisor desk that the Workforce agent chose (``routing.assigned_desk``). This is the history shown
  when you click an advisor, and the numbers of the KPI wall.

Analogy: the control room of a stadium. Each chat is a camera; the hub sends every camera to the screens of
the control room, and a screen switched on during the match first sees a replay of the match so far.
"""

# How it works: a chat gets a ChatFeed (hub.open). The agents report every step with feed.emit(kind, data),
# exactly like a LiveSession's emit. The hub wraps each event as {"chat", "channel", "seq", "event"} and
# sends it to every subscribed screen (one callback per WebSocket). Words streamed one by one ("token") are
# not sent: the centre shows "typing..." and then the finished message. When a chat sends "done", the hub
# forgets it (its transcript is on disk, where saved_chats reads it).
import json
import threading
import time
import uuid
from collections import Counter
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from callverse.orchestration.live import live_chats_dir

Send = Callable[[dict[str, Any]], None]
FORGET_AFTER_SECONDS = 2 * 3600  # a chat with no event for 2 hours is forgotten (e.g. a tab closed mid-chat)


class CentreBusy(RuntimeError):
    """The centre already serves as many of its own customers as allowed."""


class ChatFeed:
    """One chat as the centre sees it: its id, where it comes from, and its events so far."""

    def __init__(self, hub: "CentreHub", channel: str, name: str) -> None:
        self.id = f"CH-{uuid.uuid4().hex[:8]}"
        # Where the customer comes from: "centre" = sent by the centre page (the Client agent plays it).
        self.channel = channel
        self.name = name
        self.started_at = time.time()
        self.last_activity = self.started_at
        self.events: list[dict[str, Any]] = []
        self.finished = False
        self._hub = hub

    def emit(self, kind: str, data: dict[str, Any]) -> None:
        """Same signature as a LiveSession's emit: give it to the session, and the centre sees every step."""
        self._hub.publish(self, {"type": kind, **data})

    def close(self) -> None:
        """End the story on the centre screens when the chat stopped without "done" (error, closed tab)."""
        if not self.finished:
            self.emit("done", {"reviewed": False})

    def run(self, work: Callable[[], Any]) -> None:
        """Run a whole chat (in a worker thread). An error is shown on the centre screen; the story ends."""
        try:
            work()
        except Exception as error:  # surfaced to the centre screen
            self.emit("error", {"message": str(error)})
        finally:
            self.close()


class CentreHub:
    """Every running chat of the server, and the centre screens that watch them."""

    def __init__(self) -> None:
        self._chats: dict[str, ChatFeed] = {}
        self._screens: dict[int, Send] = {}
        self._next_token = 0
        self._lock = threading.RLock()  # protects the chats, their event logs and the list of screens

    def open(self, channel: str, name: str, limit: int | None = None) -> ChatFeed:
        """A new chat. ``limit``: at most that many running chats of this channel (else ``CentreBusy``)."""
        with self._lock:
            self._forget_stale()
            if limit is not None and self.running(channel) >= limit:
                raise CentreBusy("A customer is already being served: wait until the story ends.")
            feed = ChatFeed(self, channel, name)
            self._chats[feed.id] = feed
        return feed

    def running(self, channel: str | None = None) -> int:
        """How many chats are running now (of one channel, or of all channels)."""
        with self._lock:
            return sum(channel is None or feed.channel == channel for feed in self._chats.values())

    def publish(self, feed: ChatFeed, event: dict[str, Any]) -> None:
        """Send one event of a chat to every screen, and keep it for the screens that open later."""
        if event.get("type") == "token":
            return  # words one by one: the centre shows "typing..." and then the finished message
        with self._lock:
            if feed.finished:
                return  # nothing comes after "done"
            # seq = the step number in this chat: a screen that reconnects gets the story again and skips the
            # steps it already showed.
            message = {"chat": feed.id, "channel": feed.channel, "seq": len(feed.events), "event": event}
            feed.events.append(message)
            feed.last_activity = time.time()
            if event.get("type") == "done":
                feed.finished = True
                self._chats.pop(feed.id, None)
            screens = list(self._screens.values())
        # Sent outside the lock: a screen's callback only puts the message in that WebSocket's outbox.
        for send in screens:
            send(message)

    def subscribe(self, send: Send) -> int:
        """Attach a centre screen: first the story so far of every running chat, then the live events."""
        with self._lock:
            self._forget_stale()
            token = self._next_token
            self._next_token += 1
            for feed in sorted(self._chats.values(), key=lambda f: f.started_at):
                for message in feed.events:
                    send(message)
            self._screens[token] = send
        return token

    def unsubscribe(self, token: int) -> None:
        """Detach a centre screen (its WebSocket closed)."""
        with self._lock:
            self._screens.pop(token, None)

    def _forget_stale(self) -> None:
        """Drop the chats with no event for a long time (they will never send "done")."""
        now = time.time()
        for chat_id, feed in list(self._chats.items()):
            if now - feed.last_activity > FORGET_AFTER_SECONDS:
                del self._chats[chat_id]


# One hub for the whole server (the API's WebSockets and the centre's own customers share it).
CENTRE = CentreHub()


def centre_channel(channel: str, customer: str) -> str:
    """Where a chat comes from, for the centre's labels: "centre" (sent by the centre page), "visitor" (a
    person speaks into the centre page's microphone), "phone" (a person calls from a phone), "web" (a person
    writes on the customer portal) or "agents" (the Client agent plays the customer: the Agent theater, or the
    advisor desk where a person may answer)."""
    if channel in ("phone", "centre", "visitor"):
        return channel
    return "web" if customer == "human" else "agents"


# ----------------------------------------------------------------------------- history
def chat_summary(path: Path, state: dict[str, Any]) -> dict[str, Any]:
    """One finished chat as the centre's history shows it (from a transcript saved by LiveSession.finish)."""
    profile = state.get("profile") or {}
    routing = state.get("routing") or {}
    card = state.get("scorecard") or {}
    kpis = state.get("kpis") or {}
    live = state.get("live") or {}
    messages = state.get("messages") or []
    csat = state.get("csat")
    advisor_meta = [m.get("meta") or {} for m in messages if m["speaker"] == "advisor"]
    return {
        "id": path.stem,
        # The advisor desk the Workforce agent chose, e.g. "advisor-02" (desk 3 on the centre's floor).
        "advisor": routing.get("assigned_desk"),
        "specialty": routing.get("desk_specialty"),
        # Older transcripts have no end time: the file's last change is the end of the chat.
        "ended_at": state.get("ended_at") or path.stat().st_mtime,
        "contact_id": profile.get("contact_id"),
        "customer_unique_id": profile.get("customer_unique_id"),
        "intent": profile.get("intent"),
        "group": profile.get("intent_group"),
        "predicted_intent": routing.get("predicted_intent"),
        "channel": live.get("channel") or "web",
        "customer_side": live.get("customer"),  # "agent" (Client agent) or "human"
        "advisor_side": live.get("advisor"),  # "agent" (Advisor agent) or "human" (a person at the desk)
        "quality": card.get("overall"),
        "scores": card.get("scores") or {},
        "rationale": card.get("rationale"),
        "resolved": card.get("resolved"),
        "correct": card.get("correct"),
        "judge": card.get("judge"),
        "judge_model": card.get("model"),
        "reference": state.get("reference") or {},
        "csat": csat if csat is not None else kpis.get("csat"),
        "fcr": kpis.get("fcr"),
        "compliant": kpis.get("compliant"),
        # Erlang C wait of that hour (the twin's estimate), None when the centre was closed.
        "wait_seconds": routing.get("expected_wait_seconds"),
        "turns": len(messages),
        "tokens": sum(int(meta.get("tokens") or 0) for meta in advisor_meta),  # the Advisor agent's LLM text
        "messages": [
            {
                "speaker": m["speaker"],
                "text": m["text"],
                "tools": [t.get("name") for t in (m.get("meta") or {}).get("tools", [])],
            }
            for m in messages
        ],
    }


def saved_chats(folder: Path | None = None) -> list[dict[str, Any]]:
    """Every finished live chat, newest first (a file being written or broken is left out)."""
    folder = folder or live_chats_dir()
    chats = []
    for path in folder.glob("*.json"):
        try:
            chats.append(chat_summary(path, json.loads(path.read_text(encoding="utf-8"))))
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return sorted(chats, key=lambda chat: chat["ended_at"], reverse=True)


def _mean(values: Iterable[Any]) -> float | None:
    """Average of the known values (None when there is none)."""
    known = [float(v) for v in values if v is not None]
    return round(sum(known) / len(known), 3) if known else None


def _figures(chats: list[dict[str, Any]]) -> dict[str, Any]:
    """The numbers of a group of chats: count, Quality score, solved first time, customer rating."""
    return {
        "chats": len(chats),
        "quality": _mean(c["quality"] for c in chats),
        "fcr": _mean(None if c["fcr"] is None else float(bool(c["fcr"])) for c in chats),
        "csat": _mean(c["csat"] for c in chats),
    }


def advisors_summary(chats: list[dict[str, Any]]) -> dict[str, Any]:
    """The KPI wall (totals of every chat) and one line per advisor desk, sorted by desk number."""
    by_advisor: dict[str, list[dict[str, Any]]] = {}
    for chat in chats:
        if chat["advisor"]:
            by_advisor.setdefault(chat["advisor"], []).append(chat)
    advisors = []
    for advisor, own in by_advisor.items():
        specialties = Counter(c["specialty"] for c in own if c["specialty"])
        advisors.append(
            {
                "id": advisor,
                **_figures(own),
                "specialty": specialties.most_common(1)[0][0] if specialties else None,
                "last_at": max(c["ended_at"] for c in own),
            }
        )
    advisors.sort(key=lambda a: (len(a["id"]), a["id"]))  # advisor-02 before advisor-10
    totals = {
        **_figures(chats),
        "wait_seconds": _mean(c["wait_seconds"] for c in chats),
        "tokens": sum(c["tokens"] for c in chats),
        "by_ai": sum(c["advisor_side"] == "agent" for c in chats),
        "by_human": sum(c["advisor_side"] == "human" for c in chats),
    }
    return {"totals": totals, "advisors": advisors}
