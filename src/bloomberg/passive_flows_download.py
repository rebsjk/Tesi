"""Skeleton: pull passive-fund AUM and net flows for a given set of ETF/fund
tickers (structure only — no confirmed ticker universe yet).

Not run as part of this batch: the full list of index/sector ETFs relevant
to the CSI passive-flows angle (SPY/IVV/VOO plus whatever sector or factor
funds the thesis ends up using) hasn't been decided yet, so this file
intentionally ships with an empty default universe rather than a guessed
one — fill in TICKERS before running for real.

Field mnemonics ARE confirmed in terminal (2026-07-02) against `SPY US
Equity`, following the same procedure as
docs/data_notes/bloomberg_field_reference.md:

| Concept | Mnemonic | Notes |
|---|---|---|
| Fund AUM | `FUND_TOTAL_ASSETS` | Confirmed non-blank, daily history available via BDH. Units: millions of the fund's listing currency. |
| Fund net flow | `FUND_FLOW` | Confirmed non-blank, daily history available via BDH. Same units as AUM. |

`ESTIMATED_FLOW` was also tried and came back blank for SPY — not used.
Re-run the confirmation checklist in bloomberg_field_reference.md for any
new ticker before trusting these two fields for it; ETF share classes vary
in what they report.
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


# Fill in before running for real — intentionally empty in this skeleton.
TICKERS: list[str] = []

FIELDS = {
    "aum": "FUND_TOTAL_ASSETS",
    "flow": "FUND_FLOW",
}

CONTENT_SLUG = "passive_flows"


def fetch_history_passive_flows(
    tickers: list[str], start_date: date, end_date: date
) -> pd.DataFrame:
    """Pull daily AUM + net flow history for a list of ETF/fund tickers.

    Returns a long DataFrame: columns date, ticker, aum, flow. Raises
    RuntimeError if xbbg/Bloomberg Desktop API isn't available, and
    ValueError if `tickers` is empty — only called from main(), so
    importing this module never requires Bloomberg to be installed.
    """
    if not BLOOMBERG_AVAILABLE:
        raise RuntimeError(
            "xbbg is not installed, or no Bloomberg Desktop API session is "
            "available. Install xbbg and run this from a machine with an "
            "active Bloomberg Terminal session to actually pull data."
        )
    if not tickers:
        raise ValueError("tickers is empty — fill in TICKERS (or pass --tickers) before running.")

    raw = blp.bdh(
        tickers=tickers,
        flds=list(FIELDS.values()),
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        backend="pandas",
    )
    if not isinstance(raw, pd.DataFrame) and hasattr(raw, "to_pandas"):
        raw = raw.to_pandas()

    long_df = raw.copy()
    long_df["date"] = pd.to_datetime(long_df["date"])
    long_df["value"] = pd.to_numeric(long_df["value"], errors="coerce")

    mnemonic_to_concept = {v: k for k, v in FIELDS.items()}
    long_df["concept"] = long_df["field"].map(mnemonic_to_concept)

    wide = long_df.pivot_table(index=["ticker", "date"], columns="concept", values="value")
    wide = wide.reset_index()
    for concept in FIELDS:
        if concept not in wide.columns:
            wide[concept] = pd.Series(dtype="float64")

    return wide[["date", "ticker", "aum", "flow"]].sort_values(["ticker", "date"]).reset_index(drop=True)


def default_output_path(as_of: date | None = None) -> Path:
    as_of = as_of or datetime.now(timezone.utc).date()
    BLOOMBERG_RAW.mkdir(parents=True, exist_ok=True)
    return BLOOMBERG_RAW / f"bloomberg_{CONTENT_SLUG}_{as_of:%Y%m%d}.csv"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tickers", nargs="+", default=None, help="e.g. --tickers 'SPY US Equity' 'IVV US Equity'")
    parser.add_argument("--start", type=date.fromisoformat, default=None)
    parser.add_argument("--end", type=date.fromisoformat, default=None)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    tickers = args.tickers or TICKERS
    end_date = args.end or datetime.now(timezone.utc).date()
    start_date = args.start or (end_date - timedelta(days=30))
    out_path = args.out or default_output_path()

    df = fetch_history_passive_flows(tickers, start_date, end_date)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)

    if df.empty:
        print(f"Wrote 0 rows to {out_path} — no data returned for {start_date} to {end_date}.")
    else:
        print(f"Wrote {len(df)} rows to {out_path}")
        print(f"Date range: {df['date'].min().date()} to {df['date'].max().date()}")


if __name__ == "__main__":
    main()
