"""Project paths and YAML settings shared by every layer.

Every module reads its assumptions from ``configs/*.yaml`` through this file, so a
value is defined once. Paths can be moved with the ``CALLVERSE_*`` environment
variables (see ``.env.example``).
"""

# How to read this file: it answers two questions for the whole project. 1. "Where are the files?" (the folder
# constants below: data/, artifacts/, configs/ ...) 2. "What are the settings?" (load_yaml reads
# configs/*.yaml)
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

# yaml reads the human-friendly settings files in configs/ (app.yaml, agents.yaml, ...).
import yaml


def _find_project_root() -> Path:
    """Folder holding ``configs/``: the env override, the CWD, or the source tree."""
    # 1) An explicit folder given in the CALLVERSE_ROOT environment variable always wins.
    override = os.environ.get("CALLVERSE_ROOT")
    if override:
        return Path(override).resolve()
    # 2) Otherwise walk up from the current folder (then from this file) until we find a folder that contains
    # configs/app.yaml: that folder is the project root.
    for start in (Path.cwd(), Path(__file__).resolve()):
        for folder in (start, *start.parents):
            if (folder / "configs" / "app.yaml").exists():
                return folder
    # 3) Last resort: two folders above this file (src/callverse/config.py -> the project root).
    return Path(__file__).resolve().parents[2]


# Computed once, the first time any module imports config.py.
PROJECT_ROOT = _find_project_root()


def _load_dotenv(path: Path) -> None:
    """Read ``KEY=VALUE`` lines of ``.env``; real environment variables win."""
    if not path.exists():
        return
    # One setting per line, written KEY=VALUE. Empty lines and # comments are skipped. This is how secrets
    # such as OPENROUTER_API_KEY reach the code: they live only in .env, which git ignores, never in a tracked
    # file.
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        # Remove the quotes around a value ("abc" or 'abc' -> abc).
        value = value.strip().strip('"').strip("'")
        # setdefault: a variable already set in the real environment is NOT overwritten by .env.
        if value:
            os.environ.setdefault(key.strip(), value)


# Load .env immediately, so every module imported after this one sees its values.
_load_dotenv(PROJECT_ROOT / ".env")
# Where everything lives. data/ holds the inputs and the prepared tables; artifacts/ holds what the pipeline
# produces (forecasts, trained policies, evaluations, LLM traces). Both can be moved with environment
# variables (useful in Docker).
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


# lru_cache remembers the result: each YAML file is read from disk only once per process.
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
