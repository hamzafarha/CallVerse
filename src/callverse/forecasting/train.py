"""Forecast stage: backtest, final model, next-week forecast, MLflow run."""

from collections.abc import Callable
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from callverse.config import FORECAST_DIR, ensure_dirs  # noqa: E402
from callverse.data import loaders  # noqa: E402
from callverse.forecasting.backtest import (  # noqa: E402
    ALL_MODELS,
    FAST_MODELS,
    integrity_checks,
    run_backtest,
)
from callverse.forecasting.demand_model import (  # noqa: E402
    LIGHTGBM_PARAMS,
    feature_importance,
    fit_lightgbm,
    save_model,
)
from callverse.forecasting.features import (  # noqa: E402
    EVAL_END,
    build_date_features,
    build_panel,
    contact_series,
    leakage_check,
)
from callverse.forecasting.predict import (  # noqa: E402
    BACKTEST_FILE,
    METRICS_FILE,
    MODEL_FILE,
    NEXT_WEEK_FILE,
    ForecastInputs,
    forecast_next_week,
)
from callverse.tracking import log_dataframe, mlflow_run  # noqa: E402


def load_inputs() -> ForecastInputs:
    """Processed tables written by the data pipeline."""
    return ForecastInputs(
        daily_group=loaders.daily_contacts_by_group(),
        daily_activity=loaders.daily_activity(),
        orders=loaders.orders_analytical(),
        daily_calendar=loaders.daily_calendar(),
        events=loaders.promo_events(),
    )


def plot_total(predictions: pd.DataFrame, path) -> None:
    """Actual vs LightGBM forecast, total contacts per day."""
    total = predictions[
        (predictions["intent_group"] == "total") & (predictions["model"] == "lightgbm")
    ].sort_values("date")
    figure, axis = plt.subplots(figsize=(11, 4.2))
    axis.plot(total["date"], total["actual"], color="#2a78d6", linewidth=2, label="Actual")
    axis.plot(total["date"], total["forecast"], color="#eb6834", linewidth=2, label="LightGBM")
    axis.set_title("Daily contacts: actual vs 1-7-day-ahead forecast (total)", loc="left")
    axis.set_ylabel("Contacts per day")
    axis.set_ylim(bottom=0)
    axis.grid(axis="y", color="#e6e5e1", linewidth=0.8)
    axis.spines[["top", "right"]].set_visible(False)
    axis.legend(frameon=False, loc="upper left")
    figure.tight_layout()
    figure.savefig(path, dpi=150)
    plt.close(figure)


def run_forecast_stage(fast: bool = False, log: Callable[[str], None] = print) -> dict[str, Any]:
    """Backtest every model, save artifacts and the final model, log to MLflow."""
    ensure_dirs()
    inputs = load_inputs()
    series = contact_series(inputs.daily_group)
    date_features = build_date_features(
        inputs.daily_activity, inputs.orders, inputs.daily_calendar, inputs.events
    )
    feature_set = build_panel(series, date_features)
    if not leakage_check(feature_set, series, "2018-03-15"):
        raise RuntimeError("Leakage guard failed: lag_7 is not 7 days old.")
    models = FAST_MODELS if fast else ALL_MODELS
    log(f"Backtesting {len(models)} models: {', '.join(models)}")
    result = run_backtest(series, feature_set, inputs.daily_calendar, models, log=log)
    checks = integrity_checks(result, len(feature_set.groups), len(models))
    if not checks["passed"].all():
        raise RuntimeError(f"Backtest integrity checks failed:\n{checks}")

    final_model = fit_lightgbm(feature_set, train_end=EVAL_END)
    importance = feature_importance(final_model, feature_set.features)
    next_week = forecast_next_week(inputs)

    result.predictions.to_parquet(FORECAST_DIR / BACKTEST_FILE, index=False)
    result.metrics.to_csv(FORECAST_DIR / METRICS_FILE, index=False)
    save_model(final_model, FORECAST_DIR / MODEL_FILE)
    importance.to_csv(FORECAST_DIR / "lightgbm_feature_importance.csv", index=False)
    next_week.to_csv(FORECAST_DIR / NEXT_WEEK_FILE, index=False)
    plot_path = FORECAST_DIR / "contact_forecast_backtest_total.png"
    plot_total(result.predictions, plot_path)

    wmape = result.wmape_table()
    gain = result.beats_naive("lightgbm", "total")
    with mlflow_run("forecast", "lightgbm_rolling_backtest", {"dso": "DSO4"}) as run:
        run.log_params(
            {
                **{f"lgbm_{k}": v for k, v in LIGHTGBM_PARAMS.items()},
                "models": ",".join(models),
                "horizon_days": 7,
                "origins": result.predictions["origin"].nunique(),
            }
        )
        for level, row in wmape.iterrows():
            for model_name, value in row.items():
                run.log_metric(f"wmape_{level}_{model_name}", float(value))
        total_lgbm = result.metrics.query("intent_group == 'total' and model == 'lightgbm'").iloc[0]
        run.log_metrics(
            {
                "wmape_total": float(total_lgbm["wMAPE_percent"]),
                "rmse_total": float(total_lgbm["RMSE"]),
                "mae_total": float(total_lgbm["MAE"]),
                "bias_total_percent": float(total_lgbm["bias_percent"]),
                "gain_vs_naive_percent": gain,
            }
        )
        run.log_artifact(str(plot_path))
        run.log_artifact(str(FORECAST_DIR / MODEL_FILE), artifact_path="model")
        log_dataframe(run, result.metrics, "metrics", "backtest_metrics.csv")
        log_dataframe(run, importance, "metrics", "feature_importance.csv")

    log("wMAPE % (lower is better):\n" + wmape.round(1).to_string())
    log(f"LightGBM vs same-day-last-week (total): {gain:+.1f}% wMAPE reduction")
    return {
        "wmape": wmape,
        "gain_vs_naive_percent": gain,
        "checks": checks,
        "sarima_problems": result.sarima_problems,
    }
