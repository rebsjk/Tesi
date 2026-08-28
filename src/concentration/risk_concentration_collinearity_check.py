"""
Risk-concentration collinearity check, mirroring the mandatory Phase-3
check in `src/concentration/collinearity_check.py`, in two stages:

1. **Internal** - among the risk-concentration candidates themselves
   (`risk_share_top5/7/10`, `n_eff_risk`, `risk_entropy`), the same
   "one representative per empirically-distinct cluster" discipline
   already applied to hhi/cr_k/effective_n/entropy_concentration in Phase
   2. Not requested explicitly in the original brief, but the same logic
   applies: before comparing risk concentration to capital concentration,
   we should know whether the risk-concentration candidate set itself is
   internally redundant.
2. **Cross-dimension** (the check the thesis needs) - risk-concentration
   candidates vs. `hhi`, `cr_10`, `entropy_concentration`, and the CSI
   composite itself. Answers: does risk concentration add information
   distinct from capital concentration, or is it mostly a transformation
   of it?

Same conventions as collinearity_check.py: Pearson AND Spearman, on BOTH
levels and first differences (month-over-month), threshold |r| > 0.90,
`effective_n`/`n_eff_risk` sign-flipped so all series agree on direction
before comparison.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.utils.paths import CONCENTRATION_FINAL, CSI_FINAL, FIGURES, LOGS, TABLES, latest_raw_file  # noqa: E402

logger = logging.getLogger(__name__)

RISK_SERIES_COLS = [
    "risk_share_top5", "risk_share_top7", "risk_share_top10",
    "n_eff_risk_flipped", "risk_entropy",
]
CAPITAL_SERIES_COLS = ["hhi", "cr_10", "entropy_concentration", "csi"]
THRESHOLD = 0.90
RUN_TAG = datetime.now(timezone.utc).strftime("%Y%m%d")


def load_merged_series() -> pd.DataFrame:
    risk_path = latest_raw_file(CONCENTRATION_FINAL, "risk_concentration_measures_monthly")
    capital_path = latest_raw_file(CONCENTRATION_FINAL, "concentration_measures_monthly")
    csi_path = latest_raw_file(CSI_FINAL, "csi_composite_monthly")

    risk = pd.read_csv(risk_path, parse_dates=["date"])
    risk["n_eff_risk_flipped"] = -risk["n_eff_risk"]

    capital = pd.read_csv(capital_path, parse_dates=["date"])[["date", "hhi", "cr_10", "entropy_concentration"]]
    csi = pd.read_csv(csi_path, parse_dates=["date"])[["date", "csi"]]

    merged = (
        risk[["date"] + RISK_SERIES_COLS]
        .merge(capital, on="date", how="inner")
        .merge(csi, on="date", how="inner")
    )
    return merged.set_index("date")


def _corr_matrices(df: pd.DataFrame, cols: list[str]) -> dict[str, pd.DataFrame]:
    series = df[cols]
    diffs = series.diff().dropna(how="all")
    return {
        "pearson_levels": series.corr(method="pearson"),
        "spearman_levels": series.corr(method="spearman"),
        "pearson_diff": diffs.corr(method="pearson"),
        "spearman_diff": diffs.corr(method="spearman"),
    }


def flag_pairs(corr: pd.DataFrame, cols: list[str], method: str, basis: str) -> list[dict]:
    flags = []
    for a, b in combinations(cols, 2):
        r = corr.loc[a, b]
        if abs(r) > THRESHOLD:
            flags.append({"pair": f"{a} / {b}", "method": method, "basis": basis, "r": r})
    return flags


def plot_heatmaps(matrices: dict[str, pd.DataFrame], title: str, out_path: Path) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(13, 11))
    layout = [
        (axes[0, 0], matrices["pearson_levels"], "Pearson — levels"),
        (axes[0, 1], matrices["spearman_levels"], "Spearman — levels"),
        (axes[1, 0], matrices["pearson_diff"], "Pearson — 1st differences (MoM)"),
        (axes[1, 1], matrices["spearman_diff"], "Spearman — 1st differences (MoM)"),
    ]
    for ax, corr, subtitle in layout:
        sns.heatmap(
            corr, ax=ax, annot=True, fmt=".2f", cmap="RdBu_r", vmin=-1, vmax=1,
            square=True, cbar_kws={"shrink": 0.8},
        )
        ax.set_title(subtitle)
    fig.suptitle(title, fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(out_path, dpi=150)


def _configure_logging() -> Path:
    LOGS.mkdir(parents=True, exist_ok=True)
    log_path = LOGS / f"risk_concentration_collinearity_check_{RUN_TAG}.txt"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(log_path), logging.StreamHandler()],
    )
    return log_path


def _log_and_save(matrices: dict, cols: list[str], label: str) -> None:
    TABLES.mkdir(parents=True, exist_ok=True)
    for name, corr in matrices.items():
        path = TABLES / f"risk_concentration_{label}_correlation_{name}_{RUN_TAG}.csv"
        corr.to_csv(path)
        logger.info("Wrote %s", path)

    FIGURES.mkdir(parents=True, exist_ok=True)
    fig_path = FIGURES / f"risk_concentration_{label}_collinearity_{RUN_TAG}.png"
    plot_heatmaps(
        matrices,
        f"Risk concentration — {label} collinearity check ({RUN_TAG})",
        fig_path,
    )
    logger.info("Wrote %s", fig_path)

    all_flags = []
    for basis_key, corr in matrices.items():
        method, basis = basis_key.split("_")
        all_flags += flag_pairs(corr, cols, method, basis)

    logger.info("=" * 70)
    logger.info("[%s] Threshold: |r| > %.2f (Pearson OR Spearman), levels AND 1st differences", label, THRESHOLD)
    if all_flags:
        for f in all_flags:
            logger.info("  [%s] %s: %s r=%.4f", f["basis"], f["pair"], f["method"], f["r"])
    else:
        logger.info("  none — no pair exceeds the threshold on either basis.")


def main() -> None:
    log_path = _configure_logging()
    logger.info("Logging to %s", log_path)

    df = load_merged_series()
    logger.info("Merged %d monthly observations, %s to %s", len(df), df.index.min(), df.index.max())

    internal_matrices = _corr_matrices(df, RISK_SERIES_COLS)
    _log_and_save(internal_matrices, RISK_SERIES_COLS, "internal")

    cross_cols = RISK_SERIES_COLS + CAPITAL_SERIES_COLS
    cross_matrices = _corr_matrices(df, cross_cols)
    # Only report cross-dimension pairs (risk vs capital), not the
    # already-reported internal risk/risk or the already-known capital/
    # capital pairs from collinearity_check.py - avoids double-counting.
    cross_only_flags = {}
    for basis_key, corr in cross_matrices.items():
        method, basis = basis_key.split("_")
        flags = [
            f for f in flag_pairs(corr, cross_cols, method, basis)
            if any(c in f["pair"] for c in RISK_SERIES_COLS)
            and any(c in f["pair"] for c in CAPITAL_SERIES_COLS)
        ]
        cross_only_flags[basis_key] = flags

    TABLES.mkdir(parents=True, exist_ok=True)
    for name, corr in cross_matrices.items():
        path = TABLES / f"risk_concentration_cross_dimension_correlation_{name}_{RUN_TAG}.csv"
        corr.to_csv(path)
        logger.info("Wrote %s", path)

    FIGURES.mkdir(parents=True, exist_ok=True)
    fig_path = FIGURES / f"risk_concentration_cross_dimension_collinearity_{RUN_TAG}.png"
    plot_heatmaps(
        cross_matrices,
        f"Risk concentration vs. capital concentration/CSI — cross-dimension collinearity ({RUN_TAG})",
        fig_path,
    )
    logger.info("Wrote %s", fig_path)

    logger.info("=" * 70)
    logger.info("Cross-dimension flags (risk-concentration candidate vs. capital-concentration/CSI series):")
    any_flag = False
    for basis_key, flags in cross_only_flags.items():
        for f in flags:
            any_flag = True
            logger.info("  [%s] %s: %s r=%.4f", f["basis"], f["pair"], f["method"], f["r"])
    if not any_flag:
        logger.info("  none — no risk-concentration/capital-concentration pair exceeds the threshold on either basis.")


if __name__ == "__main__":
    main()
