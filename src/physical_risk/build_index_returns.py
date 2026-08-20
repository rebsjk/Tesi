"""
Phase-4 step 0: builds the P-measure's dependent variable — daily index
returns and monthly realized volatility — from the Phase-1 constituent
panel (`data_final/universe/`), self-weighted.

Deliberately does NOT use a vendor index-return file (e.g. CRSP's
`vwretd`). The index return here is built from the exact same
self-computed weights (`weight = dlycap_i,t / sum(dlycap over active
members)`, see docs/methodology_notes/index_weight_construction.md) that
the CSI's capital-concentration measures are computed from — so "the
index whose concentration we measure" and "the index whose realized risk
we predict" are methodologically the same object, not two different
vendor definitions that happen to both be called "the S&P 500."

r_idx,d = sum_i weight_i,d * ret_i,d   (same-day weight, same-day return
— no look-ahead: this describes day d's index return using day d's own
composition, not a forecast)

RV_t = sqrt(sum_{d in month t} r_idx,d^2)   (realized volatility, monthly,
un-annualized — daily-squared-return summation, standard given only
daily-frequency data; annualizing is a display-time transform, not baked
into the stored series)

CRSP daily returns physically never touch options data — this script only
reads data_final/universe/, consistent with the P/Q separation rule in
CLAUDE.md.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.utils.paths import LOGS, PHYSICAL_RISK_FINAL, UNIVERSE_FINAL, latest_raw_file  # noqa: E402

logger = logging.getLogger(__name__)

RUN_TAG = datetime.now(timezone.utc).strftime("%Y%m%d")


def build_daily_index_returns(panel: pd.DataFrame) -> pd.DataFrame:
    panel = panel.dropna(subset=["weight", "ret"])
    daily = (
        panel.assign(contrib=panel["weight"] * panel["ret"])
        .groupby("date")["contrib"]
        .sum()
        .rename("r_idx")
        .reset_index()
    )
    return daily


def build_monthly_realized_vol(daily: pd.DataFrame) -> pd.DataFrame:
    daily = daily.copy()
    daily["month"] = daily["date"].dt.to_period("M")
    monthly = daily.groupby("month").agg(
        date=("date", "max"),  # month-end trading date, matches concentration/CSI convention
        rv=("r_idx", lambda x: float(np.sqrt(np.sum(x**2)))),
        r_idx_monthly=("r_idx", lambda x: float(np.prod(1 + x) - 1)),
        n_days=("r_idx", "size"),
    )
    return monthly.reset_index(drop=True)[["date", "rv", "r_idx_monthly", "n_days"]]


def _configure_logging() -> Path:
    LOGS.mkdir(parents=True, exist_ok=True)
    log_path = LOGS / f"build_index_returns_{RUN_TAG}.txt"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(log_path), logging.StreamHandler()],
    )
    return log_path


def main() -> None:
    log_path = _configure_logging()
    logger.info("Logging to %s", log_path)

    panel_path = latest_raw_file(UNIVERSE_FINAL, "universe_constituent_panel")
    logger.info("Loading constituent panel: %s", panel_path)
    panel = pd.read_parquet(panel_path)

    daily = build_daily_index_returns(panel)
    logger.info(
        "Built %d daily index-return observations, %s to %s",
        len(daily),
        daily["date"].min(),
        daily["date"].max(),
    )
    logger.info(
        "Daily r_idx summary: mean=%.5f, std=%.5f, min=%.4f (%s), max=%.4f (%s)",
        daily["r_idx"].mean(),
        daily["r_idx"].std(),
        daily["r_idx"].min(),
        daily.loc[daily["r_idx"].idxmin(), "date"],
        daily["r_idx"].max(),
        daily.loc[daily["r_idx"].idxmax(), "date"],
    )

    monthly = build_monthly_realized_vol(daily)
    logger.info(
        "Built %d monthly realized-vol observations, %s to %s. n_days per month: min=%d, max=%d",
        len(monthly),
        monthly["date"].min(),
        monthly["date"].max(),
        monthly["n_days"].min(),
        monthly["n_days"].max(),
    )

    PHYSICAL_RISK_FINAL.mkdir(parents=True, exist_ok=True)
    daily_out = PHYSICAL_RISK_FINAL / f"index_returns_daily_{RUN_TAG}.csv"
    monthly_out = PHYSICAL_RISK_FINAL / f"realized_vol_monthly_{RUN_TAG}.csv"
    daily.to_csv(daily_out, index=False)
    monthly.to_csv(monthly_out, index=False)
    logger.info("Wrote %s", daily_out)
    logger.info("Wrote %s", monthly_out)


if __name__ == "__main__":
    main()
