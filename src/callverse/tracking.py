"""MLflow experiment tracking (params, metrics, artifacts, models) for every run.

``MLFLOW_TRACKING_URI`` overrides the URI of ``configs/app.yaml`` (Docker Compose
points it at the MLflow server). If MLflow is not installed, runs are not tracked
but the code still works.
"""

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from callverse.config import PROJECT_ROOT, load_yaml


def tracking_uri() -> str:
    """Absolute tracking URI (a relative ``sqlite:///mlflow.db`` is anchored at the project)."""
    uri = os.environ.get("MLFLOW_TRACKING_URI") or load_yaml("app")["mlflow"]["tracking_uri"]
    prefix = "sqlite:///"
    if uri.startswith(prefix) and not Path(uri.removeprefix(prefix)).is_absolute():
        return prefix + (PROJECT_ROOT / uri.removeprefix(prefix)).resolve().as_posix()
    return uri


def _set_experiment(mlflow: Any, name: str) -> None:
    """Create the experiment with artifacts under the project, then select it."""
    if mlflow.get_experiment_by_name(name) is None and not os.environ.get("MLFLOW_TRACKING_URI"):
        artifacts = PROJECT_ROOT / load_yaml("app")["mlflow"].get("artifact_dir", "mlruns")
        artifacts.mkdir(parents=True, exist_ok=True)
        mlflow.create_experiment(name, artifact_location=artifacts.resolve().as_uri())
    mlflow.set_experiment(name)


class _NullRun:
    """Stand-in when MLflow is missing: every logging call is ignored."""

    def __getattr__(self, name: str) -> Any:
        return lambda *args, **kwargs: None


@contextmanager
def mlflow_run(experiment: str, run_name: str, tags: dict[str, str] | None = None) -> Iterator[Any]:
    """Context manager yielding the ``mlflow`` module inside an active run.

    ``experiment`` is a key of ``mlflow.experiments`` in ``configs/app.yaml``.
    """
    try:
        import mlflow
    except ImportError:
        yield _NullRun()
        return
    mlflow.set_tracking_uri(tracking_uri())
    name = load_yaml("app")["mlflow"]["experiments"].get(experiment, experiment)
    _set_experiment(mlflow, name)
    with mlflow.start_run(run_name=run_name, tags=tags or {}):
        yield mlflow


def log_dataframe(run: Any, frame: Any, artifact_path: str, file_name: str) -> None:
    """Log a DataFrame as a CSV artifact."""
    import tempfile

    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / file_name
        frame.to_csv(path, index=False)
        run.log_artifact(str(path), artifact_path=artifact_path)


def recent_runs(max_results: int = 50) -> list[dict[str, Any]]:
    """Latest runs of every CallVerse experiment, for the MLOps page."""
    try:
        import mlflow
    except ImportError:
        return []
    mlflow.set_tracking_uri(tracking_uri())
    names = list(load_yaml("app")["mlflow"]["experiments"].values())
    experiments = [e for e in (mlflow.get_experiment_by_name(n) for n in names) if e]
    if not experiments:
        return []
    runs = mlflow.search_runs(
        experiment_ids=[e.experiment_id for e in experiments],
        max_results=max_results,
        order_by=["attributes.start_time DESC"],
        output_format="list",
    )
    by_id = {e.experiment_id: e.name for e in experiments}
    return [
        {
            "run_id": run.info.run_id,
            "run_name": run.info.run_name,
            "experiment": by_id.get(run.info.experiment_id),
            "status": run.info.status,
            "start_time": run.info.start_time,
            "metrics": {k: round(v, 4) for k, v in run.data.metrics.items()},
            "params": dict(run.data.params),
        }
        for run in runs
    ]
