"""Headless runner for the data-preparation notebooks (Phases 1C to 1E).

The notebooks are the documented, reviewed source of every data decision
(cleaning flags, analytical features, contact rates, promo calendar, synthetic
contacts). Instead of copying their logic into modules, the pipeline executes them
in order, top to bottom, exactly as a reviewer would, and keeps an executed copy
as proof of the run (``artifacts/notebook_runs/``).
"""

import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from callverse.config import NOTEBOOK_RUN_DIR, PROJECT_ROOT, RAW_DIR, load_yaml

REQUIRED_RAW_FILES = [
    "olist/olist_orders_dataset.csv",
    "olist/olist_order_items_dataset.csv",
    "olist/olist_customers_dataset.csv",
    "olist/olist_order_payments_dataset.csv",
    "olist/olist_order_reviews_dataset.csv",
    "olist/olist_products_dataset.csv",
    "olist/olist_sellers_dataset.csv",
    "olist/product_category_name_translation.csv",
    "bitext/bitext-retail-ecommerce-llm-chatbot-training-dataset.csv",
]


@dataclass(frozen=True)
class NotebookRun:
    """Result of one executed notebook."""

    notebook: str
    seconds: float
    output_path: Path


def missing_raw_files(raw_dir: Path = RAW_DIR) -> list[str]:
    """Raw inputs that are not on disk (Olist and Bitext must be downloaded)."""
    return [name for name in REQUIRED_RAW_FILES if not (raw_dir / name).exists()]


def run_notebook(path: Path, output_dir: Path = NOTEBOOK_RUN_DIR, timeout: int = 1800) -> NotebookRun:
    """Execute one notebook with its own folder as working directory."""
    import nbformat
    from nbclient import NotebookClient

    notebook = nbformat.read(path, as_version=4)
    client = NotebookClient(
        notebook,
        timeout=timeout,
        kernel_name="python3",
        resources={"metadata": {"path": str(path.parent)}},
    )
    start = time.perf_counter()
    client.execute()
    seconds = time.perf_counter() - start
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / path.name
    nbformat.write(notebook, output_path)
    return NotebookRun(path.name, seconds, output_path)


def run_data_pipeline(
    notebooks: list[str] | None = None,
    log: Callable[[str], None] = print,
) -> list[NotebookRun]:
    """Execute the configured notebooks in order; stops at the first failure."""
    missing = missing_raw_files()
    if missing:
        raise FileNotFoundError(
            "Raw data missing: " + ", ".join(missing) + ". See docs/RUN_GUIDE.md, section 'Get the raw data'."
        )
    settings = load_yaml("data")["pipeline"]
    names = notebooks or settings["notebooks"]
    runs = []
    for name in names:
        log(f"  running notebooks/{name} ...")
        run = run_notebook(
            PROJECT_ROOT / "notebooks" / name,
            timeout=int(settings["timeout_seconds"]),
        )
        log(f"  done in {run.seconds:.0f}s -> {run.output_path.relative_to(PROJECT_ROOT)}")
        runs.append(run)
    return runs
