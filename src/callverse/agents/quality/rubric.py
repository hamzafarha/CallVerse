"""The quality scorecard filled for every conversation (1 = very poor, 5 = excellent)."""

from dataclasses import dataclass, field
from typing import Any

from callverse.config import load_yaml

# The 5 criteria of the scorecard; their definitions are in configs/agents.yaml (quality.rubric).
CRITERIA = ["compliance", "relevance", "satisfaction", "sentiment", "resolution"]


def rubric() -> dict[str, str]:
    """Criterion -> definition (``quality.rubric`` in agents.yaml)."""
    return dict(load_yaml("agents")["quality"]["rubric"])


@dataclass
class Scorecard:
    """Scores of one conversation by one judge."""

    # scores: criterion -> 1..5; correct: same outcome as the reference; resolved: solved, or correctly handed
    # over; rationale: one sentence; judge: "llm" or "rules".
    scores: dict[str, int]
    correct: bool | None
    resolved: bool
    rationale: str
    judge: str  # "llm" or "rules"
    model: str | None = None
    latency_ms: float = 0.0
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def overall(self) -> float:
        """The average of the 5 scores."""
        return sum(self.scores.values()) / len(self.scores)

    def to_dict(self) -> dict[str, Any]:
        """A JSON-friendly version (for the API and the saved transcripts)."""
        return {
            "scores": self.scores,
            "overall": round(self.overall, 2),
            "correct": self.correct,
            "resolved": self.resolved,
            "rationale": self.rationale,
            "judge": self.judge,
            "model": self.model,
            "latency_ms": round(self.latency_ms, 1),
            "details": self.details,
        }
