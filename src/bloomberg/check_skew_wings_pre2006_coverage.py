"""One-off check: does SPX skew-wing coverage go back to 2000 (matching the
CRSP universe panel's 2000-01-03 start), or only as far back as 2006 (the
date every skew-wing field in bloomberg_field_reference.md happens to have
been first checked from, not a verified true start date)?

Not a pipeline script. Reproduces the same BDH-bisection discipline
bloomberg_field_reference.md's checklist already prescribes for finding a
field's real start date ("don't assume 2006 ... if blank, bisect forward"),
just applied in the direction nobody has actually tried yet: backward from
2006 toward 2000, the earliest date the physical-side panel could ever use
regardless of what Bloomberg has further back.

For each field: test a short window at 2000-01, and if blank, bisect
forward one year at a time (2001, 2002, ..., 2005) until a non-blank window
is found or 2006 is reached (already confirmed non-blank there for every
field in this list).

Usage:
    python -m src.bloomberg.check_skew_wings_pre2006_coverage
"""

from __future__ import annotations

try:
    from xbbg import blp

    BLOOMBERG_AVAILABLE = True
except ImportError:
    blp = None
    BLOOMBERG_AVAILABLE = False

TICKER = "SPX Index"

# The full skew-wing set currently in spx_skew_wings_download.py's FIELDS
# (3 original, confirmed non-blank from 2006-01, plus the 12 added
# 2026-08-28, also confirmed non-blank from 2006-01 — but "from 2006-01" is
# as far back as anyone tested, not necessarily the true start).
FIELDS: dict[str, str] = {
    "iv_1m_put_10d": "1M_PUT_IMP_VOL_10DELTA_DFLT",
    "iv_1m_put_25d": "1M_PUT_IMP_VOL_25DELTA_DFLT",
    "iv_1m_put_50d": "1M_PUT_IMP_VOL_50DELTA_DFLT",
    "iv_1m_call_10d": "1M_CALL_IMP_VOL_10DELTA_DFLT",
    "iv_1m_call_25d": "1M_CALL_IMP_VOL_25DELTA_DFLT",
    "iv_1m_call_50d": "1M_CALL_IMP_VOL_50DELTA_DFLT",
    "iv_2m_put_10d": "2M_PUT_IMP_VOL_10DELTA_DFLT",
    "iv_2m_put_25d": "2M_PUT_IMP_VOL_25DELTA_DFLT",
    "iv_2m_put_40d": "2M_PUT_IMP_VOL_40DELTA_DFLT",
    "iv_2m_put_50d": "2M_PUT_IMP_VOL_50DELTA_DFLT",
    "iv_2m_call_10d": "2M_CALL_IMP_VOL_10DELTA_DFLT",
    "iv_2m_call_25d": "2M_CALL_IMP_VOL_25DELTA_DFLT",
    "iv_2m_call_40d": "2M_CALL_IMP_VOL_40DELTA_DFLT",
    "iv_2m_call_50d": "2M_CALL_IMP_VOL_50DELTA_DFLT",
    "iv_3m_atm_put": "3MO_PUT_IMP_VOL",
}

# Bisection years to try, in order, starting from the CRSP panel's own
# start year. 2006 is deliberately not included here — it's already
# confirmed non-blank for every field above, so it's the fallback if 2000
# through 2005 are all blank, not something this script needs to re-check.
CANDIDATE_YEARS = [2000, 2001, 2002, 2003, 2004, 2005]


def _window_has_data(mnemonic: str, year: int) -> bool:
    df = blp.bdh(
        tickers=TICKER,
        flds=mnemonic,
        start_date=f"{year}-01-01",
        end_date=f"{year}-01-31",
        backend="pandas",
    )
    if not hasattr(df, "empty") and hasattr(df, "to_pandas"):
        df = df.to_pandas()
    return not df.empty


def find_earliest_year(mnemonic: str) -> object:
    """Return the earliest candidate year with non-blank Jan data, or
    "2006+ (all of 2000-2005 blank)" if none of them have data, or an
    error string if a request itself fails."""
    try:
        for year in CANDIDATE_YEARS:
            if _window_has_data(mnemonic, year):
                return year
        return "2006+ (all of 2000-2005 blank)"
    except Exception as exc:  # noqa: BLE001
        return f"ERROR: {exc!r}"


def main() -> None:
    if not BLOOMBERG_AVAILABLE:
        raise RuntimeError(
            "xbbg is not installed, or no Bloomberg Desktop API session is "
            "available. Install xbbg and run this from a machine with an "
            "active Bloomberg Terminal session to actually run this check."
        )

    print(f"=== Earliest non-blank January among {CANDIDATE_YEARS} — {TICKER} ===")
    for name, mnemonic in FIELDS.items():
        result = find_earliest_year(mnemonic)
        print(f"{name:16s} ({mnemonic:30s}) -> {result}")


if __name__ == "__main__":
    main()
