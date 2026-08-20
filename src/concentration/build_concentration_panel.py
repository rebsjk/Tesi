"""
Phase-2 orchestration: applies the pure measure functions in
`src/concentration/measures.py` to the Phase-1 constituent panel
(`data_final/universe/`), at **month-end** frequency, using the
**monthly-fixed top-k cohort** convention frozen in
`docs/methodology_notes/csi_construction.md` ("Top-k subset selection and
reselection convention"):

- For CR-5/7/10, the top-k cohort is selected using weights as of each
  calendar month's *first available trading date*, then held fixed for the
  whole month. The reported CR-k value uses that same fixed cohort's
  weights *as of month-end* (not the weights that selected it) — a cohort
  member that has left the index by month-end contributes 0, not a missing
  value, and is logged.
- HHI, effective-N, and entropy_concentration use the full weight
  distribution directly at month-end (no top-k restriction — see
  csi_construction.md's candidate-components table).

This intentionally does NOT use `measures.compute_concentration_panel`,
which computes a plain daily, same-day top-k series (the "standalone"
CR-k variant csi_construction.md explicitly allows but distinguishes from
the monthly-fixed convention). The pure per-date math (`herfindahl_index`,
`effective_number_of_constituents`, `entropy_concentration`) is reused
as-is; only the cohort-selection/reselection logic is new here, since it
is entity-aware (needs to track which permno is in the cohort across two
different dates) and doesn't belong in measures.py's anonymous-array
function signatures.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.concentration.measures import (  # noqa: E402
    effective_number_of_constituents,
    entropy_concentration,
    herfindahl_index,
)
from src.utils.paths import CONCENTRATION_FINAL, LOGS, UNIVERSE_FINAL, latest_raw_file  # noqa: E402

logger = logging.getLogger(__name__)

CR_K_VALUES = (5, 7, 10)
RUN_TAG = datetime.now(timezone.utc).strftime("%Y%m%d")


def build_monthly_concentration_panel(
    panel: pd.DataFrame, cr_k_values: tuple[int, ...] = CR_K_VALUES
) -> tuple[pd.DataFrame, list[tuple]]:
    """Return (monthly concentration panel, cohort-attrition log entries).

    `panel` is the Phase-1 output (date, permno, weight, ...) — rows with a
    missing weight (e.g. an appended delisting-return observation with no
    dlycap) are dropped first, since they are not real weight observations.
    """
    panel = panel.dropna(subset=["weight"]).copy()
    panel["month"] = panel["date"].dt.to_period("M")

    month_start_date = panel.groupby("month")["date"].min()
    month_end_date = panel.groupby("month")["date"].max()

    records = []
    cohort_attrition = []

    for month in month_start_date.index:
        start_date = month_start_date[month]
        end_date = month_end_date[month]

        start_weights = panel.loc[panel["date"] == start_date].set_index("permno")["weight"]
        end_weights = panel.loc[panel["date"] == end_date].set_index("permno")["weight"]

        row = {
            "date": end_date,
            "n_constituents": int(end_weights.size),
            "hhi": herfindahl_index(end_weights.to_numpy()),
            "effective_n": effective_number_of_constituents(end_weights.to_numpy()),
            "entropy_concentration": entropy_concentration(end_weights.to_numpy()),
        }

        for k in cr_k_values:
            cohort = start_weights.nlargest(k).index
            missing = cohort.difference(end_weights.index)
            if len(missing):
                cohort_attrition.append((str(month), k, list(missing)))
            row[f"cr_{k}"] = float(end_weights.reindex(cohort, fill_value=0.0).sum())

        records.append(row)

    result = (
        pd.DataFrame.from_records(records)
        .sort_values("date")
        .reset_index(drop=True)
    )
    return result, cohort_attrition


def _configure_logging() -> Path:
    LOGS.mkdir(parents=True, exist_ok=True)
    log_path = LOGS / f"build_concentration_panel_{RUN_TAG}.txt"
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

    n_missing_weight = panel["weight"].isna().sum()
    logger.info(
        "%d of %d panel rows have a missing weight and are excluded from this build.",
        n_missing_weight,
        len(panel),
    )

    result, cohort_attrition = build_monthly_concentration_panel(panel)

    logger.info("Built %d monthly observations, %s to %s", len(result), result["date"].min(), result["date"].max())
    logger.info(
        "n_constituents range: %d to %d (median %.0f)",
        result["n_constituents"].min(),
        result["n_constituents"].max(),
        result["n_constituents"].median(),
    )
    if cohort_attrition:
        logger.info(
            "%d cohort-attrition events (a top-k cohort member left the index before "
            "month-end and contributed 0 to that month's CR-k): %s",
            len(cohort_attrition),
            cohort_attrition,
        )
    else:
        logger.info("No cohort-attrition events (every monthly top-k cohort member was "
                     "still in the index at month-end for the whole sample).")

    CONCENTRATION_FINAL.mkdir(parents=True, exist_ok=True)
    out_path = CONCENTRATION_FINAL / f"concentration_measures_monthly_{RUN_TAG}.csv"
    result.to_csv(out_path, index=False)
    logger.info("Wrote %s", out_path)


if __name__ == "__main__":
    main()
