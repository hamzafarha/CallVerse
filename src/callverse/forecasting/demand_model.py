"""Main DSO4 forecast: one global LightGBM model for all intent groups.

Contacts per day are counts, so the model uses a Poisson objective. One model for
the four groups (with ``group_code`` as a categorical feature) has four times more
training rows than one model per group.
"""

from pathlib import Path

import numpy as np
import pandas as pd

from callverse.forecasting.features import TRAIN_START, FeatureSet

LIGHTGBM_PARAMS = {
    "objective": "poisson",
    "learning_rate": 0.05,
    "n_estimators": 400,
    "num_leaves": 15,
    "min_child_samples": 20,
    "subsample": 0.8,
    "subsample_freq": 1,
    "colsample_bytree": 0.8,
    "random_state": 42,
    "deterministic": True,
    "force_row_wise": True,
    "verbose": -1,
}


def fit_lightgbm(feature_set: FeatureSet, train_end: pd.Timestamp, train_start: pd.Timestamp = TRAIN_START):
    """Fit on every day from ``train_start`` to ``train_end`` (inclusive)."""
    import lightgbm as lgb

    panel = feature_set.panel
    train = panel[(panel["date"] >= train_start) & (panel["date"] <= train_end)]
    train = train[train["contacts"].notna()]
    model = lgb.LGBMRegressor(**LIGHTGBM_PARAMS)
    model.fit(train[feature_set.features], train["contacts"], categorical_feature=["group_code"])
    return model


def predict_days(model, feature_set: FeatureSet, days: pd.DatetimeIndex) -> pd.DataFrame:
    """Forecast every group for the given days (columns date, intent_group, forecast)."""
    rows = feature_set.panel[feature_set.panel["date"].isin(days)]
    if rows[feature_set.features].isna().any().any():
        raise ValueError("Missing feature values: the days are too far ahead (max 7).")
    result = rows[["date", "intent_group"]].copy()
    result["forecast"] = np.clip(model.predict(rows[feature_set.features]), 0, None)
    return result.reset_index(drop=True)


def feature_importance(model, features: list[str]) -> pd.DataFrame:
    """Share of total gain per feature (%), largest first."""
    gain = pd.Series(model.booster_.feature_importance(importance_type="gain"), index=features)
    share = (gain / gain.sum() * 100).sort_values(ascending=False).round(2)
    return share.rename("gain_percent").rename_axis("feature").reset_index()


def save_model(model, path: str | Path) -> None:
    """Write the booster as text (readable, versionable)."""
    model.booster_.save_model(str(path))


def load_booster(path: str | Path):
    """Load a saved booster (predict with ``booster.predict(X)``)."""
    import lightgbm as lgb

    return lgb.Booster(model_file=str(path))
