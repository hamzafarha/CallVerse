"""Cached back-end objects and JSON helpers for the API."""

import json
import math
from functools import lru_cache
from typing import Any

import numpy as np
import pandas as pd

from callverse.config import EVALUATION_DIR
from callverse.twin import DigitalTwin


@lru_cache(maxsize=1)
def twin() -> DigitalTwin:
    """One digital twin per process (plans are cached inside)."""
    return DigitalTwin()


def clean(value: Any) -> Any:
    """Make numpy / pandas values JSON-safe (NaN -> None, Timestamp -> ISO)."""
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        number = float(value)
        return None if math.isnan(number) or math.isinf(number) else number
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    if isinstance(value, np.ndarray):
        return clean(value.tolist())
    if value is pd.NA or value is pd.NaT:
        return None
    return value


def records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    """DataFrame -> list of JSON-safe dicts."""
    if frame is None or frame.empty:
        return []
    return json.loads(frame.to_json(orient="records", date_format="iso"))


def read_eval(name: str) -> list[dict[str, Any]]:
    """An evaluation table as records (empty if not produced yet)."""
    path = EVALUATION_DIR / name
    return records(pd.read_csv(path)) if path.exists() else []
