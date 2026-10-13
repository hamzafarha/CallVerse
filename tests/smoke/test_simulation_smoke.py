"""Smoke tests for CallVerse package, CLI, and simulation."""

import importlib
import pkgutil
from pathlib import Path

import callverse
import numpy as np
import pandas as pd
from callverse.main import app
from callverse.simulation import (
    LognormalServiceModel,
    contact_kpis,
    generate_contacts,
    load_simulation_config,
    run_simulation,
)
from typer.testing import CliRunner

CONFIG_PATH = Path(__file__).resolve().parents[2] / "configs" / "simulation.yaml"

runner = CliRunner()


def test_import_all_callverse_modules() -> None:
    """Verify that every module within callverse can be imported without errors."""
    prefix = callverse.__name__ + "."
    for _, modname, _ in pkgutil.walk_packages(callverse.__path__, prefix):
        imported = importlib.import_module(modname)
        assert imported is not None


def test_cli_help() -> None:
    """Verify that callverse --help exits with returncode 0."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "CallVerse" in result.output or "callverse" in result.output


def test_simulation_smoke() -> None:
    """Run one short simulation day with the project configuration."""
    config = load_simulation_config(CONFIG_PATH)
    model = LognormalServiceModel(config.service_times)
    daily = pd.DataFrame(
        {
            "date": [pd.Timestamp("2018-01-01")] * len(config.service_times),
            "intent_group": list(config.service_times),
            "contacts": [5] * len(config.service_times),
        }
    )
    contacts = generate_contacts(
        daily,
        np.full(24, 1 / 24),
        pd.Timestamp("2018-01-01"),
        config,
        model,
        np.random.default_rng(config.random_seed),
    )
    open_hours = [config.is_open(hour % 24) for hour in range(48)]
    staffing = np.where(open_hours, 4, 0)
    records = run_simulation(contacts, staffing)
    kpis = contact_kpis(records, staffing, config.service_level_threshold_seconds)
    assert len(records) == len(contacts) > 0
    assert 0 <= kpis["service_level"] <= 1
