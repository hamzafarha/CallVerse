"""Request models of the REST API (validated by Pydantic)."""

from typing import Literal

from pydantic import BaseModel, Field


class TwinRunRequest(BaseModel):
    """One what-if configuration of the digital twin."""

    scenario: str = "baseline"
    plan: Literal["cpsat", "rules_erlang", "fixed", "fixed_tuned", "erlang_hourly"] = "cpsat"
    router: Literal["fifo", "skill_score", "ppo"] = "fifo"
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
    variant: Literal["rag_policy", "rag"] = "rag_policy"
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
