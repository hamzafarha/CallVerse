"""Can the AI judge be trusted? Agreement with human grades (DSO2 metric).

- Cohen's kappa with quadratic weights: agreement on an ordinal 1-5 scale,
  corrected for chance (0 = chance, 1 = perfect; > 0.4 moderate, > 0.6 substantial).
- Spearman rank correlation: do judge and humans rank conversations alike?
- Exact and within-one-point agreement, easy to explain.

Human labels are entered on the dashboard's labeling page and stored in
``data/labels/human_quality_labels.csv``. Until enough exist, the synthetic
tickets give proxy labels (the generator's hidden answer key).
"""

from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.metrics import cohen_kappa_score

from callverse.agents.quality.rubric import CRITERIA
from callverse.config import PROJECT_ROOT, load_yaml

LABEL_COLUMNS = ["ticket_id", "labeler", "labeled_at", *CRITERIA, "comment"]


def labels_path() -> Path:
    return PROJECT_ROOT / load_yaml("agents")["quality"]["human_labels_file"]


def load_human_labels() -> pd.DataFrame:
    """Human grades entered on the labeling page (may be empty)."""
    path = labels_path()
    if not path.exists():
        return pd.DataFrame(columns=LABEL_COLUMNS)
    return pd.read_csv(path)


def save_human_label(row: dict) -> int:
    """Append one human grade; returns the number of labeled conversations."""
    path = labels_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame([{c: row.get(c) for c in LABEL_COLUMNS}])
    frame.to_csv(path, mode="a", header=not path.exists(), index=False)
    return int(load_human_labels()["ticket_id"].nunique())


def agreement(judge: pd.Series, human: pd.Series) -> dict[str, float]:
    """Agreement statistics between two series of 1-5 grades."""
    pairs = pd.DataFrame({"judge": judge, "human": human}).dropna().astype(int)
    n = len(pairs)
    if n < 2:
        return {
            "n": float(n),
            "quadratic_kappa": np.nan,
            "spearman": np.nan,
            "exact_agreement": np.nan,
            "within_one": np.nan,
        }
    same_values = pairs["judge"].nunique() == 1 and pairs["human"].nunique() == 1
    kappa = (
        1.0
        if same_values and (pairs["judge"] == pairs["human"]).all()
        else float(
            cohen_kappa_score(pairs["judge"], pairs["human"], weights="quadratic", labels=[1, 2, 3, 4, 5])
        )
    )
    rho = stats.spearmanr(pairs["judge"], pairs["human"]).statistic if not same_values else np.nan
    return {
        "n": float(n),
        "quadratic_kappa": kappa,
        "spearman": float(rho),
        "exact_agreement": float((pairs["judge"] == pairs["human"]).mean()),
        "within_one": float(((pairs["judge"] - pairs["human"]).abs() <= 1).mean()),
    }


def resolution_label(outcome_class: str) -> int:
    """Proxy resolution grade from the generator's outcome class."""
    return {"resolved_in_chat": 5, "follow_up": 3, "escalated": 2}.get(outcome_class, 3)


def calibration_table(judge_scores: pd.DataFrame, labels: pd.DataFrame, source: str) -> pd.DataFrame:
    """Agreement per criterion between judge scores and labels (joined on ticket_id)."""
    merged = judge_scores.merge(labels, on="ticket_id", suffixes=("_judge", "_label"))
    rows = []
    for criterion in CRITERIA:
        judge_col, label_col = f"{criterion}_judge", f"{criterion}_label"
        if judge_col not in merged or label_col not in merged:
            continue
        stats_row = agreement(merged[judge_col], merged[label_col])
        if stats_row["n"] >= 2:
            rows.append({"criterion": criterion, "label_source": source, **stats_row})
    return pd.DataFrame(rows)
