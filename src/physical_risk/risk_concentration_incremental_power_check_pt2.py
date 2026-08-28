"""
Part 2 of the 2026-08-27 exploratory diagnostic (see
`risk_concentration_incremental_power_check.py` for part 1, the continuous-
CSI version). Two follow-ups requested after reviewing part 1:

FAMILY 4 - regime-dummy model + risk concentration. The continuous-CSI
model in part 1 was already null for capital concentration itself
(csi_t p=0.678), so a null incremental result there is uninformative about
whether risk concentration matters where it's most plausible to matter -
the regime-dummy specification, the only Phase-4 model that showed even a
marginal capital-CSI signal (p=0.06). Reruns the same
capital-baseline-vs-capital+risk logic from part 1, but with
`regression_csi_regime_predicts_vol.py`'s regime dummies (`regime_medium`,
`regime_high`) as the capital side instead of continuous `csi_t`.

Design choice, stated explicitly per the review request: risk-concentration
candidates enter as CONTINUOUS regressors alongside the existing regime
dummies, not as a newly-built "risk concentration regime" (its own
rolling-tercile classification). Building a parallel regime classification
would mean standing up a second instance of `classify_regime.py`'s whole
point-in-time machinery (60-month rolling window, burn-in, hysteresis
check) - a real production step, not a same-session diagnostic, and would
front-run the Fase-3 integration decision this check is meant to inform
rather than answer it. A continuous risk regressor next to the existing
regime dummies answers the actual question ("does risk concentration add
anything on top of the capital regime classification") without building
new pipeline machinery.

ROBUSTNESS CHECKS on the one marginal part-1 result (csi_t + n_eff_risk_
flipped, p=0.048 on n_eff_risk_flipped):
- COVID exclusion (drop 2020-02 through 2020-06)
- HAC lag sensitivity (6, 12, 18 lags)
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import statsmodels.api as sm

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.physical_risk.risk_concentration_incremental_power_check import (  # noqa: E402
    HAC_LAGS, RISK_COLS, build_frame, fit,
)
from src.utils.paths import CSI_FINAL, LOGS, TABLES, latest_raw_file  # noqa: E402

logger = logging.getLogger(__name__)
RUN_TAG = datetime.now(timezone.utc).strftime("%Y%m%d")
COVID_EXCLUDE = ("2020-02-01", "2020-06-30")


def build_regime_frame() -> pd.DataFrame:
    df = build_frame()  # date, rv_next, csi_t, rv_t, RISK_COLS..., risk_zavg
    regime = pd.read_csv(latest_raw_file(CSI_FINAL, "csi_regime_monthly"), parse_dates=["date"])[["date", "regime"]]
    df = df.merge(regime, on="date", how="inner").dropna(subset=["regime"]).reset_index(drop=True)
    df["regime_medium"] = (df["regime"] == "medium").astype(int)
    df["regime_high"] = (df["regime"] == "high").astype(int)
    return df


def _configure_logging(tag: str) -> Path:
    LOGS.mkdir(parents=True, exist_ok=True)
    log_path = LOGS / f"risk_concentration_incremental_power_check_pt2_{tag}_{RUN_TAG}.txt"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(log_path), logging.StreamHandler()],
    )
    return log_path


def run_regime_family() -> None:
    log_path = _configure_logging("regime_family")
    logger.info("Logging to %s", log_path)

    df = build_regime_frame()
    logger.info(
        "Merged regression sample: %d months, %s to %s (regime-dummy family)",
        len(df), df["date"].min(), df["date"].max(),
    )
    logger.info("Regime distribution: %s", df["regime"].value_counts().to_dict())

    rows = []

    def log_model(label: str, regressors: list[str]) -> None:
        model, n = fit(df, regressors)
        logger.info("-" * 70)
        logger.info("[%s] regressors=%s, N=%d, R2=%.4f", label, regressors, n, model.rsquared)
        for name in regressors:
            logger.info("  %s: coef=%.5f  p=%.4f", name, model.params[name], model.pvalues[name])
        rows.append({
            "model": label, "n": n, "r2": model.rsquared,
            **{f"coef_{name}": model.params[name] for name in regressors},
            **{f"p_{name}": model.pvalues[name] for name in regressors},
        })

    logger.info("=" * 70)
    logger.info("FAMILY 4a - baseline (regime dummies only, reproduces Phase-4 regime result)")
    log_model("baseline_regime_only", ["regime_medium", "regime_high", "rv_t"])

    logger.info("=" * 70)
    logger.info("FAMILY 4b - regime dummies + risk concentration (continuous)")
    for col in RISK_COLS:
        log_model(f"regime_plus_{col}", ["regime_medium", "regime_high", col, "rv_t"])
    log_model("regime_plus_risk_zavg", ["regime_medium", "regime_high", "risk_zavg", "rv_t"])

    out_table = TABLES / f"p_measure_risk_concentration_incremental_power_regime_{RUN_TAG}.csv"
    TABLES.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(out_table, index=False)
    logger.info("=" * 70)
    logger.info("Wrote %s", out_table)


def run_robustness_checks() -> None:
    log_path = _configure_logging("robustness")
    logger.info("Logging to %s", log_path)

    df = build_frame()
    regressors = ["csi_t", "n_eff_risk_flipped", "rv_t"]
    covid_mask = (df["date"] >= COVID_EXCLUDE[0]) & (df["date"] <= COVID_EXCLUDE[1])
    df_excov = df.loc[~covid_mask].reset_index(drop=True)

    logger.info("=" * 70)
    logger.info("CHECK 1 - COVID exclusion (drop %s to %s), risk-concentration coefficient", *COVID_EXCLUDE)
    full_model, n_full = fit(df, regressors)
    logger.info("[full sample] N=%d, R2=%.4f, n_eff_risk_flipped p=%.4f, coef=%.5f",
                n_full, full_model.rsquared, full_model.pvalues["n_eff_risk_flipped"],
                full_model.params["n_eff_risk_flipped"])
    logger.info("Excluding %d months: %s", covid_mask.sum(), df.loc[covid_mask, "date"].dt.strftime("%Y-%m").tolist())
    excov_model, n_excov = fit(df_excov, regressors)
    logger.info("[COVID-excluded] N=%d, R2=%.4f, n_eff_risk_flipped p=%.4f, coef=%.5f",
                n_excov, excov_model.rsquared, excov_model.pvalues["n_eff_risk_flipped"],
                excov_model.params["n_eff_risk_flipped"])

    logger.info("=" * 70)
    logger.info("CHECK 1b - SCOPE BEYOND TODAY'S RISK-CONCENTRATION TEST: does the existing")
    logger.info("Phase-4 capital-only result itself depend on the same 5 COVID months?")
    logger.info("-" * 70)
    logger.info("[continuous CSI model, capital-only baseline]")
    base_cont_full, n1 = fit(df, ["csi_t", "rv_t"])
    logger.info("  [full sample]     N=%d, R2=%.4f, csi_t coef=%.5f p=%.4f",
                n1, base_cont_full.rsquared, base_cont_full.params["csi_t"], base_cont_full.pvalues["csi_t"])
    base_cont_excov, n2 = fit(df_excov, ["csi_t", "rv_t"])
    logger.info("  [COVID-excluded]  N=%d, R2=%.4f, csi_t coef=%.5f p=%.4f",
                n2, base_cont_excov.rsquared, base_cont_excov.params["csi_t"], base_cont_excov.pvalues["csi_t"])

    logger.info("[regime-dummy model, capital-only baseline]")
    df_regime = build_regime_frame()
    covid_mask_r = (df_regime["date"] >= COVID_EXCLUDE[0]) & (df_regime["date"] <= COVID_EXCLUDE[1])
    logger.info("  COVID months present in regime sample: %d", covid_mask_r.sum())
    df_regime_excov = df_regime.loc[~covid_mask_r].reset_index(drop=True)
    base_reg_full, n3 = fit(df_regime, ["regime_medium", "regime_high", "rv_t"])
    logger.info("  [full sample]     N=%d, R2=%.4f, regime_high coef=%.5f p=%.4f, regime_medium coef=%.5f p=%.4f",
                n3, base_reg_full.rsquared,
                base_reg_full.params["regime_high"], base_reg_full.pvalues["regime_high"],
                base_reg_full.params["regime_medium"], base_reg_full.pvalues["regime_medium"])
    base_reg_excov, n4 = fit(df_regime_excov, ["regime_medium", "regime_high", "rv_t"])
    logger.info("  [COVID-excluded]  N=%d, R2=%.4f, regime_high coef=%.5f p=%.4f, regime_medium coef=%.5f p=%.4f",
                n4, base_reg_excov.rsquared,
                base_reg_excov.params["regime_high"], base_reg_excov.pvalues["regime_high"],
                base_reg_excov.params["regime_medium"], base_reg_excov.pvalues["regime_medium"])

    logger.info("=" * 70)
    logger.info("CHECK 2 - HAC lag sensitivity (6, 12, 18 lags), full sample vs. COVID-excluded")
    for label, frame in [("full sample", df), ("COVID-excluded", df_excov)]:
        for lags in (6, 12, 18):
            sub = frame.dropna(subset=["rv_next"] + regressors)
            X = sm.add_constant(sub[regressors])
            y = sub["rv_next"]
            m = sm.OLS(y, X).fit(cov_type="HAC", cov_kwds={"maxlags": lags})
            logger.info("  [%s] HAC lags=%2d: n_eff_risk_flipped p=%.4f, coef=%.5f, csi_t p=%.4f",
                        label, lags, m.pvalues["n_eff_risk_flipped"], m.params["n_eff_risk_flipped"],
                        m.pvalues["csi_t"])


if __name__ == "__main__":
    run_regime_family()
    run_robustness_checks()
