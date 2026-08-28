"""
Phase-2 (risk-concentration dimension) orchestration: builds the monthly
risk-concentration panel from the Phase-1 constituent panel
(`data_final/universe/`), reusing:

- the frozen top-k/top-N subset selection convention (anchor at each
  calendar month's first available trading date, held fixed for the
  month) from `docs/methodology_notes/csi_construction.md`, applied here
  to BOTH the top-100 covariance-estimation subset and the top-5/7/10
  capital-weight cohorts used for `risk_share_topk`'s comparability with
  `cr_5`/`cr_7`/`cr_10`;
- `src/concentration/covariance_estimation.py` for Sigma_t (top-100
  subset, 252-trading-day trailing window, Ledoit-Wolf constant-
  correlation shrinkage);
- `src/concentration/risk_measures.py` for the risk-share/N_eff_risk/
  risk_entropy calculations on top of Sigma_t.

Burn-in: a month is only included once a FULL 252-trading-day window is
available (checked via `n_window_dates == WINDOW_TRADING_DAYS`), excluded
rather than computed on a partial window - consistent with how build_csi.py
and classify_regime.py treat their own burn-in periods.

risk_share_topk uses the top-k-BY-WEIGHT cohort selected at the SAME
month-start anchor date used for `cr_5`/`cr_7`/`cr_10` in
build_concentration_panel.py, so the two series are comparable against the
identical named cohort - not two independently-selected top-k lists.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.concentration.covariance_estimation import (  # noqa: E402
    N_SUBSET,
    WINDOW_TRADING_DAYS,
    estimate_sigma_t,
)
from src.concentration.risk_measures import (  # noqa: E402
    effective_n_risk,
    risk_contributions,
    risk_entropy,
)
from src.utils.paths import CONCENTRATION_FINAL, LOGS, UNIVERSE_FINAL, latest_raw_file  # noqa: E402

logger = logging.getLogger(__name__)

TOPK_VALUES = (5, 7, 10)
RUN_TAG = datetime.now(timezone.utc).strftime("%Y%m%d")


def build_monthly_risk_concentration_panel(
    panel: pd.DataFrame,
    topk_values: tuple[int, ...] = TOPK_VALUES,
    n_subset: int = N_SUBSET,
    window_days: int = WINDOW_TRADING_DAYS,
) -> tuple[pd.DataFrame, dict]:
    """Return (monthly risk-concentration panel, diagnostics dict).

    Diagnostics dict carries the cross-month logging detail (skipped
    burn-in months, topk cohort attrition, negative-risk-contribution
    events) so `main()` can log them without recomputing anything.
    """
    panel = panel.dropna(subset=["weight", "ret"]).copy()
    panel["month"] = panel["date"].dt.to_period("M")

    month_start_date = panel.groupby("month")["date"].min()
    month_end_date = panel.groupby("month")["date"].max()

    records = []
    skipped_burn_in = []
    topk_attrition = []
    negative_contribution_events = []

    for month in month_start_date.index:
        start_date = month_start_date[month]
        end_date = month_end_date[month]

        start_weights = panel.loc[panel["date"] == start_date].set_index("permno")["weight"]
        topk_cohorts = {k: set(start_weights.nlargest(k).index) for k in topk_values}

        result = estimate_sigma_t(
            panel, subset_anchor_date=start_date, window_end_date=end_date,
            n=n_subset, window_days=window_days,
        )

        if result.n_window_dates < window_days:
            skipped_burn_in.append(str(month))
            continue

        weights_arr = result.weights.to_numpy()
        sigma_arr = result.sigma.to_numpy()
        p = risk_contributions(weights_arr, sigma_arr)

        row = {
            "date": end_date,
            "n_subset_nominal": n_subset,
            "n_subset_included": len(result.included),
            "n_excluded_insufficient_history": len(result.excluded_insufficient_history),
            "shrinkage_intensity": result.shrinkage_intensity,
            "n_eff_risk": float(1.0 / np.sum(p**2)),
            "risk_entropy": risk_entropy(weights_arr, sigma_arr),
            "n_negative_contributions": int((p < 0).sum()),
        }

        for k in topk_values:
            cohort = topk_cohorts[k]
            missing = cohort - set(result.included)
            if missing:
                topk_attrition.append((str(month), k, sorted(missing)))
            mask = np.array([permno in cohort for permno in result.included])
            row[f"risk_share_top{k}"] = float(p[mask].sum())

        if row["n_negative_contributions"] > 0:
            neg_names = [
                permno for permno, p_i in zip(result.included, p) if p_i < 0
            ]
            negative_contribution_events.append((str(month), neg_names))

        records.append(row)

    result_df = (
        pd.DataFrame.from_records(records).sort_values("date").reset_index(drop=True)
        if records
        else pd.DataFrame()
    )
    diagnostics = {
        "skipped_burn_in": skipped_burn_in,
        "topk_attrition": topk_attrition,
        "negative_contribution_events": negative_contribution_events,
    }
    return result_df, diagnostics


def _configure_logging() -> Path:
    LOGS.mkdir(parents=True, exist_ok=True)
    log_path = LOGS / f"build_risk_concentration_panel_{RUN_TAG}.txt"
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
        "Risk-concentration construction parameters: n_subset=%d, "
        "window_days=%d (rolling, trailing, month-end), shrinkage=Ledoit-Wolf "
        "constant-correlation target, topk_values=%s",
        N_SUBSET, WINDOW_TRADING_DAYS, TOPK_VALUES,
    )

    panel_path = latest_raw_file(UNIVERSE_FINAL, "universe_constituent_panel")
    logger.info("Loading constituent panel: %s", panel_path)
    panel = pd.read_parquet(panel_path)

    result, diagnostics = build_monthly_risk_concentration_panel(panel)

    logger.info(
        "Built %d monthly risk-concentration observations, %s to %s "
        "(%d months excluded by 252-trading-day burn-in)",
        len(result),
        result["date"].min() if len(result) else None,
        result["date"].max() if len(result) else None,
        len(diagnostics["skipped_burn_in"]),
    )
    logger.info(
        "n_subset_included range: %d to %d (median %.0f) out of nominal %d",
        result["n_subset_included"].min(),
        result["n_subset_included"].max(),
        result["n_subset_included"].median(),
        N_SUBSET,
    )
    logger.info(
        "shrinkage_intensity range: %.4f to %.4f (median %.4f)",
        result["shrinkage_intensity"].min(),
        result["shrinkage_intensity"].max(),
        result["shrinkage_intensity"].median(),
    )

    if diagnostics["topk_attrition"]:
        logger.info(
            "%d topk-cohort-attrition events (a top-k-by-weight member was "
            "excluded from Sigma_t for insufficient history that month): %s",
            len(diagnostics["topk_attrition"]),
            diagnostics["topk_attrition"],
        )
    else:
        logger.info("No topk-cohort-attrition events.")

    n_months_with_negatives = len(diagnostics["negative_contribution_events"])
    total_negative_obs = int(result["n_negative_contributions"].sum())
    logger.info(
        "Negative risk-contribution diagnostic: %d of %d months have at least one "
        "negative p_i,t (%d total negative-contribution name-months). "
        "See docs/variable_definitions/risk_concentration.md for the clipping "
        "convention this feeds into risk_entropy.",
        n_months_with_negatives,
        len(result),
        total_negative_obs,
    )

    CONCENTRATION_FINAL.mkdir(parents=True, exist_ok=True)
    out_path = CONCENTRATION_FINAL / f"risk_concentration_measures_monthly_{RUN_TAG}.csv"
    result.to_csv(out_path, index=False)
    logger.info("Wrote %s", out_path)


if __name__ == "__main__":
    main()
