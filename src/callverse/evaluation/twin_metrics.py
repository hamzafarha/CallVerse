"""Twin fidelity metrics (DSO4 part 2): saved for the report and the dashboard."""

from typing import Any

from callverse.config import EVALUATION_DIR, ensure_dirs
from callverse.twin.calibration import fidelity_report


def run_fidelity(week_start: str = "2018-05-07", weeks: int = 4) -> dict[str, Any]:
    """Run the fidelity checks and save their tables."""
    ensure_dirs()
    report = fidelity_report(week_start, weeks)
    report["checks"].to_csv(EVALUATION_DIR / "twin_fidelity_checks.csv", index=False)
    report["erlang"].to_csv(EVALUATION_DIR / "twin_fidelity_erlang.csv", index=False)
    report["hourly_profile"].to_csv(EVALUATION_DIR / "twin_fidelity_hourly.csv", index=False)
    report["daily"].to_csv(EVALUATION_DIR / "twin_fidelity_daily.csv", index=False)
    return report
