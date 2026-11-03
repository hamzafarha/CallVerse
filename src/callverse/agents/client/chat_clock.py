"""The customer's chat clock: how long it has waited, and how patient it is.

The Client agent's ``check_my_waiting_time`` tool reads it, like a customer looking
at the timer of its chat window. The waits come from the digital twin or from the
real clock:

- queue wait (before an advisor joined): in twin runs, the Workforce agent's Erlang C
  wait for that hour (0 when the centre was closed, as in the twin); on the advisor
  desk, the time the customer spent in your queue;
- wait for an answer: the real seconds between the customer's last message and the
  advisor's answer (on the desk, the time you take to reply).

Patience is the persona's: the same mean patience the twin uses for abandonment
(``patience_mean_seconds`` x the persona's ``patience_multiplier``).
"""

# How to read this file: persona_patience() gives the patience; queue_wait_from_twin() gives the queue wait;
# ChatClock adds up all the waiting; reading() is what the tool returns.
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from callverse.simulation import load_twin_settings


def persona_patience(persona: str) -> float:
    """Mean patience of a persona, in seconds (impatient 90, normal 180, patient 360)."""
    # load_twin_settings() reads configs/simulation.yaml (mean patience 180 s) and the persona multipliers of
    # configs/agents.yaml (impatient 0.5, normal 1, patient 2).
    settings = load_twin_settings()
    multiplier = settings.patience_mix.get(persona, (0.0, 1.0))[1]
    return float(settings.sim.patience_mean_seconds) * multiplier


def queue_wait_from_twin(routing: dict[str, Any]) -> float:
    """Queue wait of a twin run: the Workforce agent's Erlang C wait for that hour.

    When the centre was closed, the message waited for the morning, but the customer was
    told so: like in the twin (no abandonment while closed), that wait does not use up
    its patience, so it counts as 0.
    """
    # Centre open: the Erlang C mean wait that the Workforce agent computed for that hour.
    if routing.get("is_live", True) and routing.get("expected_wait_seconds") is not None:
        return float(routing["expected_wait_seconds"])
    return 0.0


def duration(seconds: float) -> str:
    """'45 s', '3 min 24 s', '7 h 02 min' (what a chat timer shows)."""
    seconds = int(round(seconds))
    if seconds < 60:
        return f"{seconds} s"
    if seconds < 3600:
        return f"{seconds // 60} min {seconds % 60:02d} s"
    return f"{seconds // 3600} h {seconds % 3600 // 60:02d} min"


@dataclass
class ChatClock:
    """Timer of one chat. ``now`` is the wall clock (a fake one in tests).

    The customer's patience is a budget for all its waiting in this chat: the queue,
    then every wait for an advisor's answer.
    """

    # patience_seconds: the budget; queue_wait_seconds: the time in the queue before the chat; now: a clock
    # function; last_customer_at: when the customer last wrote; answer_waits: one entry per advisor answer.
    patience_seconds: float
    queue_wait_seconds: float = 0.0
    now: Callable[[], float] = field(default=time.monotonic, repr=False)
    last_customer_at: float = -1.0
    answer_waits: list[float] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.last_customer_at < 0:  # the chat opens with the customer's first message
            self.last_customer_at = self.now()

    def answer_arrived(self) -> None:
        """An advisor answered: the time since the customer's last message was a wait."""
        self.answer_waits.append(max(0.0, self.now() - self.last_customer_at))

    def customer_wrote(self) -> None:
        """The customer just wrote: a new wait for the advisor's answer starts now."""
        self.last_customer_at = self.now()

    @property
    def total_wait_seconds(self) -> float:
        """All the waiting so far: the queue plus every answer wait."""
        return self.queue_wait_seconds + sum(self.answer_waits)

    def reading(self) -> dict[str, Any]:
        """What the timer shows (the tool result)."""
        last = self.answer_waits[-1] if self.answer_waits else 0.0
        total = self.total_wait_seconds
        # over_my_patience is computed by code (small LLMs are bad at comparing numbers); the LLM decides what
        # to DO about it (mention it, complain, or leave).
        return {
            "waited_in_queue_seconds": round(self.queue_wait_seconds),
            "waited_for_last_answer_seconds": round(last),
            "total_wait_seconds": round(total),
            "my_patience_seconds": round(self.patience_seconds),
            "over_my_patience": total >= self.patience_seconds,
            "clock": (
                f"I waited {duration(self.queue_wait_seconds)} in the queue and "
                f"{duration(sum(self.answer_waits))} for the advisor's answers, the last one took "
                f"{duration(last)} ({duration(total)} in all; my patience is about "
                f"{duration(self.patience_seconds)})"
            ),
        }


def summarize_clock(reading: dict[str, Any]) -> str:
    """One line for the UI."""
    verdict = "over my patience" if reading["over_my_patience"] else "still patient"
    return (
        f"waited {duration(reading['total_wait_seconds'])} in all, "
        f"patience {duration(reading['my_patience_seconds'])}: {verdict}"
    )
