"""Request models of the REST API (validated by Pydantic)."""

# Pydantic checks every request body: a wrong type or an out-of-range value returns an HTTP 422 error
# automatically, before our code runs.
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class TwinRunRequest(BaseModel):
    """One what-if configuration of the digital twin."""

    scenario: str = "baseline"
    plan: Literal["cpsat", "rules_erlang", "fixed", "fixed_tuned", "erlang_hourly"] = "cpsat"
    router: Literal["fifo", "skill_score", "ppo"] = "fifo"
    # Field(5, ge=1, le=30): default 5, at least 1, at most 30.
    seeds: int = Field(5, ge=1, le=30)
    prepared: bool = True
    # Optional custom what-if on top of the scenario
    multipliers: dict[str, float] | None = None
    absence_rate: float | None = Field(None, ge=0, le=0.8)
    handle_time_multiplier: float | None = Field(None, ge=0.5, le=2.0)


class TwinCompareRequest(BaseModel):
    """Several configurations on the same customers (common random numbers)."""

    scenario: str = "promo_spike"
    seeds: int = Field(5, ge=1, le=30)
    options: list[TwinRunRequest]


class ConversationRequest(BaseModel):
    """One agent conversation in the playground."""

    contact_id: str | None = None
    mode: Literal["auto", "llm", "template"] = "template"
    variant: Literal["rag_policy", "rag", "agentic"] = "rag_policy"
    seed: int = 0


class HumanLabel(BaseModel):
    """Human grades of one conversation (1-5) for judge calibration."""

    ticket_id: str
    labeler: str = Field("anonymous", max_length=40)
    compliance: int = Field(ge=1, le=5)
    relevance: int = Field(ge=1, le=5)
    satisfaction: int = Field(ge=1, le=5)
    sentiment: int = Field(ge=1, le=5)
    resolution: int = Field(ge=1, le=5)
    comment: str = Field("", max_length=500)


class InventedOrderRequest(BaseModel):
    """An order typed by the visitor (option "invent my order" of a new customer)."""

    category: str = Field(min_length=1, max_length=60)
    value_brl: float = Field(gt=0, le=20000)
    items: int = Field(1, ge=1, le=20)
    payment_type: Literal["credit_card", "boleto", "debit_card", "voucher"] = "credit_card"
    city: str = Field("sao paulo", min_length=1, max_length=60)
    state: str = Field("SP", min_length=2, max_length=2)
    purchased_at: date
    estimated_delivery: date
    # How far the order got: not shipped yet, on the way, delivered, or canceled.
    progress: Literal["processing", "shipped", "delivered", "canceled"]
    shipped_at: date | None = None
    delivered_at: date | None = None
    contact_at: date  # the day the customer writes to us


class NewCustomerRequest(BaseModel):
    """A brand-new customer: a name, a persona, a problem, and a real or an invented order."""

    name: str = Field(min_length=1, max_length=40)
    persona: Literal["impatient", "normal", "patient"] = "normal"
    intent: str = Field(min_length=1, max_length=40)
    message: str | None = Field(None, max_length=500)
    order_source: Literal["real", "invented"] = "real"
    order: InventedOrderRequest | None = None  # required when order_source is "invented"
