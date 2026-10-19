"""Forecast evaluation (DSO4 part 1): error vs the naive baseline."""

from typing import Any

import pandas as pd

from callverse.config import FORECAST_DIR
from callverse.forecasting import accuracy
from callverse.forecasting.predict import METRICS_FILE

__all__ = ["accuracy", "forecast_summary"]


def forecast_summary(forecast_dir=FORECAST_DIR) -> dict[str, Any]:
    """wMAPE table, the main model's gain over the seasonal naive, and the verdict."""
    path = forecast_dir / METRICS_FILE
    if not path.exists():
        return {"available": False}
    metrics = pd.read_csv(path)
    wmape = metrics.pivot(index="intent_group", columns="model", values="wMAPE_percent")
    total = metrics[metrics["intent_group"] == "total"].set_index("model")
    naive = float(total.loc["seasonal_naive", "wMAPE_percent"])
    main = float(total.loc["lightgbm", "wMAPE_percent"])
    gain = (naive - main) / naive * 100
    return {
        "available": True,
        "wmape": wmape.round(2).reset_index().to_dict("records"),
        "total": total.round(3).reset_index().to_dict("records"),
        "main_model": "lightgbm",
        "main_wmape": main,
        "naive_wmape": naive,
        "rmse_total": float(total.loc["lightgbm", "RMSE"]),
        "gain_vs_naive_percent": gain,
        "beats_baseline": gain > 0,
        "best_per_level": wmape.idxmin(axis=1).to_dict(),
    }
