"""Pull S&P 500 Equal Weight and S&P 500 Top 10 benchmark levels (Priority 2).

These two benchmarks are concentration-sensitive by construction — the
Equal Weight index removes cap-weighting entirely, and the Top 10 index is
the mirror-image concentrated portfolio — so together they act as a
cheap, published cross-check on the CSI's own concentration read, the same
role spx_index_download.py plays for the plain cap-weighted SPX level.

Confirmed field source: tickers resolved and confirmed in terminal
2026-07-02 via `blp.bdp()` (name + PX_LAST) and a short 2006-01/2006-02
`blp.bdh()` window (all four non-blank from 2006-01-03), following the
same terminal-confirmation procedure as
docs/data_notes/bloomberg_field_reference.md.

| Concept | Ticker | Bloomberg name (confirmed) |
|---|---|---|
| S&P 500 Equal Weight, price | `SPW Index` | S&P 500 Equal Weighted Index |
| S&P 500 Equal Weight, total return | `SPXEWTR Index` | S&P 500 Equal Weighted USD Tot[al Return] |
| S&P 500 Top 10, price | `SP5T1 Index` | S&P 500 Top 10 Index (USD) |
| S&P 500 Top 10, total return | `SP5T1T Index` | S&P 500 Top 10 Index (USD) TR |

`SP5T1`/`SP5T1T` were found via `blp.blkp("S&P 500 Top 10", yellowkey="YK_FILTER_INDX")`
security search — there is no single obvious mnemonic to guess for this
one, unlike the equal-weight ticker. If a different S&P DJI top-N variant
is needed later (Top 20/50, capped, decrement, net-of-tax...), re-run that
same `blkp` search rather than guessing a ticker by pattern.
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
# Source: this module's docstring — confirmed in terminal 2026-07-02;
# all four fields non-blank from 2006-01-03.
FIELDS: dict[str, tuple[str, str]] = {
    "spx_eqw_price": ("SPW Index", "PX_LAST"),
    "spx_eqw_tr": ("SPXEWTR Index", "PX_LAST"),
    "spx_top10_price": ("SP5T1 Index", "PX_LAST"),
    "spx_top10_tr": ("SP5T1T Index", "PX_LAST"),
}

CONTENT_SLUG = "spx_benchmarks"


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
