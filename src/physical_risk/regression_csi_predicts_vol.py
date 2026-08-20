"""
Phase-4 first model: does the CSI predict next-month realized volatility?

    RV_{t+1} = alpha + beta * CSI_t + gamma * RV_t + eps_{t+1}

CSI_t enters as the continuous composite (not regime dummies — see
docs/methodology_notes/p_measures.md for why continuous is the first
cut). RV_t (the lagged dependent variable) is included from the start,
not added later, because both CSI and realized vol are strongly
persistent series (vol clustering; CSI's own secular trend) — omitting
RV_t risks attributing shared persistence to CSI's predictive power
rather than genuine forecast content. HAC (Newey-West) standard errors,
12 lags (one year of monthly data), for residual autocorrelation/
heteroskedasticity robustness.

Timing: CSI_t is the composite as of month-end t; RV_{t+1} is realized
volatility computed from daily returns strictly within calendar month
t+1 (src/physical_risk/build_index_returns.py) — a genuine predictive
(non-contemporaneous) regression, sidestepping simultaneity concerns.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import statsmodels.api as sm

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.utils.paths import CSI_FINAL, LOGS, PHYSICAL_RISK_FINAL, TABLES, latest_raw_file  # noqa: E402

logger = logging.getLogger(__name__)

HAC_LAGS = 12
RUN_TAG = datetime.now(timezone.utc).strftime("%Y%m%d")


def build_regression_frame() -> pd.DataFrame:
    csi_path = latest_raw_file(CSI_FINAL, "csi_composite_monthly")
    rv_path = latest_raw_file(PHYSICAL_RISK_FINAL, "realized_vol_monthly")

    csi = pd.read_csv(csi_path, parse_dates=["date"])[["date", "csi"]]
    rv = pd.read_csv(rv_path, parse_dates=["date"])[["date", "rv"]]

    df = rv.merge(csi, on="date", how="inner").sort_values("date").reset_index(drop=True)
    df["rv_lag1"] = df["rv"].shift(1)
    df["csi_lag1"] = df["csi"].shift(1)
    df["rv_lead1"] = df["rv"].shift(-1)

    # Regression frame: outcome = RV_{t+1} (rv_lead1), regressors = CSI_t (csi), RV_t (rv)
    reg = df[["date", "rv_lead1", "csi", "rv"]].rename(
        columns={"rv_lead1": "rv_next", "csi": "csi_t", "rv": "rv_t"}
    )
    return reg.dropna(subset=["rv_next", "csi_t", "rv_t"]).reset_index(drop=True)


def run_regression(reg: pd.DataFrame):
    X = sm.add_constant(reg[["csi_t", "rv_t"]])
    y = reg["rv_next"]
    model = sm.OLS(y, X).fit(cov_type="HAC", cov_kwds={"maxlags": HAC_LAGS})
    return model


def _configure_logging() -> Path:
    LOGS.mkdir(parents=True, exist_ok=True)
    log_path = LOGS / f"regression_csi_predicts_vol_{RUN_TAG}.txt"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(log_path), logging.StreamHandler()],
    )
    return log_path


def main() -> None:
    log_path = _configure_logging()
    logger.info("Logging to %s", log_path)

    reg = build_regression_frame()
    logger.info(
        "Regression sample: %d months, %s to %s (predicting RV in month t+1 from CSI_t, RV_t)",
        len(reg),
        reg["date"].min(),
        reg["date"].max(),
    )

    model = run_regression(reg)
    logger.info("\n%s", model.summary())

    out_table = TABLES / f"p_measure_csi_predicts_vol_{RUN_TAG}.csv"
    TABLES.mkdir(parents=True, exist_ok=True)
    coef_table = pd.DataFrame(
        {
            "coef": model.params,
            "hac_se": model.bse,
            "t_stat": model.tvalues,
            "p_value": model.pvalues,
        }
    )
    coef_table.to_csv(out_table)
    logger.info("Wrote %s", out_table)
    logger.info("R-squared: %.4f, N: %d, HAC lags: %d", model.rsquared, int(model.nobs), HAC_LAGS)


if __name__ == "__main__":
    main()
