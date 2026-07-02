"""Pull the SPX short-tenor skew wings — the risk-neutral tail measure (Priority 1).

Confirmed field source: docs/data_notes/bloomberg_field_reference.md,
section 2 ("SPX skew wings (fixed-delta put/call implied vol)"), confirmed
in terminal 2026-07-02. This is the core Q-measure skew/tail-asymmetry
input for the CSI comparison, not just a vol level — treat it with the
same priority as the ATM term structure pull.

The confirmed spec is exactly three series: the 1M 25-delta put/call wings
plus the 3M ATM put. The wider candidate set originally considered here
(3M/6M 25-delta calls, 3M/6M 10-delta puts) did not confirm cleanly
against this subscription and has been dropped from the baseline spec —
see bloomberg_field_reference.md's terminal confirmation checklist if a
wider skew set needs to be re-verified and added back later.
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
# Source: docs/data_notes/bloomberg_field_reference.md, section 2 —
# confirmed in terminal 2026-07-02; all three fields non-blank from 2006.
# This is the full confirmed set — do not add back 3M/6M 25-delta calls or
# 10-delta puts without re-running the terminal confirmation checklist in
# bloomberg_field_reference.md first, they did not confirm on this
# subscription.
FIELDS: dict[str, tuple[str, str]] = {
    "iv_1m_put_25d": ("SPX Index", "1M_PUT_IMP_VOL_25DELTA_DFLT"),
    "iv_1m_call_25d": ("SPX Index", "1M_CALL_IMP_VOL_25DELTA_DFLT"),
    "iv_3m_atm_put": ("SPX Index", "3MO_PUT_IMP_VOL"),
}

CONTENT_SLUG = "spx_skew_wings"


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
