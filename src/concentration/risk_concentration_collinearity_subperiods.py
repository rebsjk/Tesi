"""
Sub-period breakdown of the cross-dimension collinearity check
(`risk_concentration_collinearity_check.py`) — Pearson/Spearman, levels and
first differences, split into pre-2010 / 2010-2019 / 2020-2026, to test
whether the risk-concentration-vs-capital-concentration relationship is
stable over time or specific to a sub-period (e.g. the Mag7/AI era).

Not a new measure or a new production artifact — a diagnostic extension of
the full-sample check, run once for the 2026-08-25 review discussion. Reuses
`load_merged_series` from the full-sample script rather than redefining the
merge.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.concentration.risk_concentration_collinearity_check import (  # noqa: E402
    CAPITAL_SERIES_COLS,
    RISK_SERIES_COLS,
    load_merged_series,
)
from src.utils.paths import LOGS, TABLES  # noqa: E402

RUN_TAG = datetime.now(timezone.utc).strftime("%Y%m%d")
SUBPERIODS = [
    ("pre2010", None, "2009-12-31"),
    ("2010_2019", "2010-01-01", "2019-12-31"),
    ("2020_2026", "2020-01-01", None),
]

logger = logging.getLogger(__name__)


def _configure_logging() -> Path:
    LOGS.mkdir(parents=True, exist_ok=True)
    log_path = LOGS / f"risk_concentration_collinearity_subperiods_{RUN_TAG}.txt"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(log_path), logging.StreamHandler()],
    )
    return log_path


def main() -> None:
    log_path = _configure_logging()
    logger.info("Logging to %s", log_path)

    df = load_merged_series()
    cross_cols = RISK_SERIES_COLS + CAPITAL_SERIES_COLS

    TABLES.mkdir(parents=True, exist_ok=True)

    for label, start, end in SUBPERIODS:
        sub = df.copy()
        if start:
            sub = sub[sub.index >= start]
        if end:
            sub = sub[sub.index <= end]

        n = len(sub)
        logger.info("=" * 70)
        logger.info("[%s] n=%d months, %s to %s", label, n, sub.index.min(), sub.index.max())

        levels = sub[cross_cols]
        diffs = levels.diff().dropna(how="all")

        pear_lv = levels.corr(method="pearson")
        spear_lv = levels.corr(method="spearman")
        pear_df = diffs.corr(method="pearson")
        spear_df = diffs.corr(method="spearman")

        for name, corr in [
            ("pearson_levels", pear_lv), ("spearman_levels", spear_lv),
            ("pearson_diff", pear_df), ("spearman_diff", spear_df),
        ]:
            path = TABLES / f"risk_concentration_cross_dimension_correlation_{name}_{label}_{RUN_TAG}.csv"
            corr.to_csv(path)
            logger.info("Wrote %s", path)

        # Report only risk-vs-capital pairs, both bases, all four stats
        for risk_col in RISK_SERIES_COLS:
            for cap_col in CAPITAL_SERIES_COLS:
                logger.info(
                    "  %s / %s: levels pearson=%.3f spearman=%.3f | diff pearson=%.3f spearman=%.3f",
                    risk_col, cap_col,
                    pear_lv.loc[risk_col, cap_col], spear_lv.loc[risk_col, cap_col],
                    pear_df.loc[risk_col, cap_col], spear_df.loc[risk_col, cap_col],
                )


if __name__ == "__main__":
    main()
