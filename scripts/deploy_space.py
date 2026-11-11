"""Put CallVerse online: build the folder of a Hugging Face Space, check it, then upload it.

The Space runs ONE Docker container (deploy/huggingface/Dockerfile) with the API and both web apps:
https://<user>-<space>.hf.space/ (front office) and .../back-office/ (back office).

What the script does, in order:
1. Copies what the Space needs into a staging folder, from an explicit list: never .env, keys or caches.
2. Removes private data from the copies (your own files do not change): the new customers you created (their
   names and problems), the live chat history, and the text previews of the LLM trace.
3. Writes space/constraints.txt with the versions of the key libraries in this environment, so the Space
   loads the saved models with the same versions that made them.
4. Checks the folder: no secret (API key, token, private key) and none of the removed names.
5. Uploads it to the Space (created if needed). Hugging Face then builds the image and starts it; the script
   follows the build and prints the end of the log if it fails.

Log in once first (a token with "write" access):   .venv\\Scripts\\hf auth login
Deploy, or update, with the project's Python:      .venv\\Scripts\\python scripts\\deploy_space.py
Only build and check the folder (no upload):       .venv\\Scripts\\python scripts\\deploy_space.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import time
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = PROJECT_ROOT / "deploy" / "huggingface"
MARKER = ".callverse-space"  # marks a staging folder made by this script: only such a folder is emptied

# What the Space needs, relative to the project. Everything else stays on this computer.
CODE = ["pyproject.toml", "src", "configs", "frontend"]
DATA = [
    "data/callverse.db",  # orders, customers, tickets, chats (cleaned below)
    "data/processed",  # the prepared datasets that the pages read
    "data/knowledge_base",  # help-centre documents and their search index (RAG)
    "data/external",  # the list of Brazilian banks (BrasilAPI)
    "artifacts/evaluations",
    "artifacts/forecasts",
    "artifacts/policies",  # trained models: intent classifier, PPO routing, staffing plans
    "artifacts/notebook_runs",
    "artifacts/traces/conversations",  # evaluation chats between AI customers and the advisor
    "artifacts/traces/llm_calls.jsonl",  # LLM trace of the monitoring page (text previews removed below)
    "artifacts/traces/llm_models.lock.json",
    "artifacts/traces/simulation_baseline_trace_example.parquet",
    "mlflow.db",
    "mlruns",
]
# Real chats typed by you and your team: only uploaded with --keep-private-data.
PRIVATE = ["artifacts/traces/live_sessions"]
TRACE = "artifacts/traces/llm_calls.jsonl"
TRACE_TEXT_FIELDS = ("input_preview", "output_preview")
DATABASE = "data/callverse.db"

# Never copied, wherever they are.
SKIP_DIRS = {
    "node_modules",
    "dist",
    "certs",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    ".vite",
}
SKIP_SUFFIXES = {".pyc", ".pyo", ".tsbuildinfo", ".log", ".key", ".pem", ".crt", ".p12", ".pfx"}

# Libraries pinned to this environment's versions: they wrote the saved models, the MLflow database and the
# search index, or they serve the app.
PINNED = [
    "numpy", "pandas", "pyarrow", "scipy", "scikit-learn", "joblib", "torch", "transformers", "tokenizers",
    "safetensors", "sentence-transformers", "huggingface-hub", "faiss-cpu", "accelerate", "stable-baselines3",
    "sb3-contrib", "gymnasium", "lightgbm", "statsmodels", "prophet", "cmdstanpy", "mlflow", "fastapi",
    "starlette", "uvicorn", "pydantic", "mcp", "langgraph", "ortools", "simpy", "pandera",
]  # fmt: skip

SECRETS = {
    "an OpenRouter key": re.compile(rb"sk-or-v1-[0-9a-f]{16,}"),
    "a Hugging Face token": re.compile(rb"\bhf_[A-Za-z0-9]{30,}"),
    "a private key": re.compile(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
}
# Files whose bytes are searched (text files and SQLite databases).
SCANNED = {
    ".py", ".ts", ".tsx", ".js", ".json", ".jsonl", ".yaml", ".yml", ".toml", ".md", ".txt", ".csv", ".html",
    ".css", ".ini", ".cfg", ".db", ".sqlite",
}  # fmt: skip
# Stages of a Space while Hugging Face builds and starts it, and the stages of a failure.
BUILDING = {"BUILDING", "RUNNING_BUILDING", "APP_STARTING", "RUNNING_APP_STARTING"}
FAILED = {"BUILD_ERROR", "RUNTIME_ERROR", "CONFIG_ERROR", "NO_APP_FILE"}


# --------------------------------------------------------------------------------------------- 1. copy
def prepare_folder(staging: Path) -> None:
    """Start from an empty staging folder (only a folder made by this script is ever emptied)."""
    if staging.exists():
        if any(staging.iterdir()) and not (staging / MARKER).exists():
            sys.exit(f"{staging} is not empty and was not made by this script: choose another --staging.")
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    (staging / MARKER).write_text("made by scripts/deploy_space.py\n", encoding="utf-8")


def _skipped(_: str, names: list[str]) -> set[str]:
    return {
        name
        for name in names
        if name in SKIP_DIRS
        or name.startswith(".env")
        or name.endswith(".egg-info")
        or Path(name).suffix.lower() in SKIP_SUFFIXES
    }


def copy_sqlite(source: Path, target: Path) -> None:
    """Copy a SQLite database with SQLite's own backup: a consistent copy, even while the API uses it."""
    target.parent.mkdir(parents=True, exist_ok=True)
    original = sqlite3.connect(f"{source.resolve().as_uri()}?mode=ro", uri=True)  # read-only: never changed
    copy = sqlite3.connect(target)
    try:
        original.backup(copy)
    finally:
        original.close()
        copy.close()


def copy_item(source: Path, target: Path) -> None:
    if source.suffix in (".db", ".sqlite"):
        copy_sqlite(source, target)
    elif source.is_file():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    else:
        shutil.copytree(source, target, ignore=_skipped, copy_function=shutil.copyfile, dirs_exist_ok=True)


def write_constraints(path: Path) -> list[str]:
    """Pin the key libraries to this environment's versions (torch without its +cu126 / +cpu suffix)."""
    pins = []
    for name in PINNED:
        try:
            pins.append(f"{name}=={version(name).split('+')[0]}")
        except PackageNotFoundError:
            continue
    path.parent.mkdir(parents=True, exist_ok=True)
    header = (
        "# Versions of the environment that made the saved models (written by scripts/deploy_space.py).\n"
    )
    path.write_text(header + "\n".join(pins) + "\n", encoding="utf-8")
    return pins


def write_card(staging: Path, space_url: str) -> None:
    """The Space's README.md: the settings Hugging Face reads (YAML at the top) and the visitors' notes."""
    card = (TEMPLATE_DIR / "README.md").read_text(encoding="utf-8")
    (staging / "README.md").write_text(card.replace("{{SPACE_URL}}", space_url), encoding="utf-8")


# ------------------------------------------------------------------------------------ 2. private data
def clean_database(database: Path) -> list[str]:
    """Delete the new customers (and their invented orders) from the COPY; return their names."""
    from callverse.data.new_customers import delete_new_customer, list_new_customers

    try:
        customers = list_new_customers(db_path=database)
    except sqlite3.OperationalError:  # no new_customers table yet
        customers = []
    for customer in customers:
        delete_new_customer(customer["contact_id"], db_path=database)
    # VACUUM rewrites the file: deleted rows would otherwise stay readable in its free pages.
    connection = sqlite3.connect(database)
    try:
        connection.execute("VACUUM")
    finally:
        connection.close()
    return [str(customer["name"]) for customer in customers if customer.get("name")]


def clean_trace(path: Path) -> int:
    """Keep the numbers of each LLM call (model, tokens, latency, tools) but drop its text previews."""
    if not path.exists():
        return 0
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            record = json.loads(line)
        except ValueError:
            continue  # an empty or half-written line
        for field in TRACE_TEXT_FIELDS:
            record.pop(field, None)
        records.append(json.dumps(record, ensure_ascii=False))
    path.write_text("\n".join(records) + "\n", encoding="utf-8")
    return len(records)


# ------------------------------------------------------------------------------------------- 3. check
def scan(staging: Path, names: list[str]) -> list[str]:
    """What must stop the upload: an .env file, a secret, or a removed customer's name in the data."""
    # Plain text search, without word boundaries: SQLite stores the columns of a row side by side, so a name
    # touches its neighbours ("NC000001Hamza...") and a whole-word search would never find it.
    words = sorted({word for name in names for word in (name, *name.split()) if len(word) >= 4})
    name_pattern = re.compile(b"|".join(re.escape(w.encode()) for w in words)) if words else None
    data_parts = ("data/", "artifacts/", "mlruns/", "mlflow.db")
    problems = [f"{path.relative_to(staging).as_posix()}: an .env file" for path in staging.rglob(".env*")]
    for path in sorted(staging.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SCANNED:
            continue
        relative, content = path.relative_to(staging).as_posix(), path.read_bytes()
        problems += [
            f"{relative}: looks like {label}" for label, rule in SECRETS.items() if rule.search(content)
        ]
        if name_pattern and relative.startswith(data_parts):
            found = sorted({match.group().decode() for match in name_pattern.finditer(content)})
            if found:
                problems.append(f"{relative}: still contains {', '.join(found)}")
    return problems


def describe(staging: Path) -> None:
    files = [path for path in staging.rglob("*") if path.is_file()]
    total = sum(path.stat().st_size for path in files)
    print(f"    {len(files)} files, {total / 1e6:.0f} MB. Biggest:")
    for path in sorted(files, key=lambda p: p.stat().st_size, reverse=True)[:5]:
        print(f"      {path.stat().st_size / 1e6:6.1f} MB  {path.relative_to(staging).as_posix()}")


# ------------------------------------------------------------------------------------------ 4. upload
def space_url(api: Any, repo_id: str) -> str:
    """The app's own address, e.g. https://owner-callverse.hf.space."""
    host = getattr(api.space_info(repo_id), "host", None)
    return (
        host.rstrip("/") if host else "https://" + re.sub(r"[^a-z0-9]+", "-", repo_id.lower()) + ".hf.space"
    )


def print_log(repo_id: str, kind: str, last: int = 60) -> None:
    """Print the end of the Space's build or run log (a stream of server-sent events)."""
    import httpx
    from huggingface_hub import get_token

    url = f"https://huggingface.co/api/spaces/{repo_id}/logs/{kind}"
    lines: list[str] = []
    try:
        headers = {"Authorization": f"Bearer {get_token()}"}
        with httpx.stream("GET", url, headers=headers, timeout=httpx.Timeout(20, read=10)) as response:
            for line in response.iter_lines():
                if line.startswith("data:"):
                    try:
                        lines.append(str(json.loads(line[5:]).get("data", "")).rstrip())
                    except ValueError:
                        lines.append(line[5:].strip())
    except httpx.HTTPError:
        pass  # the stream stays open for new lines: the read timeout ends it
    print(f"--- last lines of the {kind} log ---")
    print("\n".join(lines[-last:]) or "(empty)")


def follow_build(api: Any, repo_id: str, minutes: int = 45) -> bool:
    """Print each stage of the build until the Space runs (True) or fails (False)."""
    print("    Following the build (Ctrl+C stops watching; the build goes on).")
    start, last_stage, started = time.time(), None, False
    while time.time() - start < minutes * 60:
        stage = api.get_space_runtime(repo_id).stage
        stage = str(getattr(stage, "value", stage))  # plain text here; an enum in some versions
        if stage != last_stage:
            print(f"      {time.strftime('%H:%M:%S')}  {stage}")
            last_stage = stage
        started = started or stage in BUILDING
        # Right after the upload, the stage can still be the previous build's: trust it once the new build
        # has started, or after 3 minutes.
        settled = started or time.time() - start > 180
        if stage == "RUNNING" and settled:
            return True
        if stage in FAILED and settled:
            print_log(repo_id, "build" if stage in ("BUILD_ERROR", "CONFIG_ERROR") else "run")
            return False
        time.sleep(15)
    print("    Still not running: look at the logs on the Space page.")
    return False


def upload(staging: Path, space: str, private: bool, wait: bool) -> None:
    # The project's .env keeps the Hugging Face hub offline (HF_HUB_OFFLINE=1, so the app never downloads a
    # model during a demo), and cleaning the database loaded it. This upload needs the hub online.
    os.environ["HF_HUB_OFFLINE"] = "0"
    from huggingface_hub import HfApi, constants

    constants.HF_HUB_OFFLINE = False
    api = HfApi()
    try:
        user = api.whoami()["name"]
    except Exception as error:  # noqa: BLE001 - shown to the user as it is
        sys.exit(f"Cannot use your Hugging Face login ({error}). Log in with .venv\\Scripts\\hf auth login.")
    repo_id = space if "/" in space else f"{user}/{space}"
    print(f"    Space {repo_id} ({'private' if private else 'public'})")
    # An existing Space is only updated if this script made it: the upload replaces all of a Space's files.
    if api.repo_exists(repo_id, repo_type="space"):
        files = set(api.list_repo_files(repo_id, repo_type="space"))
        if files - {".gitattributes", "README.md"} and "space/constraints.txt" not in files:
            sys.exit(f"The Space {repo_id} already exists with other files: choose another --space name.")
    api.create_repo(repo_id, repo_type="space", space_sdk="docker", private=private, exist_ok=True)
    url = space_url(api, repo_id)
    write_card(staging, url)
    print("    Uploading (the database and datasets take a few minutes on a slow connection)...")
    # delete_patterns="*": files removed from the project leave the Space too (.gitattributes always stays).
    commit = api.upload_folder(
        repo_id=repo_id,
        repo_type="space",
        folder_path=staging,
        commit_message="Deploy CallVerse",
        ignore_patterns=[MARKER],
        delete_patterns="*",
    )
    print(f"    Uploaded: {commit.commit_url}")
    running = follow_build(api, repo_id) if wait else None
    print(
        f"\nFront office: {url}/\nBack office:  {url}/back-office/\nSpace page:   https://huggingface.co/spaces/{repo_id}"
    )
    if running is False:
        sys.exit("The Space did not start: see the log above.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--space", default="callverse", help="Space name, or owner/name (default: callverse)")
    parser.add_argument(
        "--private", action="store_true", help="create the Space as private (only you see it)"
    )
    parser.add_argument(
        "--staging",
        type=Path,
        default=Path(tempfile.gettempdir()) / "callverse-space",
        help="where the folder is built (default: your temporary folder, outside OneDrive)",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="build and check the folder, but do not upload"
    )
    parser.add_argument(
        "--keep-private-data",
        action="store_true",
        help="also upload your new customers, your live chat history and the trace's text previews",
    )
    parser.add_argument("--no-wait", action="store_true", help="do not follow the build after the upload")
    args = parser.parse_args()
    staging = build_staging(args.staging.resolve(), args.keep_private_data)
    if args.dry_run:
        print(f"Dry run: nothing uploaded. The folder is ready to look at: {staging}")
        return
    print("4/4 Uploading to Hugging Face")
    upload(staging, args.space, args.private, wait=not args.no_wait)


def build_staging(staging: Path, keep_private: bool = False) -> Path:
    """Steps 1-3: copy what the container needs, remove the private data, check. Also used by
    deploy_azure.py: the folder is the Docker build context, wherever the image is built."""
    print(f"1/4 Copying what the container needs to {staging}")
    prepare_folder(staging)
    for item in CODE + DATA + (PRIVATE if keep_private else []):
        if (PROJECT_ROOT / item).exists():
            copy_item(PROJECT_ROOT / item, staging / item)
        else:
            print(f"    (not found, skipped) {item}")
    shutil.copyfile(TEMPLATE_DIR / "Dockerfile", staging / "Dockerfile")
    write_card(staging, "https://<user>-<space>.hf.space")  # replaced by the real address on upload
    pins = write_constraints(staging / "space" / "constraints.txt")
    print(f"    Pinned {len(pins)} libraries to this environment's versions (space/constraints.txt).")

    names: list[str] = []
    if keep_private:
        print("2/4 Private data KEPT (--keep-private-data)")
    else:
        names = clean_database(staging / DATABASE)
        calls = clean_trace(staging / TRACE)
        print(f"2/4 Removed {len(names)} new customers, the live chats and the text of {calls} LLM calls")

    print("3/4 Checking for secrets and private names")
    problems = scan(staging, names)
    if problems:
        print("\n".join(f"    PROBLEM {problem}" for problem in problems))
        sys.exit("Nothing was uploaded.")
    describe(staging)
    return staging


if __name__ == "__main__":
    main()
