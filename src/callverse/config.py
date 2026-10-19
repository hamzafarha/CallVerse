"""Project paths and YAML settings shared by every layer.

Every module reads its assumptions from ``configs/*.yaml`` through this file, so a
value is defined once. Paths can be moved with the ``CALLVERSE_*`` environment
variables (see ``.env.example``).
"""

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


def _find_project_root() -> Path:
    """Folder holding ``configs/``: the env override, the CWD, or the source tree."""
    override = os.environ.get("CALLVERSE_ROOT")
    if override:
        return Path(override).resolve()
    for start in (Path.cwd(), Path(__file__).resolve()):
        for folder in (start, *start.parents):
            if (folder / "configs" / "app.yaml").exists():
                return folder
    return Path(__file__).resolve().parents[2]


PROJECT_ROOT = _find_project_root()


def _load_dotenv(path: Path) -> None:
    """Read ``KEY=VALUE`` lines of ``.env``; real environment variables win."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        if value:
            os.environ.setdefault(key.strip(), value)


_load_dotenv(PROJECT_ROOT / ".env")
CONFIG_DIR = PROJECT_ROOT / "configs"
DATA_DIR = PROJECT_ROOT / os.environ.get("CALLVERSE_DATA_DIR", "data")
ARTIFACTS_DIR = PROJECT_ROOT / os.environ.get("CALLVERSE_ARTIFACTS_DIR", "artifacts")
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
LABELS_DIR = DATA_DIR / "labels"
FORECAST_DIR = ARTIFACTS_DIR / "forecasts"
POLICY_DIR = ARTIFACTS_DIR / "policies"
EVALUATION_DIR = ARTIFACTS_DIR / "evaluations"
TRACE_DIR = ARTIFACTS_DIR / "traces"
NOTEBOOK_RUN_DIR = ARTIFACTS_DIR / "notebook_runs"


@lru_cache(maxsize=None)
def load_yaml(name: str) -> dict[str, Any]:
    """Parsed ``configs/<name>.yaml`` (cached; the files are read-only at runtime)."""
    with open(CONFIG_DIR / f"{name}.yaml", encoding="utf-8") as config_file:
        return yaml.safe_load(config_file) or {}


def config_path(name: str) -> Path:
    """Path of ``configs/<name>.yaml``."""
    return CONFIG_DIR / f"{name}.yaml"


def ensure_dirs() -> None:
    """Create the output folders (they are git-ignored apart from .gitkeep)."""
    for folder in (
        PROCESSED_DIR,
        LABELS_DIR,
        FORECAST_DIR,
        POLICY_DIR,
        EVALUATION_DIR,
        TRACE_DIR,
        NOTEBOOK_RUN_DIR,
    ):
        folder.mkdir(parents=True, exist_ok=True)


def database_path() -> Path:
    """SQLite store of orders, contacts, tickets and chats."""
    return PROJECT_ROOT / load_yaml("data")["database"]["path"]
