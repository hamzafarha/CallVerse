"""What-if scenarios of the digital twin (``configs/scenarios.yaml``)."""

from dataclasses import dataclass, field

import pandas as pd

from callverse.config import load_yaml


@dataclass(frozen=True)
class ScenarioSpec:
    """A real week of history, changed by explicit multipliers."""

    name: str
    label: str
    description: str
    week_start: pd.Timestamp
    multipliers: dict[str, float] = field(default_factory=dict)
    absence_rate: float = 0.0
    handle_time_multiplier: float = 1.0
    days: int = 7

    @property
    def dates(self) -> pd.DatetimeIndex:
        return pd.date_range(self.week_start, periods=self.days)

    def with_overrides(self, **changes) -> "ScenarioSpec":
        """Copy with some fields changed (custom what-if from the dashboard)."""
        values = {**self.__dict__, **{k: v for k, v in changes.items() if v is not None}}
        return ScenarioSpec(**values)


def load_scenarios() -> dict[str, ScenarioSpec]:
    """Every configured scenario by name."""
    raw = load_yaml("scenarios")["scenarios"]
    return {
        name: ScenarioSpec(
            name=name,
            label=spec["label"],
            description=" ".join(str(spec["description"]).split()),
            week_start=pd.Timestamp(spec["week_start"]),
            multipliers={k: float(v) for k, v in spec["multipliers"].items()},
            absence_rate=float(spec["absence_rate"]),
            handle_time_multiplier=float(spec["handle_time_multiplier"]),
        )
        for name, spec in raw.items()
    }


def scenario_defaults() -> dict[str, int]:
    """Seeds and drain days of ``configs/scenarios.yaml``."""
    raw = load_yaml("scenarios")["defaults"]
    return {"seeds": int(raw["seeds"]), "drain_days": int(raw["drain_days"])}
