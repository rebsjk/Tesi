"""Pull the SPX short-tenor skew wings — the risk-neutral tail measure (Priority 1).

Confirmed field source: docs/data_notes/bloomberg_field_reference.md,
section 2 ("SPX skew wings (fixed-delta put/call implied vol)"), confirmed
in terminal 2026-07-02 (1M 25D wings, 3M ATM put) and extended 2026-08-28
(1M 10D/50D wings, full 2M delta grid). This is the core Q-measure
skew/tail-asymmetry input for the CSI comparison, not just a vol level —
treat it with the same priority as the ATM term structure pull.

3M/6M 25-delta calls and 10-delta puts still do not confirm on this
subscription (checked both 2026-07-02 and again 2026-08-28) — no 3M/6M
delta-wing family exists here, only the single 3M ATM put field already in
this spec. The delta grid that does exist is 10/25/40/50(/75/90 call-side)
across exactly two tenors, 1M and 2M — see bloomberg_field_reference.md
section 2 for the full confirmation record.

2M_CALL_IMP_VOL_75DELTA_DFLT and 2M_CALL_IMP_VOL_90DELTA_DFLT are
deliberately NOT included below: confirmed empirically (2026-08-28) to be
numerically identical to 2M_PUT_IMP_VOL_25DELTA_DFLT and
2M_PUT_IMP_VOL_10DELTA_DFLT respectively (same strike, quoted from the
call side instead of the put side) — pulling them would duplicate data
already in this FIELDS dict, not add smile information.
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
# Source: docs/data_notes/bloomberg_field_reference.md, section 2.
# Original three (confirmed 2026-07-02, non-blank from 2006) plus the
# extended 1M/2M delta grid (confirmed 2026-08-28, non-blank from 2006 via
# BDH, real differentiated BDP values, not the degenerate-constant pattern
# seen on the unrelated official-index-weight fields). All mnemonics use
# the "_DFLT" model suffix (Bloomberg's default surface model) for
# consistency with the original three fields — do not mix in a "_VG"
# (Vanna-Volga) variant for any of these without an explicit decision to
# do so, see bloomberg_field_reference.md.
# Do not add back 3M/6M 25-delta calls or 10-delta puts, or the redundant
# 2M 75D/90D call fields — see module docstring.
FIELDS: dict[str, tuple[str, str]] = {
    "iv_1m_put_10d": ("SPX Index", "1M_PUT_IMP_VOL_10DELTA_DFLT"),
    "iv_1m_put_25d": ("SPX Index", "1M_PUT_IMP_VOL_25DELTA_DFLT"),
    "iv_1m_put_50d": ("SPX Index", "1M_PUT_IMP_VOL_50DELTA_DFLT"),
    "iv_1m_call_10d": ("SPX Index", "1M_CALL_IMP_VOL_10DELTA_DFLT"),
    "iv_1m_call_25d": ("SPX Index", "1M_CALL_IMP_VOL_25DELTA_DFLT"),
    "iv_1m_call_50d": ("SPX Index", "1M_CALL_IMP_VOL_50DELTA_DFLT"),
    "iv_2m_put_10d": ("SPX Index", "2M_PUT_IMP_VOL_10DELTA_DFLT"),
    "iv_2m_put_25d": ("SPX Index", "2M_PUT_IMP_VOL_25DELTA_DFLT"),
    "iv_2m_put_40d": ("SPX Index", "2M_PUT_IMP_VOL_40DELTA_DFLT"),
    "iv_2m_put_50d": ("SPX Index", "2M_PUT_IMP_VOL_50DELTA_DFLT"),
    "iv_2m_call_10d": ("SPX Index", "2M_CALL_IMP_VOL_10DELTA_DFLT"),
    "iv_2m_call_25d": ("SPX Index", "2M_CALL_IMP_VOL_25DELTA_DFLT"),
    "iv_2m_call_40d": ("SPX Index", "2M_CALL_IMP_VOL_40DELTA_DFLT"),
    "iv_2m_call_50d": ("SPX Index", "2M_CALL_IMP_VOL_50DELTA_DFLT"),
    "iv_3m_atm_put": ("SPX Index", "3MO_PUT_IMP_VOL"),
}

CONTENT_SLUG = "spx_skew_wings"


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
