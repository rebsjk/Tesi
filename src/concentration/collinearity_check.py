"""
Phase-3 step 1: mandatory collinearity check across the six Phase-2
concentration measures, before any aggregation method (Option A/B/C in
docs/methodology_notes/csi_construction.md) is chosen.

Computes Pearson and Spearman pairwise correlation on the monthly
concentration panel (`data_final/concentration/`), with `effective_n`
sign-flipped (negated) so all six series agree on direction (higher =
more concentrated) before comparison — matching the direction convention
in `src/concentration/measures.py::concentration_direction`.

Threshold: |r| > 0.90 (Pearson OR Spearman), decided 2026-08-20 — see
docs/methodology_notes/csi_construction.md for the rationale (stricter
than the doc's 0.85 placeholder, chosen so components sharing most but
not all of their variance are not discarded prematurely).

Computed on both **levels** and **first differences (month-over-month
change)** of each series. The levels-only check risked overstating
collinearity: 2000-2026 has one dominant secular trend (decline to 2014,
then a strong rise through the Mag7 era), and correlating two
long-trending series in levels tends to inflate correlation mechanically
(shared nonstationary component), independent of whether the measures
actually move together at a shorter, operationally relevant horizon.
Differencing removes the shared trend and tests whether the high levels
correlation reflects genuine month-to-month comovement or just a common
trend masking short-run divergence. Both results are reported side by
side, not one replacing the other, since the aggregation-method decision
(Option A vs. B/C) should weigh both.

The (hhi, effective_n_flipped) pair is a mathematical identity
(`effective_n = 1/hhi`), not an empirical finding — it is reported
separately from the other 14 pairs, which are the actual object of this
check, per the user's explicit instruction not to blend a deterministic
exclusion into the empirical collinearity discussion.
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

from src.utils.paths import CONCENTRATION_FINAL, FIGURES, LOGS, TABLES, latest_raw_file  # noqa: E402

logger = logging.getLogger(__name__)

SERIES_COLS = ["hhi", "cr_5", "cr_7", "cr_10", "effective_n_flipped", "entropy_concentration"]
DETERMINISTIC_PAIR = frozenset({"hhi", "effective_n_flipped"})
THRESHOLD = 0.90
RUN_TAG = datetime.now(timezone.utc).strftime("%Y%m%d")


def load_series() -> pd.DataFrame:
    panel_path = latest_raw_file(CONCENTRATION_FINAL, "concentration_measures_monthly")
    df = pd.read_csv(panel_path, parse_dates=["date"])
    df["effective_n_flipped"] = -df["effective_n"]
    return df.set_index("date")[SERIES_COLS]


def flag_pairs(corr: pd.DataFrame, method: str, basis: str) -> list[dict]:
    flags = []
    for a, b in combinations(SERIES_COLS, 2):
        r = corr.loc[a, b]
        if abs(r) > THRESHOLD:
            flags.append(
                {
                    "pair": f"{a} / {b}",
                    "method": method,
                    "basis": basis,
                    "r": r,
                    "deterministic_a_priori": frozenset({a, b}) == DETERMINISTIC_PAIR,
                }
            )
    return flags


def plot_heatmaps(matrices: dict[str, pd.DataFrame], out_path: Path) -> None:
    """2x2 grid: top row = levels (Pearson, Spearman), bottom row = first
    differences (Pearson, Spearman) — side by side for direct comparison,
    per the user's explicit request not to have one replace the other.
    """
    fig, axes = plt.subplots(2, 2, figsize=(13, 11))
    layout = [
        (axes[0, 0], matrices["pearson_levels"], "Pearson — levels"),
        (axes[0, 1], matrices["spearman_levels"], "Spearman — levels"),
        (axes[1, 0], matrices["pearson_diff"], "Pearson — 1st differences (MoM change)"),
        (axes[1, 1], matrices["spearman_diff"], "Spearman — 1st differences (MoM change)"),
    ]
    for ax, corr, title in layout:
        sns.heatmap(
            corr,
            ax=ax,
            annot=True,
            fmt=".2f",
            cmap="RdBu_r",
            vmin=-1,
            vmax=1,
            square=True,
            cbar_kws={"shrink": 0.8},
        )
        ax.set_title(title)
    fig.suptitle(
        "CSI candidate-component correlation — monthly, 2000-2026 "
        "(effective_n sign-flipped) — levels vs. 1st differences",
        fontsize=12,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(out_path, dpi=150)


def _configure_logging() -> Path:
    LOGS.mkdir(parents=True, exist_ok=True)
    log_path = LOGS / f"collinearity_check_{RUN_TAG}.txt"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(log_path), logging.StreamHandler()],
    )
    return log_path


def main() -> None:
    log_path = _configure_logging()
    logger.info("Logging to %s", log_path)

    series = load_series()
    diffs = series.diff().dropna(how="all")
    logger.info("Loaded %d monthly observations, %s to %s", len(series), series.index.min(), series.index.max())
    logger.info("First-differenced series: %d observations (first month dropped, no prior diff)", len(diffs))

    matrices = {
        "pearson_levels": series.corr(method="pearson"),
        "spearman_levels": series.corr(method="spearman"),
        "pearson_diff": diffs.corr(method="pearson"),
        "spearman_diff": diffs.corr(method="spearman"),
    }

    TABLES.mkdir(parents=True, exist_ok=True)
    for name, corr in matrices.items():
        path = TABLES / f"csi_component_correlation_{name}_{RUN_TAG}.csv"
        corr.to_csv(path)
        logger.info("Wrote %s", path)

    FIGURES.mkdir(parents=True, exist_ok=True)
    fig_path = FIGURES / f"csi_component_correlation_levels_vs_diff_{RUN_TAG}.png"
    plot_heatmaps(matrices, fig_path)
    logger.info("Wrote %s", fig_path)

    all_flags = (
        flag_pairs(matrices["pearson_levels"], "pearson", "levels")
        + flag_pairs(matrices["spearman_levels"], "spearman", "levels")
        + flag_pairs(matrices["pearson_diff"], "pearson", "diff")
        + flag_pairs(matrices["spearman_diff"], "spearman", "diff")
    )
    deterministic_flags = [f for f in all_flags if f["deterministic_a_priori"]]
    empirical_flags = [f for f in all_flags if not f["deterministic_a_priori"]]

    logger.info("=" * 70)
    logger.info("Threshold: |r| > %.2f (Pearson OR Spearman), levels AND 1st differences", THRESHOLD)
    logger.info(
        "A priori deterministic exclusion (hhi / effective_n_flipped, "
        "effective_n = 1/hhi by construction — not an empirical finding):"
    )
    for f in deterministic_flags:
        logger.info("  [%s] %s: %s r=%.4f", f["basis"], f["pair"], f["method"], f["r"])

    logger.info("Empirical flags among the other 14 pairs (%d found across both bases):", len(empirical_flags))
    for f in empirical_flags:
        logger.info("  [%s] %s: %s r=%.4f", f["basis"], f["pair"], f["method"], f["r"])

    if not empirical_flags:
        logger.info("  none — no non-deterministic pair exceeds the threshold on either basis.")


if __name__ == "__main__":
    main()
