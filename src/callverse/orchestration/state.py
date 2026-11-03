"""State passed between the LangGraph nodes of one conversation."""

# TypedDict: a dictionary whose keys and value types are declared (it helps the editor and LangGraph).
# total=False: every key is optional, because the nodes fill them in turn.
from typing import Any, TypedDict


class ConversationState(TypedDict, total=False):
    """Serializable state of one twin conversation (streamed to the dashboard)."""

    profile: dict[str, Any]
    messages: list[dict[str, Any]]  # speaker, text, meta
    events: list[dict[str, Any]]  # node timeline (what each agent did)
    customer_turns: int
    ended: bool
    csat: int | None
    routing: dict[str, Any]
    advisor: dict[str, Any]  # memory of the advisor (intent, outcome, handover)
    reference: dict[str, Any]
    scorecard: dict[str, Any]
    kpis: dict[str, Any]
