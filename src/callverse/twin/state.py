"""What-if scenarios of the digital twin (``configs/scenarios.yaml``)."""

from dataclasses import dataclass, field

import pandas as pd

from callverse.config import load_yaml


@dataclass(frozen=True)
class ScenarioSpec:
    """A real week of history, changed by explicit multipliers."""

    # name, label, description; week_start: the real week that is replayed; multipliers: extra volume per
    # problem group (e.g. 1.6 = +60%); absence_rate: the share of agents absent each day;
    # handle_time_multiplier: chats take longer (e.g. after a new product launch). reference_week (real
    # historical weeks only): the normal week an unprepared, "business as usual" manager copies its staffing
    # from; without it, unprepared = the same week's forecast without the multipliers.
    name: str
    label: str
    description: str
    week_start: pd.Timestamp
    multipliers: dict[str, float] = field(default_factory=dict)
    absence_rate: float = 0.0
    handle_time_multiplier: float = 1.0
    days: int = 7
    reference_week: pd.Timestamp | None = None

    @property
    def dates(self) -> pd.DatetimeIndex:
        """The days of the scenario."""
        return pd.date_range(self.week_start, periods=self.days)

    def with_overrides(self, **changes) -> "ScenarioSpec":
        """Copy with some fields changed (custom what-if from the dashboard)."""
        # Keep the original values, replaced only by the changes that are not None.
        values = {**self.__dict__, **{k: v for k, v in changes.items() if v is not None}}
        return ScenarioSpec(**values)


def load_scenarios() -> dict[str, ScenarioSpec]:
    """Every configured scenario by name."""
    raw = load_yaml("scenarios")["scenarios"]
    scenarios = {
        name: ScenarioSpec(
            name=name,
            label=spec["label"],
            # Collapse the multi-line YAML description into one line.
            description=" ".join(str(spec["description"]).split()),
            week_start=pd.Timestamp(spec["week_start"]),
            multipliers={k: float(v) for k, v in spec["multipliers"].items()},
            absence_rate=float(spec["absence_rate"]),
            handle_time_multiplier=float(spec["handle_time_multiplier"]),
            reference_week=pd.Timestamp(spec["reference_week"]) if spec.get("reference_week") else None,
        )
        for name, spec in raw.items()
    }
    # The copied staffing is laid day by day on the scenario week, so both weeks must start on the same day.
    for spec in scenarios.values():
        if spec.reference_week is not None and spec.reference_week.dayofweek != spec.week_start.dayofweek:
            raise ValueError(f"Scenario '{spec.name}': reference_week must start on the same weekday.")
    return scenarios


def scenario_defaults() -> dict[str, int]:
    """Seeds and drain days of ``configs/scenarios.yaml``."""
    raw = load_yaml("scenarios")["defaults"]
    return {"seeds": int(raw["seeds"]), "drain_days": int(raw["drain_days"])}
