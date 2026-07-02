"""Pull SPX index price/return levels — the Phase-1 cross-check series (Priority 2).

Confirmed field source: docs/data_notes/bloomberg_field_reference.md,
section 5 ("SPX index price/return levels"). Trivial footprint (single
ticker, two fields, ~5,000 daily rows each over 2006-2026) — used to
validate the CRSP/Compustat-reconstructed cap-weighted return series
against the actual published index, not as a primary data source for any
phase. PX_LAST itself is a standard field and essentially guaranteed to
work; TOT_RETURN_INDEX_GROSS_DVDS is the one mnemonic here that actually
needs confirming — total-return index field naming varies, and if it's
wrong a dividend-yield field can be pulled separately as a fallback to
reconstruct total return manually.
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
# Source: docs/data_notes/bloomberg_field_reference.md, section 5.
FIELDS: dict[str, tuple[str, str]] = {
    "px_last": ("SPX Index", "PX_LAST"),  # standard field, low risk
    "total_return_index": ("SPX Index", "TOT_RETURN_INDEX_GROSS_DVDS"),  # TODO: confirm exact mnemonic
}

CONTENT_SLUG = "spx_index_levels"


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
    )

    flat = pd.DataFrame(index=raw.index)
    for concept, (ticker, mnemonic) in fields.items():
        flat[concept] = raw[(ticker, mnemonic)]
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
