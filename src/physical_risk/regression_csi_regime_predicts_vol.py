"""
Phase-4 second model: does the CSI *regime* (not the continuous
composite) predict next-month realized volatility?

    RV_{t+1} = alpha + beta_med * 1{regime_t=medium} + beta_high * 1{regime_t=high}
               + gamma * RV_t + eps_{t+1}

`low` is the omitted/reference category, so `beta_med`/`beta_high` are
read relative to the low-concentration regime. Same dependent variable,
sample window, AR(1) control, and HAC (12 lags) as the continuous model
in regression_csi_predicts_vol.py — the only change is how CSI enters,
so this is a clean test of whether a threshold/nonlinear specification
tells a different story than the linear-continuous null result.

Regime labels come from data_final/csi/csi_regime_monthly_<date>.csv
(rolling 60-month tercile classification — see
docs/methodology_notes/csi_construction.md, "State/regime classification").
Months with no defined regime (the classification's own 59-month burn-in,
on top of the CSI composite's 24-month burn-in) are dropped from this
regression's sample, same as any other missing regressor.
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
    regime_path = latest_raw_file(CSI_FINAL, "csi_regime_monthly")
    rv_path = latest_raw_file(PHYSICAL_RISK_FINAL, "realized_vol_monthly")

    regime = pd.read_csv(regime_path, parse_dates=["date"])[["date", "regime"]]
    rv = pd.read_csv(rv_path, parse_dates=["date"])[["date", "rv"]]

    df = rv.merge(regime, on="date", how="inner").sort_values("date").reset_index(drop=True)
    df["rv_lead1"] = df["rv"].shift(-1)

    reg = df[["date", "rv_lead1", "regime", "rv"]].rename(
        columns={"rv_lead1": "rv_next", "rv": "rv_t"}
    )
    reg = reg.dropna(subset=["rv_next", "regime", "rv_t"]).reset_index(drop=True)

    reg["regime_medium"] = (reg["regime"] == "medium").astype(int)
    reg["regime_high"] = (reg["regime"] == "high").astype(int)
    return reg


def run_regression(reg: pd.DataFrame):
    X = sm.add_constant(reg[["regime_medium", "regime_high", "rv_t"]])
    y = reg["rv_next"]
    model = sm.OLS(y, X).fit(cov_type="HAC", cov_kwds={"maxlags": HAC_LAGS})
    return model


def _configure_logging() -> Path:
    LOGS.mkdir(parents=True, exist_ok=True)
    log_path = LOGS / f"regression_csi_regime_predicts_vol_{RUN_TAG}.txt"
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
        "Regression sample: %d months, %s to %s (predicting RV in month t+1 from "
        "regime dummies at t, RV_t)",
        len(reg),
        reg["date"].min(),
        reg["date"].max(),
    )
    logger.info("Regime distribution in sample: %s", reg["regime"].value_counts().to_dict())

    model = run_regression(reg)
    logger.info("\n%s", model.summary())

    out_table = TABLES / f"p_measure_csi_regime_predicts_vol_{RUN_TAG}.csv"
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
