"""
Exploratory diagnostic (NOT a Phase-4 model, not point-in-time-safe) for the
2026-08-27 CSI composite-integration discussion: does risk concentration add
incremental predictive power for next-month realized volatility, on top of
what the existing capital-only CSI already gets in
`regression_csi_predicts_vol.py`?

    RV_{t+1} = alpha + beta_csi * CSI_t [+ beta_risk * risk_measure_t]
               + gamma * RV_t + eps_{t+1}

Same dependent variable, same RV_t AR(1) control, same HAC(12) standard
errors, same non-contemporaneous timing convention as the existing Phase-4
continuous-CSI model — chosen over the regime-dummy model because it is
the simpler of the two (no 59-month regime-classification burn-in to lose)
and is the specification this diagnostic is checked against.

Runs three families of models:
1. Baseline (capital CSI only) — reproduces the existing Phase-4 result for
   reference.
2. Capital + risk: CSI_t plus each risk-concentration candidate individually,
   and CSI_t plus an equal-weight z-score composite of all five.
3. Risk only (no CSI_t): the same risk regressors alone, to isolate whether
   any signal found in (2) comes from risk concentration itself or only in
   combination with capital concentration.

Caveat, stated once here rather than repeated at every model: the z-score
composite in (2)/(3) is standardized on full-sample mean/std, not a
trailing/expanding window — acceptable for a same-session exploratory check,
NOT acceptable for a point-in-time-valid Phase-4/6 result if this ever
becomes one.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import statsmodels.api as sm

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.utils.paths import (  # noqa: E402
    CONCENTRATION_FINAL, CSI_FINAL, LOGS, PHYSICAL_RISK_FINAL, TABLES, latest_raw_file,
)

logger = logging.getLogger(__name__)

HAC_LAGS = 12
RUN_TAG = datetime.now(timezone.utc).strftime("%Y%m%d")
RISK_COLS = ["risk_share_top5", "risk_share_top7", "risk_share_top10", "n_eff_risk_flipped", "risk_entropy"]


def build_frame() -> pd.DataFrame:
    csi = pd.read_csv(latest_raw_file(CSI_FINAL, "csi_composite_monthly"), parse_dates=["date"])[["date", "csi"]]
    rv = pd.read_csv(latest_raw_file(PHYSICAL_RISK_FINAL, "realized_vol_monthly"), parse_dates=["date"])[["date", "rv"]]
    risk = pd.read_csv(latest_raw_file(CONCENTRATION_FINAL, "risk_concentration_measures_monthly"), parse_dates=["date"])
    risk["n_eff_risk_flipped"] = -risk["n_eff_risk"]
    risk = risk[["date"] + RISK_COLS]

    df = (
        rv.merge(csi, on="date", how="inner")
        .merge(risk, on="date", how="inner")
        .sort_values("date")
        .reset_index(drop=True)
    )
    df["rv_next"] = df["rv"].shift(-1)
    df = df.rename(columns={"rv": "rv_t", "csi": "csi_t"})

    z = (df[RISK_COLS] - df[RISK_COLS].mean()) / df[RISK_COLS].std()
    df["risk_zavg"] = z.mean(axis=1)

    return df.dropna(subset=["rv_next", "csi_t", "rv_t"]).reset_index(drop=True)


def fit(df: pd.DataFrame, regressors: list[str]) -> sm.regression.linear_model.RegressionResultsWrapper:
    cols = ["rv_next"] + regressors
    sub = df.dropna(subset=cols)
    X = sm.add_constant(sub[regressors])
    y = sub["rv_next"]
    return sm.OLS(y, X).fit(cov_type="HAC", cov_kwds={"maxlags": HAC_LAGS}), len(sub)


def _configure_logging() -> Path:
    LOGS.mkdir(parents=True, exist_ok=True)
    log_path = LOGS / f"risk_concentration_incremental_power_check_{RUN_TAG}.txt"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(log_path), logging.StreamHandler()],
    )
    return log_path


def main() -> None:
    log_path = _configure_logging()
    logger.info("Logging to %s", log_path)

    df = build_frame()
    logger.info("Merged regression sample: %d months, %s to %s", len(df), df["date"].min(), df["date"].max())

    rows = []

    def log_model(label: str, regressors: list[str]) -> None:
        model, n = fit(df, regressors)
        logger.info("-" * 70)
        logger.info("[%s] regressors=%s, N=%d, R2=%.4f", label, regressors, n, model.rsquared)
        for name in regressors:
            logger.info("  %s: coef=%.5f  p=%.4f", name, model.params[name], model.pvalues[name])
        rows.append({
            "model": label,
            "regressors": ",".join(regressors),
            "n": n,
            "r2": model.rsquared,
            **{f"coef_{name}": model.params[name] for name in regressors},
            **{f"p_{name}": model.pvalues[name] for name in regressors},
        })

    logger.info("=" * 70)
    logger.info("FAMILY 1 - baseline (capital CSI only, reproduces Phase-4 result)")
    log_model("baseline_csi_only", ["csi_t", "rv_t"])

    logger.info("=" * 70)
    logger.info("FAMILY 2 - capital + risk concentration")
    for col in RISK_COLS:
        log_model(f"csi_plus_{col}", ["csi_t", col, "rv_t"])
    log_model("csi_plus_risk_zavg", ["csi_t", "risk_zavg", "rv_t"])

    logger.info("=" * 70)
    logger.info("FAMILY 3 - risk concentration only (no CSI_t)")
    for col in RISK_COLS:
        log_model(f"risk_only_{col}", [col, "rv_t"])
    log_model("risk_only_zavg", ["risk_zavg", "rv_t"])

    out_table = TABLES / f"p_measure_risk_concentration_incremental_power_{RUN_TAG}.csv"
    TABLES.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(out_table, index=False)
    logger.info("=" * 70)
    logger.info("Wrote %s", out_table)


if __name__ == "__main__":
    main()
