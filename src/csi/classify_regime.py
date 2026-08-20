"""
Phase-3 step 3: state/regime classification for the composite CSI.

Trailing-quantile thresholds, per csi_construction.md's "State / regime
classification" section: tercile cutoffs (33rd/67th percentile) of the
CSI's own trailing 60-month rolling window, computed inclusive of the
current month (point-in-time valid — never uses data after t).

Rolling, not expanding: a genuinely different design question from the
composite's own expanding z-score. Regime classification asks "is this
month unusual relative to recent conditions," not "relative to the whole
sample since 2000" — an expanding classification on a persistently
trending series like this one would make "high regime" almost
synonymous with "post-2019," which is a poor conditioning variable for
Phase 4/6 regressions (near-collinear with a calendar-time trend). 60
months (5 years) reuses the length already flagged as a Phase-6
robustness candidate for the composite itself, rather than introducing a
new arbitrary constant. See docs/methodology_notes/csi_construction.md
for the full reasoning and the deferred alternatives (median split,
asymmetric/tail-only thresholds, hysteresis, Markov-switching).

No hysteresis in this first pass — raw threshold crossing, with a
flickering diagnostic (quick round-trip transitions) logged so a Phase-6
hysteresis/Markov-switching revisit is an empirical decision, not a
guess.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.utils.paths import CSI_FINAL, LOGS, latest_raw_file  # noqa: E402

logger = logging.getLogger(__name__)

ROLLING_WINDOW_MONTHS = 60
LOWER_PCT = 0.33
UPPER_PCT = 0.67
GFC_START = "2007-12-01"
GFC_END = "2009-06-30"
RUN_TAG = datetime.now(timezone.utc).strftime("%Y%m%d")


def classify_regime(csi: pd.DataFrame, window: int = ROLLING_WINDOW_MONTHS) -> pd.DataFrame:
    df = csi.sort_values("date").set_index("date").copy()

    roll = df["csi"].rolling(window=window, min_periods=window)
    df["rolling_p33"] = roll.quantile(LOWER_PCT)
    df["rolling_p67"] = roll.quantile(UPPER_PCT)

    def label(row):
        if pd.isna(row["rolling_p33"]):
            return None
        if row["csi"] <= row["rolling_p33"]:
            return "low"
        if row["csi"] >= row["rolling_p67"]:
            return "high"
        return "medium"

    df["regime"] = df.apply(label, axis=1)
    return df.reset_index()


def check_gfc_coverage(result: pd.DataFrame) -> tuple[bool, pd.DataFrame]:
    gfc = result[(result["date"] >= GFC_START) & (result["date"] <= GFC_END)]
    undefined = gfc[gfc["regime"].isna()]
    return len(undefined) == 0, undefined


def count_flicker_events(result: pd.DataFrame, max_gap_months: int = 2) -> list[dict]:
    """A 'flicker' = the regime returns to its previous value within
    `max_gap_months` after having left it (a quick round trip), e.g.
    medium -> high -> medium within 2 months. Diagnostic only, no
    correction applied.
    """
    labeled = result.dropna(subset=["regime"]).reset_index(drop=True)
    events = []
    for i in range(1, len(labeled) - 1):
        prev_regime = labeled.loc[i - 1, "regime"]
        cur_regime = labeled.loc[i, "regime"]
        if cur_regime == prev_regime:
            continue
        # look ahead up to max_gap_months for a return to prev_regime
        for j in range(i + 1, min(i + 1 + max_gap_months, len(labeled))):
            if labeled.loc[j, "regime"] == prev_regime:
                events.append(
                    {
                        "left_date": str(labeled.loc[i, "date"].date()),
                        "returned_date": str(labeled.loc[j, "date"].date()),
                        "from_regime": prev_regime,
                        "to_regime": cur_regime,
                        "months_away": j - i + 1,
                    }
                )
                break
    return events


def _configure_logging() -> Path:
    LOGS.mkdir(parents=True, exist_ok=True)
    log_path = LOGS / f"classify_regime_{RUN_TAG}.txt"
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
        "Regime classification parameters: window=rolling %d months (inclusive of t), "
        "thresholds=tercile (%.0f/%.0f pct), hysteresis=none",
        ROLLING_WINDOW_MONTHS,
        LOWER_PCT * 100,
        UPPER_PCT * 100,
    )

    csi_path = latest_raw_file(CSI_FINAL, "csi_composite_monthly")
    logger.info("Loading composite CSI: %s", csi_path)
    csi = pd.read_csv(csi_path, parse_dates=["date"])[["date", "csi"]]

    result = classify_regime(csi)

    n_undefined = result["regime"].isna().sum()
    first_defined = result.loc[result["regime"].notna(), "date"].min()
    logger.info(
        "%d of %d months have no regime (burn-in) — first defined regime: %s",
        n_undefined,
        len(result),
        first_defined,
    )

    gfc_covered, gfc_undefined = check_gfc_coverage(result)
    if gfc_covered:
        logger.info(
            "GFC coverage check PASSED: every month in [%s, %s] has a defined regime.",
            GFC_START,
            GFC_END,
        )
    else:
        logger.error(
            "GFC coverage check FAILED: %d month(s) in [%s, %s] have no regime defined "
            "(burn-in extends into the GFC window): %s",
            len(gfc_undefined),
            GFC_START,
            GFC_END,
            gfc_undefined["date"].tolist(),
        )

    regime_counts = result["regime"].value_counts(dropna=True)
    logger.info("Regime distribution (defined months only): %s", regime_counts.to_dict())

    flickers = count_flicker_events(result)
    logger.info(
        "Flickering diagnostic: %d quick round-trip transition(s) (regime returns to its "
        "prior value within 2 months) out of %d defined months.",
        len(flickers),
        len(result) - n_undefined,
    )
    for f in flickers:
        logger.info("  %s", f)

    out_path = CSI_FINAL / f"csi_regime_monthly_{RUN_TAG}.csv"
    result.to_csv(out_path, index=False)
    logger.info("Wrote %s", out_path)


if __name__ == "__main__":
    main()
