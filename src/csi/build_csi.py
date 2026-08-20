"""
Phase-3 step 2: builds the composite Concentration State Index from the
three components selected in the collinearity check
(docs/methodology_notes/csi_construction.md, "Decision (2026-08-20)"):
`hhi`, `cr_10`, `entropy_concentration`. `effective_n` is excluded
(deterministic identity with `hhi`); `cr_5`/`cr_7` remain standalone
diagnostics, not composite inputs.

CSI_t = mean(z_hhi,t, z_cr_10,t, z_entropy_concentration,t) — equal-weight
z-score average (Option B). No sign-flip needed: all three retained
components already have direction +1 (higher = more concentrated).

Standardization: expanding window ending at t (inclusive), burn-in 24
months. Both parameters are documented with their rationale and listed as
Phase-6 robustness variants in docs/variable_definitions/csi.md — read
that file before changing either value here.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.utils.paths import CONCENTRATION_FINAL, CSI_FINAL, LOGS, latest_raw_file  # noqa: E402

logger = logging.getLogger(__name__)

COMPONENTS = ["hhi", "cr_10", "entropy_concentration"]
BURN_IN_MONTHS = 24
RUN_TAG = datetime.now(timezone.utc).strftime("%Y%m%d")


def expanding_zscore(series: pd.Series, burn_in: int = BURN_IN_MONTHS) -> pd.Series:
    """Expanding-window z-score, inclusive of t, with ddof=1 (sample std).

    The window used to standardize the value at t is [start of series, t]
    — it grows every period, so it is point-in-time valid (never uses
    data after t) but NOT frozen against future re-runs: standardizing
    the same historical date again after more months have been appended
    changes the mean/std used for it. See docs/variable_definitions/csi.md
    ("Expanding window: a trade-off, stated explicitly").

    The first `burn_in` observations get NaN (excluded, not backfilled)
    because a std computed on very few points is unstable — see
    docs/variable_definitions/csi.md for why 24 was chosen over 12/36.
    """
    expanding_mean = series.expanding(min_periods=burn_in).mean()
    expanding_std = series.expanding(min_periods=burn_in).std(ddof=1)
    return (series - expanding_mean) / expanding_std


def build_csi(panel: pd.DataFrame, burn_in: int = BURN_IN_MONTHS) -> pd.DataFrame:
    panel = panel.sort_values("date").set_index("date")

    z_cols = {}
    for comp in COMPONENTS:
        z_cols[f"z_{comp}"] = expanding_zscore(panel[comp], burn_in)

    z_df = pd.DataFrame(z_cols, index=panel.index)
    csi = z_df.mean(axis=1, skipna=False)  # all 3 must be defined (post burn-in) — no partial average

    out = pd.concat([csi.rename("csi"), z_df, panel[COMPONENTS]], axis=1)
    out = out.dropna(subset=["csi"]).reset_index()
    return out


def _configure_logging() -> Path:
    LOGS.mkdir(parents=True, exist_ok=True)
    log_path = LOGS / f"build_csi_{RUN_TAG}.txt"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(log_path), logging.StreamHandler()],
    )
    return log_path


def main() -> None:
    log_path = _configure_logging()
    logger.info("Logging to %s", log_path)
    logger.info(
        "CSI construction parameters: components=%s, weighting=equal, "
        "standardization=expanding z-score (ddof=1), burn_in_months=%d "
        "(see docs/methodology_notes/csi_construction.md 'Decision (2026-08-20)' "
        "and docs/variable_definitions/csi.md)",
        COMPONENTS,
        BURN_IN_MONTHS,
    )

    panel_path = latest_raw_file(CONCENTRATION_FINAL, "concentration_measures_monthly")
    logger.info("Loading concentration panel: %s", panel_path)
    panel = pd.read_csv(panel_path, parse_dates=["date"])

    result = build_csi(panel)
    logger.info(
        "Built %d monthly CSI observations, %s to %s (%d months excluded by burn-in)",
        len(result),
        result["date"].min(),
        result["date"].max(),
        len(panel) - len(result),
    )
    logger.info(
        "CSI summary: mean=%.4f, std=%.4f, min=%.4f (%s), max=%.4f (%s)",
        result["csi"].mean(),
        result["csi"].std(),
        result["csi"].min(),
        result.loc[result["csi"].idxmin(), "date"],
        result["csi"].max(),
        result.loc[result["csi"].idxmax(), "date"],
    )

    CSI_FINAL.mkdir(parents=True, exist_ok=True)
    out_path = CSI_FINAL / f"csi_composite_monthly_{RUN_TAG}.csv"
    result.to_csv(out_path, index=False)
    logger.info("Wrote %s", out_path)


if __name__ == "__main__":
    main()
