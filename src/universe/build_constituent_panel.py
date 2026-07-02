"""Build the phase-1 constituent universe panel (membership, weights, returns).

Point-in-time design
---------------------
Bloomberg membership data must arrive as *intervals*, not a current snapshot:
one row per (entity_id, weight, start_date, end_date), where start_date is
the reconstitution date the weight became effective and end_date is the next
reconstitution date (or null/NaT if the constituent is still in the index as
of the last pull). This is what makes the panel usable as an input to a
state variable that will condition regressions run over the same historical
period — a panel built from "current membership applied backward" would
leak future index composition into past dates.

Interval boundary convention: **half-open, [start_date, end_date)**.
start_date is inclusive; end_date is exclusive. This REQUIRES that
end_date of an outgoing interval equal start_date of the succeeding
interval for the same entity — not "the last day the name was still a
member". If the source membership file instead marks end_date as the last
inclusive membership day, shift it forward by one day (to the next
interval's start_date) before calling `load_membership`/
`build_constituent_panel`, or every reconstitution boundary will silently
lose one day's observation for the outgoing name.

For every CRSP return observation we look up the membership interval whose
start_date is the most recent one on or before the return date (never a
later one), then keep the row only if the return date also falls before
that interval's end_date. A return date that doesn't fall inside any
interval means the entity was not a constituent on that date, and the row
is dropped from the panel (it is still a real CRSP observation — it simply
isn't part of the index universe at that time).
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

if __package__ in (None, ""):
    # Allow `python src/universe/build_constituent_panel.py` in addition to
    # `python -m src.universe.build_constituent_panel` — only the script's
    # own directory is put on sys.path by default in the former case.
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.utils.paths import (
    BLOOMBERG_INTERIM,
    CRSP_INTERIM,
    LOGS,
    MANUAL_RAW,
    UNIVERSE_FINAL,
    latest_raw_file,
)

logger = logging.getLogger(__name__)

REQUIRED_MEMBERSHIP_COLS = {"entity_id", "weight", "start_date", "end_date"}
REQUIRED_CROSSWALK_COLS = {"entity_id", "permno"}
REQUIRED_RETURNS_COLS = {"permno", "date", "ret"}


def load_membership(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["start_date", "end_date"])
    missing = REQUIRED_MEMBERSHIP_COLS - set(df.columns)
    if missing:
        raise ValueError(f"membership file {path} is missing columns: {missing}")
    return df


def load_crosswalk(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    missing = REQUIRED_CROSSWALK_COLS - set(df.columns)
    if missing:
        raise ValueError(f"crosswalk file {path} is missing columns: {missing}")
    return df


def load_returns(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["date"])
    missing = REQUIRED_RETURNS_COLS - set(df.columns)
    if missing:
        raise ValueError(f"returns file {path} is missing columns: {missing}")
    return df


def _check_membership_interval_structure(membership: pd.DataFrame) -> None:
    """Validate the per-permno interval structure `merge_asof` silently relies on.

    `merge_asof` does not error on overlapping or duplicate-start intervals —
    it just picks the nearest one, which would silently produce a wrong (but
    plausible-looking) panel. This checks, per permno, that:
    - at most the most recent interval is open-ended (NaT end_date);
    - consecutive intervals do not overlap (end_date <= next start_date).

    Gaps (end_date < next start_date) are allowed — e.g. a name can leave and
    later re-enter the index — but are logged, since a *systematic* one-day
    gap between every consecutive interval across many permnos would signal
    an inclusive- rather than exclusive-end_date convention upstream (see
    module docstring).
    """
    gap_days = []
    for permno, group in membership.sort_values("start_date").groupby("permno"):
        starts = group["start_date"].to_numpy()
        ends = group["end_date"].to_numpy()
        if len(group) <= 1:
            continue

        open_ended = pd.isna(ends)
        if open_ended[:-1].any():
            raise AssertionError(
                f"permno {permno} has an open-ended membership interval "
                "(NaT end_date) that is not its most recent interval."
            )

        overlaps = ends[:-1] > starts[1:]
        if overlaps.any():
            raise AssertionError(
                f"permno {permno} has overlapping membership intervals — "
                "merge_asof would silently pick one and drop the other. "
                "Fix the source membership data before building the panel."
            )

        gaps = (starts[1:] - ends[:-1]).astype("timedelta64[D]").astype(int)
        gap_days.extend(gaps[gaps > 0].tolist())

    if gap_days:
        gap_series = pd.Series(gap_days)
        logger.info(
            "%d gaps between consecutive membership intervals (median %.1f days, "
            "%d of them exactly 1 day). A large count of 1-day gaps suggests "
            "end_date is being supplied as inclusive rather than exclusive — "
            "see the interval boundary convention in the module docstring.",
            len(gap_series),
            gap_series.median(),
            int((gap_series == 1).sum()),
        )


def build_constituent_panel(
    membership: pd.DataFrame,
    crosswalk: pd.DataFrame,
    returns: pd.DataFrame,
) -> pd.DataFrame:
    """Return the point-in-time entity-date constituent panel.

    Output columns: date, permno, entity_id, weight, ret, membership_start,
    membership_end.
    """
    membership_pn = membership.merge(crosswalk, on="entity_id", how="left")
    unmatched = membership_pn["permno"].isna().sum()
    if unmatched:
        logger.warning(
            "%d of %d membership intervals had no crosswalk match to a PERMNO "
            "and were dropped.",
            unmatched,
            len(membership_pn),
        )
    membership_pn = membership_pn.dropna(subset=["permno"]).copy()
    membership_pn["permno"] = membership_pn["permno"].astype(returns["permno"].dtype)

    _check_membership_interval_structure(membership_pn)

    returns_sorted = returns.sort_values(["permno", "date"]).reset_index(drop=True)
    membership_sorted = membership_pn.sort_values(
        ["permno", "start_date"]
    ).reset_index(drop=True)

    # asof-merge with direction="backward" only ever looks at membership
    # intervals whose start_date is <= the return date — this is what
    # prevents a later reconstitution from leaking into an earlier date.
    panel = pd.merge_asof(
        returns_sorted,
        membership_sorted,
        left_on="date",
        right_on="start_date",
        by="permno",
        direction="backward",
    )

    # A row can lack a membership match altogether (permno never in the
    # index, or the return predates the permno's first membership interval)
    # — merge_asof leaves entity_id/end_date null in that case too, so
    # has_match must gate both the "still open" and "within interval" checks
    # to avoid conflating "no match" with "open-ended interval".
    has_match = panel["entity_id"].notna()
    still_open = has_match & panel["end_date"].isna()
    within_interval = has_match & (panel["date"] < panel["end_date"])
    in_index = within_interval | still_open

    dropped = int((~in_index).sum())
    logger.info(
        "%d of %d return observations fell outside any membership interval "
        "and were excluded from the constituent panel.",
        dropped,
        len(panel),
    )

    panel = panel.loc[in_index].copy()
    panel = panel.rename(columns={"start_date": "membership_start", "end_date": "membership_end"})
    panel = panel[
        ["date", "permno", "entity_id", "weight", "ret", "membership_start", "membership_end"]
    ].reset_index(drop=True)

    _assert_point_in_time_integrity(panel)
    _assert_unique_grain(panel)

    return panel


def _assert_point_in_time_integrity(panel: pd.DataFrame) -> None:
    before_start = panel["date"] < panel["membership_start"]
    after_end = panel["membership_end"].notna() & (panel["date"] >= panel["membership_end"])
    violations = before_start | after_end
    if violations.any():
        raise AssertionError(
            f"{violations.sum()} panel rows fall outside their own membership "
            "interval — this indicates a bug in the point-in-time join, not a "
            "data quality issue to be routed to data-validator."
        )


def _assert_unique_grain(panel: pd.DataFrame) -> None:
    dupes = panel.duplicated(subset=["permno", "date"]).sum()
    if dupes:
        # Membership overlap is ruled out by _check_membership_interval_structure
        # before the merge runs, so a duplicate grain here can only mean the
        # input returns data itself has duplicate (permno, date) rows.
        raise AssertionError(
            f"{dupes} duplicate (permno, date) rows in the constituent panel — "
            "the input returns data has duplicate (permno, date) rows."
        )


def _configure_run_logging() -> Path:
    LOGS.mkdir(parents=True, exist_ok=True)
    log_path = LOGS / f"build_constituent_panel_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(log_path), logging.StreamHandler()],
    )
    return log_path


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--membership", type=Path, default=None)
    parser.add_argument("--crosswalk", type=Path, default=None)
    parser.add_argument("--returns", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    log_path = _configure_run_logging()
    logger.info("Logging to %s", log_path)

    membership_path = args.membership or latest_raw_file(
        BLOOMBERG_INTERIM, "bloomberg_membership_weights"
    )
    crosswalk_path = args.crosswalk or latest_raw_file(
        MANUAL_RAW, "manual_permno_bbgid_crosswalk"
    )
    returns_path = args.returns or latest_raw_file(CRSP_INTERIM, "crsp_returns")

    logger.info("membership: %s", membership_path)
    logger.info("crosswalk:  %s", crosswalk_path)
    logger.info("returns:    %s", returns_path)

    membership = load_membership(membership_path)
    crosswalk = load_crosswalk(crosswalk_path)
    returns = load_returns(returns_path)

    panel = build_constituent_panel(membership, crosswalk, returns)

    UNIVERSE_FINAL.mkdir(parents=True, exist_ok=True)
    out_path = args.out or UNIVERSE_FINAL / (
        f"universe_constituent_panel_{datetime.now(timezone.utc):%Y%m%d}.parquet"
    )
    panel.to_parquet(out_path, index=False)
    logger.info("Wrote %d rows to %s", len(panel), out_path)


if __name__ == "__main__":
    main()
