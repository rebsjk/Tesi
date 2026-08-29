"""
Phase-5 source-cleaning step: turns the raw `data_raw/bloomberg/` SPX
index-level Q-signal pulls (ATM term structure, skew wings, VIX family +
SKEW index — all re-pulled 2026-08-28 with the corrected 2005-01 start
date, see docs/data_notes/bloomberg_field_reference.md) into cleaned
per-source files plus one merged daily panel.

Scope note (2026-08-29): index-level only. Constituent-level option
underlyings were explicitly ruled out of current scope when Bloomberg
terminal access ended — see docs/workflow_notes/data_inventory.md, "Open
decision blocking pull scope". If that scope changes later, a separate
constituent-level cleaning step would be needed; this script only ever
touches the three SPX/VIX-family raw files below.

Two things happen here, mirroring src/crsp/clean_sp500_raw.py's split
between per-source cleaning and the phase-level merge:

1. **Per-source cleaning** (-> data_interim/bloomberg/): parse dates,
   verify each file is sorted with no duplicate dates, coerce value
   columns to numeric, and log null counts per column without filling
   anything — this project doesn't impute silently (see
   docs/methodology_notes/risk_concentration_covariance_estimation.md's
   "complete-case exclusion, not pairwise imputation" for the same
   discipline applied elsewhere). Three known, already-diagnosed patterns
   are logged explicitly rather than treated as an error:
     - 1M skew-wing columns: 4 consecutive nulls, 2005-12-12 to
       2005-12-15 (a vendor-side gap, not a pull error).
     - vix9d / vix6m: structural leading nulls before their real start
       (~2011 / ~2008) — expected, documented in
       bloomberg_field_reference.md section 4.
     - vix3m / skew: null on US market-holiday dates that VIX Index still
       produces a row for but that produce no row at all in the two
       SPX-Index-sourced files — see point 2 below.

2. **Merge into one daily panel** (-> data_interim/options/): an INNER
   join on date across all three cleaned files. This is a deliberate
   choice, not the default pandas merge behavior stumbled into: the VIX
   family's calendar includes rows on US market holidays (vix9d/vix3m/
   vix6m/skew blank, vix itself sometimes populated) that the two
   SPX-Index-sourced files (ATM term structure, skew wings) never produce
   a row for at all. An inner join drops exactly those extra calendar
   rows, aligning the merged panel to the SPX options-market trading
   calendar — the calendar every other column in the merged panel is
   actually observed on. An outer join/reindex would need to carry
   NaN-only rows for a calendar no downstream consumer trades on.

Not done here — deliberately left to the eventual Phase-5 build script:
any Q-measure construction (smile fitting, moment extraction, CSI
conditioning). This script only cleans and merges; CLAUDE.md's priority
build order has Phase 5 starting after Phase 4 completes, and this is
prep work for that, not the phase itself.

Output:
- data_interim/bloomberg/bloomberg_spx_iv_term_structure_clean_<date>.csv
- data_interim/bloomberg/bloomberg_spx_skew_wings_clean_<date>.csv
- data_interim/bloomberg/bloomberg_vol_indexes_clean_<date>.csv
- data_interim/options/spx_q_signals_daily_clean_<date>.csv (the merge)
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.utils.paths import BLOOMBERG_INTERIM, BLOOMBERG_RAW, LOGS, OPTIONS_INTERIM, latest_raw_file  # noqa: E402

logger = logging.getLogger(__name__)

RUN_TAG = datetime.now(timezone.utc).strftime("%Y%m%d")

# Known, already-diagnosed gap: 4 consecutive trading days where the 1M
# skew-wing family (only) is blank. Logged if still present so a future
# re-pull that happens to fix it is visible, not silently unnoticed.
KNOWN_1M_WING_GAP = ["2005-12-12", "2005-12-13", "2005-12-14", "2005-12-15"]
ONE_MONTH_WING_COLUMNS = [
    "iv_1m_put_10d",
    "iv_1m_put_25d",
    "iv_1m_put_50d",
    "iv_1m_call_10d",
    "iv_1m_call_25d",
    "iv_1m_call_50d",
]


def load_raw() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    iv_path = latest_raw_file(BLOOMBERG_RAW, "bloomberg_spx_iv_term_structure")
    skew_path = latest_raw_file(BLOOMBERG_RAW, "bloomberg_spx_skew_wings")
    vol_path = latest_raw_file(BLOOMBERG_RAW, "bloomberg_vol_indexes")

    iv_term = pd.read_csv(iv_path, parse_dates=["date"])
    skew_wings = pd.read_csv(skew_path, parse_dates=["date"])
    vol_indexes = pd.read_csv(vol_path, parse_dates=["date"])

    logger.info("Loaded raw ATM term structure: %s (%d rows)", iv_path, len(iv_term))
    logger.info("Loaded raw skew wings:         %s (%d rows)", skew_path, len(skew_wings))
    logger.info("Loaded raw vol indexes:        %s (%d rows)", vol_path, len(vol_indexes))

    return iv_term, skew_wings, vol_indexes


def _clean_one(df: pd.DataFrame, name: str) -> pd.DataFrame:
    """Sort by date, verify no duplicate dates, coerce value columns to
    numeric, log null counts per column. Does not fill anything."""
    df = df.sort_values("date").reset_index(drop=True)

    dupes = df["date"][df["date"].duplicated()]
    if len(dupes):
        raise ValueError(f"{name}: {len(dupes)} duplicate dates found: {sorted(dupes.dt.date.unique())}")

    value_cols = [c for c in df.columns if c != "date"]
    for col in value_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    null_counts = df[value_cols].isna().sum()
    for col, n in null_counts.items():
        if n:
            first_null = df.loc[df[col].isna(), "date"].min().date()
            last_null = df.loc[df[col].isna(), "date"].max().date()
            logger.info(
                "%s.%s: %d null values (range %s to %s)", name, col, n, first_null, last_null
            )

    return df


def _check_known_1m_wing_gap(skew_wings_clean: pd.DataFrame) -> None:
    gap_dates = pd.to_datetime(KNOWN_1M_WING_GAP)
    rows = skew_wings_clean[skew_wings_clean["date"].isin(gap_dates)]
    still_null = rows[ONE_MONTH_WING_COLUMNS].isna().all(axis=None)
    if still_null:
        logger.info(
            "Confirmed known 1M skew-wing gap still present: %s (vendor-side, not a pull error — "
            "see docs/data_notes/bloomberg_field_reference.md)",
            KNOWN_1M_WING_GAP,
        )
    else:
        logger.warning(
            "Previously-documented 1M skew-wing gap (%s) is NOT fully null in this pull — "
            "the raw data may have changed since the gap was last diagnosed. Re-check before "
            "relying on the gap note in bloomberg_field_reference.md.",
            KNOWN_1M_WING_GAP,
        )


def merge_daily_panel(
    iv_term_clean: pd.DataFrame, skew_wings_clean: pd.DataFrame, vol_indexes_clean: pd.DataFrame
) -> pd.DataFrame:
    """Inner join on date — see module docstring for why inner, not outer.
    vix9d/vix3m/vix6m/skew keep whatever NaNs survive the join (structural
    leading-history nulls, or the rare non-holiday gap); nothing is filled.
    """
    merged = iv_term_clean.merge(skew_wings_clean, on="date", how="inner").merge(
        vol_indexes_clean, on="date", how="inner"
    )

    dropped_from_vol = len(vol_indexes_clean) - len(merged)
    logger.info(
        "Merged panel: %d rows (inner join). vol_indexes contributed %d rows not present in "
        "the SPX-Index-sourced files (expected: US market-holiday calendar rows — see module "
        "docstring) and %d rows shared with iv_term/skew_wings survived the join.",
        len(merged),
        dropped_from_vol,
        len(merged),
    )
    return merged


def _configure_logging() -> Path:
    LOGS.mkdir(parents=True, exist_ok=True)
    log_path = LOGS / f"clean_spx_q_signals_{RUN_TAG}.txt"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(log_path), logging.StreamHandler()],
    )
    return log_path


def main() -> None:
    log_path = _configure_logging()
    logger.info("Logging to %s", log_path)

    iv_term_raw, skew_wings_raw, vol_indexes_raw = load_raw()

    iv_term_clean = _clean_one(iv_term_raw, "iv_term_structure")
    skew_wings_clean = _clean_one(skew_wings_raw, "skew_wings")
    vol_indexes_clean = _clean_one(vol_indexes_raw, "vol_indexes")

    _check_known_1m_wing_gap(skew_wings_clean)

    BLOOMBERG_INTERIM.mkdir(parents=True, exist_ok=True)
    iv_term_out = BLOOMBERG_INTERIM / f"bloomberg_spx_iv_term_structure_clean_{RUN_TAG}.csv"
    skew_wings_out = BLOOMBERG_INTERIM / f"bloomberg_spx_skew_wings_clean_{RUN_TAG}.csv"
    vol_indexes_out = BLOOMBERG_INTERIM / f"bloomberg_vol_indexes_clean_{RUN_TAG}.csv"

    iv_term_clean.to_csv(iv_term_out, index=False)
    skew_wings_clean.to_csv(skew_wings_out, index=False)
    vol_indexes_clean.to_csv(vol_indexes_out, index=False)

    logger.info("Wrote %d rows to %s", len(iv_term_clean), iv_term_out)
    logger.info("Wrote %d rows to %s", len(skew_wings_clean), skew_wings_out)
    logger.info("Wrote %d rows to %s", len(vol_indexes_clean), vol_indexes_out)

    merged = merge_daily_panel(iv_term_clean, skew_wings_clean, vol_indexes_clean)

    OPTIONS_INTERIM.mkdir(parents=True, exist_ok=True)
    merged_out = OPTIONS_INTERIM / f"spx_q_signals_daily_clean_{RUN_TAG}.csv"
    merged.to_csv(merged_out, index=False)
    logger.info("Wrote %d merged rows to %s", len(merged), merged_out)
    logger.info(
        "Merged date range: %s to %s", merged["date"].min().date(), merged["date"].max().date()
    )


if __name__ == "__main__":
    main()
