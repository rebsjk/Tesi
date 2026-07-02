"""Pull VIX, VIX9D, VIX3M, VIX6M, and the CBOE SKEW Index (Priority 1).

Confirmed field source: docs/data_notes/bloomberg_field_reference.md,
sections 3 ("CBOE SKEW Index") and 4 ("VIX family"). These are independent
benchmarks against the thesis's own skew/tail construction from
spx_skew_wings_download.py — VIX-family series also feed a variance-risk-
premium construction on the Q side (never combine that with the CRSP-based
realized-variance leg in this file; that pairing happens in
src/integration/, per CLAUDE.md's P/Q separation rule).

Every ticker below is a proposed candidate, not confirmed to resolve on
this subscription — work through the terminal checklist in
bloomberg_field_reference.md first. VIX9D/VIX3M/VIX6M in particular have
shorter live history than the 2006 start of this thesis's window (VIX9D
from ~2011, VIX3M/VIX6M from ~2007-08) — leading blanks for those tickers
are expected, not a pull error.
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


# concept name -> (Bloomberg ticker, Bloomberg field mnemonic).
# Source: docs/data_notes/bloomberg_field_reference.md, sections 3-4.
# PX_LAST itself is a standard field and low risk; what needs confirming
# here is that each TICKER resolves on this subscription and its actual
# start date (see the caveats in the module docstring above).
FIELDS: dict[str, tuple[str, str]] = {
    "vix": ("VIX Index", "PX_LAST"),  # TODO: confirm ticker resolves
    "vix9d": ("VIX9D Index", "PX_LAST"),  # TODO: confirm ticker + start date (~2011)
    "vix3m": ("VIX3M Index", "PX_LAST"),  # TODO: confirm ticker + start date (~2007-08)
    "vix6m": ("VIX6M Index", "PX_LAST"),  # TODO: confirm ticker + start date (~2007-08)
    "skew": ("SKEW Index", "PX_LAST"),  # TODO: confirm ticker resolves
}

CONTENT_SLUG = "vol_indexes"


def _bdh_to_wide(raw: object) -> pd.DataFrame:
    """Normalize a blp.bdh() result into a wide frame: DatetimeIndex named
    "date", (ticker, field) MultiIndex columns.

    xbbg >=1.x (the installed version here is 1.4.1) rewrote bdh() around a
    pluggable backend. Without an explicit `backend=`, it can hand back a
    narwhals-wrapped frame whose `type(...).__name__` is still literally
    "DataFrame" — which is what produced the misleading
    "'DataFrame' object has no attribute 'index'" error, since narwhals
    frames don't expose a pandas-style .index. Even with backend="pandas"
    forced at the call site, the *shape* has also changed: bdh() now
    defaults to long format (columns ticker/date/field/value, values as
    strings) instead of the old wide format (DatetimeIndex + MultiIndex
    (ticker, field) columns). This function accepts either shape so the
    rest of the script doesn't care which xbbg version produced `raw`.
    """
    if not isinstance(raw, pd.DataFrame):
        if hasattr(raw, "to_pandas"):
            raw = raw.to_pandas()
        elif hasattr(raw, "to_native"):
            raw = raw.to_native()
            if not isinstance(raw, pd.DataFrame) and hasattr(raw, "to_pandas"):
                raw = raw.to_pandas()
    if not isinstance(raw, pd.DataFrame):
        raise TypeError(
            f"blp.bdh() returned an unsupported type {type(raw)!r} that "
            "could not be converted to a pandas DataFrame."
        )

    if isinstance(raw.columns, pd.MultiIndex):
        # Old-style xbbg: already wide, just normalize the index dtype.
        wide = raw.copy()
        wide.index = pd.to_datetime(wide.index)
        wide.index.name = "date"
        return wide

    if {"ticker", "date", "field", "value"}.issubset(raw.columns):
        # New-style xbbg (>=1.x): long format, one row per (ticker, date, field).
        long_df = raw.copy()
        long_df["date"] = pd.to_datetime(long_df["date"])
        long_df["value"] = pd.to_numeric(long_df["value"], errors="coerce")
        wide = long_df.pivot(index="date", columns=["ticker", "field"], values="value")
        wide = wide.sort_index()
        wide.index.name = "date"
        return wide

    raise TypeError(f"Unrecognized blp.bdh() result shape: columns={list(raw.columns)!r}")


def fetch_history(
    fields: dict[str, tuple[str, str]], start_date: date, end_date: date
) -> pd.DataFrame:
    """Pull daily BDH history for every (ticker, mnemonic) pair in `fields`.

    Returns a flat DataFrame: DatetimeIndex named "date", one column per
    concept name. Raises RuntimeError if xbbg/Bloomberg Desktop API isn't
    available — only called from main(), so importing this module never
    requires Bloomberg to be installed.
    """
    if not BLOOMBERG_AVAILABLE:
        raise RuntimeError(
            "xbbg is not installed, or no Bloomberg Desktop API session is "
            "available. Install xbbg and run this from a machine with an "
            "active Bloomberg Terminal session to actually pull data."
        )

    tickers = sorted({ticker for ticker, _ in fields.values()})
    mnemonics = sorted({mnemonic for _, mnemonic in fields.values()})

    raw = blp.bdh(
        tickers=tickers,
        flds=mnemonics,
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        backend="pandas",
    )
    wide = _bdh_to_wide(raw)

    flat = pd.DataFrame(index=wide.index)
    for concept, (ticker, mnemonic) in fields.items():
        if (ticker, mnemonic) in wide.columns:
            flat[concept] = wide[(ticker, mnemonic)]
        else:
            flat[concept] = pd.Series(dtype="float64", index=wide.index)
    flat.index.name = "date"
    return flat


def default_output_path(as_of: date | None = None) -> Path:
    as_of = as_of or datetime.now(timezone.utc).date()
    BLOOMBERG_RAW.mkdir(parents=True, exist_ok=True)
    return BLOOMBERG_RAW / f"bloomberg_{CONTENT_SLUG}_{as_of:%Y%m%d}.csv"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=date.fromisoformat, default=None)
    parser.add_argument("--end", type=date.fromisoformat, default=None)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    end_date = args.end or datetime.now(timezone.utc).date()
    start_date = args.start or (end_date - timedelta(days=30))
    out_path = args.out or default_output_path()

    df = fetch_history(FIELDS, start_date, end_date)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path)

    if df.empty:
        print(f"Wrote 0 rows to {out_path} — no data returned for {start_date} to {end_date}.")
    else:
        print(f"Wrote {len(df)} rows to {out_path}")
        print(f"Date range: {pd.Timestamp(df.index.min()).date()} to {pd.Timestamp(df.index.max()).date()}")


if __name__ == "__main__":
    main()
