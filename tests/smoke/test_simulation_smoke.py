"""Smoke tests for CallVerse package, CLI, and simulation."""

import importlib
import pkgutil

import callverse
import pytest
from callverse.main import app
from typer.testing import CliRunner

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
    """Placeholder simulation smoke test for Phase 2."""
    pytest.skip("phase 2")
