"""Pull historical S&P 500 membership with float-adjusted weights (Priority 3
— universe/weight cross-check against CRSP).

Grid, not exact effective dates: this first version snapshots membership
on the last *business* day of every calendar quarter (pandas "BQE") from
`--start-year` (default 2005) through today, not the official SPDJI
reconstitution effective dates. Close enough for a robustness check against
CRSP weights; swap in the real effective-date calendar later if the
comparison turns out to be sensitive to the few extra days of drift.

Bloomberg query approach, and a real limitation found while building this
(confirmed in terminal 2026-07-02):

  `blp.bds("SPX Index", "INDX_MWEIGHT_PX", END_DATE_OVERRIDE=<YYYYMMDD>)` is
  the natural bulk-field way to replicate a historical INDX_MEMBERS-style
  snapshot — one request per as-of date returns every constituent for that
  date (delisted names come back as Bloomberg's stable "<digits>D <EXCH>"
  placeholder tickers, e.g. "1288453D UW", confirmed by their appearance
  changing correctly across different override dates) plus that date's
  "Current Price".

  BUT: the "Percent Weight" / "Actual Weight" subfields in that same bulk
  response come back as the exact same degenerate near-zero constant
  (~-2.4e-14) for every single member, on every date tried. This was cross-
  checked three ways before concluding it's a data-entitlement gap rather
  than an xbbg bug: (1) `INDX_MWEIGHT` (current, no override) shows the
  same degenerate constant for all 503 current members; (2)
  `INDX_MWEIGHT_HIST` with the override shows it too; (3) a plain scalar
  `PERCENT_WEIGHT` BDP request on a single equity returns blank. Meanwhile
  `INDX_MWEIGHT_PX`'s own "Current Price" subfield — decoded by the exact
  same request/response path — comes back correctly differentiated per
  security. That rules out a general numeric-parsing bug and points at this
  subscription simply not being entitled to official index-weight data.

  Workaround used here: reconstruct a float-adjusted weight ourselves from
  fields that ARE entitled and DO return real, differentiated values —
  `EQY_SH_OUT` (shares outstanding) and `EQY_FREE_FLOAT_PCT` (free-float
  percentage), pulled via `blp.bdh(..., periodicitySelection="QUARTERLY")`
  for the whole member universe in one batched call, joined to each
  member's bulk-pull "Current Price":

      float_shares  = EQY_SH_OUT * EQY_FREE_FLOAT_PCT / 100
      float_mktcap  = float_shares * price
      weight_float  = float_mktcap / sum(float_mktcap over that as_of_date)

  This is a proxy for S&P's own investable-weight-factor methodology, not
  a reproduction of it — good enough for a robustness check, not for
  claiming it matches SPDJI's published weights exactly. The raw (broken)
  Bloomberg field is still carried through as `bbg_pct_weight_raw` so the
  entitlement gap is visible/auditable in the output CSV rather than
  silently dropped.

  If index-weight entitlement is added to this subscription later, delete
  the reconstruction step and rename the confirmed-good `INDX_MWEIGHT_PX`
  "Percent Weight" column directly to `weight_float` instead.

Re-run the confirmation checklist in docs/data_notes/bloomberg_field_reference.md
before trusting this workaround again if the subscription changes.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.utils.paths import BLOOMBERG_RAW

try:
    from xbbg import blp

    BLOOMBERG_AVAILABLE = True
except ImportError:
    blp = None
    BLOOMBERG_AVAILABLE = False


INDEX_TICKER = "SPX Index"
CONTENT_SLUG = "spx_members_float"

MEMBERSHIP_COLUMNS = {
    "Index Member": "member_ticker",
    "Percent Weight": "bbg_pct_weight_raw",
    "Actual Weight": "bbg_actual_weight_raw",
    "Current Price": "price",
}


def quarterly_grid(start_year: int, end_date: date) -> list[date]:
    """Business quarter-end dates from start_year Q1 through end_date."""
    idx = pd.date_range(start=f"{start_year}-01-01", end=end_date, freq="BQE")
    return [d.date() for d in idx]


def _membership_snapshot(as_of: date) -> pd.DataFrame:
    """One INDX_MWEIGHT_PX bulk pull for a single as-of date.

    Returns columns: as_of_date, member_ticker, bbg_pct_weight_raw,
    bbg_actual_weight_raw, price. The two "raw" weight columns are expected
    to be the degenerate Bloomberg constant described in the module
    docstring — kept for auditability, not used as the real weight.
    """
    raw = blp.bds(
        INDEX_TICKER,
        "INDX_MWEIGHT_PX",
        END_DATE_OVERRIDE=as_of.strftime("%Y%m%d"),
        backend="pandas",
    )
    missing = set(MEMBERSHIP_COLUMNS) - set(raw.columns)
    if missing:
        raise ValueError(f"INDX_MWEIGHT_PX response missing expected columns: {missing}")

    df = raw.rename(columns=MEMBERSHIP_COLUMNS)[list(MEMBERSHIP_COLUMNS.values())]
    df.insert(0, "as_of_date", pd.Timestamp(as_of))
    return df


def fetch_membership(grid: list[date]) -> pd.DataFrame:
    """Pull one membership snapshot per grid date, skipping (and logging)
    any date Bloomberg rejects rather than failing the whole pull."""
    snapshots = []
    for as_of in grid:
        try:
            snapshots.append(_membership_snapshot(as_of))
        except Exception as exc:
            print(f"WARNING: membership snapshot failed for {as_of}: {exc!r}", file=sys.stderr)
    if not snapshots:
        return pd.DataFrame(columns=["as_of_date", *MEMBERSHIP_COLUMNS.values()])
    return pd.concat(snapshots, ignore_index=True)


def fetch_fundamentals(member_tickers: list[str], start_year: int, end_date: date) -> pd.DataFrame:
    """One batched quarterly BDH pull of shares-out/float-% for the whole
    member universe seen across all grid dates, reused for every as_of_date.

    Returns columns: member_ticker, date, EQY_SH_OUT, EQY_FREE_FLOAT_PCT.
    """
    equities = [f"{t} Equity" for t in member_tickers]
    raw = blp.bdh(
        tickers=equities,
        flds=["EQY_SH_OUT", "EQY_FREE_FLOAT_PCT"],
        start_date=f"{start_year}-01-01",
        end_date=end_date.isoformat(),
        backend="pandas",
        periodicitySelection="QUARTERLY",
    )
    if not isinstance(raw, pd.DataFrame) and hasattr(raw, "to_pandas"):
        raw = raw.to_pandas()

    long_df = raw.copy()
    long_df["date"] = pd.to_datetime(long_df["date"])
    long_df["value"] = pd.to_numeric(long_df["value"], errors="coerce")
    long_df["member_ticker"] = long_df["ticker"].str.replace(" Equity", "", regex=False)

    wide = long_df.pivot_table(index=["member_ticker", "date"], columns="field", values="value")
    wide = wide.reset_index()
    for col in ("EQY_SH_OUT", "EQY_FREE_FLOAT_PCT"):
        if col not in wide.columns:
            wide[col] = pd.Series(dtype="float64")
    return wide[["member_ticker", "date", "EQY_SH_OUT", "EQY_FREE_FLOAT_PCT"]]


def fetch_names_and_sectors(member_tickers: list[str]) -> pd.DataFrame:
    """Current (as-of-pull-date, NOT point-in-time) name + GICS sector for
    the member universe — a cheap descriptive join, not a historical field.
    Securities Bloomberg rejects (mostly delisted placeholder tickers) come
    back as NaN rather than failing the whole request."""
    equities = [f"{t} Equity" for t in member_tickers]
    raw = blp.bdp(
        tickers=equities,
        flds=["SECURITY_NAME", "GICS_SECTOR_NAME"],
        backend="pandas",
        include_security_errors=False,
    )
    if not isinstance(raw, pd.DataFrame) and hasattr(raw, "to_pandas"):
        raw = raw.to_pandas()

    wide = raw.pivot_table(index="ticker", columns="field", values="value", aggfunc="first")
    wide = wide.reset_index().rename(columns={"ticker": "equity_ticker"})
    wide["member_ticker"] = wide["equity_ticker"].str.replace(" Equity", "", regex=False)
    for col in ("SECURITY_NAME", "GICS_SECTOR_NAME"):
        if col not in wide.columns:
            wide[col] = pd.Series(dtype="object")
    return wide[["member_ticker", "SECURITY_NAME", "GICS_SECTOR_NAME"]].rename(
        columns={"SECURITY_NAME": "name", "GICS_SECTOR_NAME": "sector"}
    )


def build_panel(start_year: int, end_date: date) -> pd.DataFrame:
    grid = quarterly_grid(start_year, end_date)
    membership = fetch_membership(grid)
    if membership.empty:
        return membership

    universe = sorted(membership["member_ticker"].unique())
    fundamentals = fetch_fundamentals(universe, start_year, end_date)
    names_sectors = fetch_names_and_sectors(universe)

    merged = membership.merge(
        fundamentals,
        left_on=["member_ticker", "as_of_date"],
        right_on=["member_ticker", "date"],
        how="left",
    ).merge(names_sectors, on="member_ticker", how="left")

    merged["float_shares_m"] = merged["EQY_SH_OUT"] * merged["EQY_FREE_FLOAT_PCT"] / 100
    merged["float_mktcap"] = merged["float_shares_m"] * merged["price"]
    total_by_date = merged.groupby("as_of_date")["float_mktcap"].transform("sum")
    merged["weight_float"] = merged["float_mktcap"] / total_by_date

    out = merged.rename(columns={"member_ticker": "ticker", "EQY_SH_OUT": "shares_out_m"})
    return out[
        [
            "as_of_date",
            "ticker",
            "name",
            "weight_float",
            "shares_out_m",
            "sector",
            "price",
            "bbg_pct_weight_raw",
        ]
    ].sort_values(["as_of_date", "ticker"]).reset_index(drop=True)


def default_output_path(as_of: date | None = None) -> Path:
    as_of = as_of or datetime.now(timezone.utc).date()
    BLOOMBERG_RAW.mkdir(parents=True, exist_ok=True)
    return BLOOMBERG_RAW / f"bloomberg_{CONTENT_SLUG}_{as_of:%Y%m%d}.csv"


def main() -> None:
    if not BLOOMBERG_AVAILABLE:
        raise RuntimeError(
            "xbbg is not installed, or no Bloomberg Desktop API session is "
            "available. Install xbbg and run this from a machine with an "
            "active Bloomberg Terminal session to actually pull data."
        )

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-year", type=int, default=2005)
    parser.add_argument("--end", type=date.fromisoformat, default=None)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    end_date = args.end or (datetime.now(timezone.utc).date() - timedelta(days=1))
    out_path = args.out or default_output_path()

    df = build_panel(args.start_year, end_date)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)

    if df.empty:
        print(f"Wrote 0 rows to {out_path} — no membership snapshots returned.")
        return

    print(f"Wrote {len(df)} rows to {out_path}")
    print(f"Date range: {df['as_of_date'].min().date()} to {df['as_of_date'].max().date()}")
    print(f"Distinct as-of dates: {df['as_of_date'].nunique()}, distinct tickers: {df['ticker'].nunique()}")

    degenerate_bbg = df["bbg_pct_weight_raw"].abs().lt(1e-8).mean()
    print(
        f"NOTE: bbg_pct_weight_raw is degenerate (near-zero) for "
        f"{degenerate_bbg:.0%} of rows — see module docstring; use "
        f"weight_float (reconstructed) instead."
    )
    missing_weight = df["weight_float"].isna().mean()
    print(f"weight_float missing for {missing_weight:.1%} of rows (no EQY_SH_OUT/price match).")


if __name__ == "__main__":
    main()
