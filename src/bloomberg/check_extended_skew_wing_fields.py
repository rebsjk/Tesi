"""One-off field-availability check for candidate SPX skew-wing mnemonics
NOT yet confirmed in docs/data_notes/bloomberg_field_reference.md.

Not a pipeline script — run this interactively in a terminal with an active
Bloomberg session, read the printed result, then report back which
mnemonics came back non-blank. Once confirmed, those get added to
src/bloomberg/spx_skew_wings_download.py's FIELDS dict (or a new sibling
script) following bloomberg_field_reference.md's documented pattern.

Checklist reproduced (bloomberg_field_reference.md, steps 2-3):
  1. BDP: does the field resolve at all right now (single recent value)?
  2. BDH over a short 2006-01 window: does it have data at the start of the
     sample, or does it need bisecting forward for a later start date?

Usage:
    python -m src.bloomberg.check_extended_skew_wing_fields
"""

from __future__ import annotations

try:
    from xbbg import blp

    BLOOMBERG_AVAILABLE = True
except ImportError:
    blp = None
    BLOOMBERG_AVAILABLE = False

TICKER = "SPX Index"

# Candidate mnemonics from an actual FLDS search on "imp vol" against SPX
# Index (2026-08-28) — all 14 non-ATM candidates below were present in that
# search result; the earlier blind 5D/15D/35D/3M-wing guesses were not, and
# stay dropped. The real available delta grid on this subscription is
# 10/25/40/50(/75/90 call-side) across two tenors, 1M and 2M — no 3M wing
# family exists (3M only has the single ATM field already confirmed).
#
# Naming format (corrected 2026-08-28, no underscore before "DELTA" —
# matches the already-confirmed 1M-25-delta fields in
# bloomberg_field_reference.md exactly, e.g. "1M_PUT_IMP_VOL_25DELTA_DFLT",
# "2M_PUT_IMP_VOL_50DELTA_DFLT"). An earlier version of this file briefly
# had an underscore before DELTA — that was wrong, reverted.
# Every mnemonic below is still model-suffix "_DFLT" (Bloomberg's default
# surface model), not "_VG" (Vanna-Volga) — kept consistent with the
# already-confirmed 25-delta fields, which are also _DFLT. Don't substitute
# a _VG variant for any of these without an explicit decision to do so.
#
# Deliberately excluded: "HIST_CALL_IMP_VOL" — ambiguous name (could be a
# realized/historical series mislabeled, not necessarily risk-neutral).
# Don't add it as a Q-side candidate until its actual definition is checked
# directly in the terminal (FLDS description / DES page), per CLAUDE.md's
# P/Q separation rule.
CANDIDATES: dict[str, str] = {
    # 1-month: 25D put/call already confirmed (bloomberg_field_reference.md).
    # These fill in the rest of the FLDS-confirmed 1M delta grid.
    "1m_put_10d": "1M_PUT_IMP_VOL_10DELTA_DFLT",
    "1m_put_50d": "1M_PUT_IMP_VOL_50DELTA_DFLT",
    "1m_call_10d": "1M_CALL_IMP_VOL_10DELTA_DFLT",
    "1m_call_50d": "1M_CALL_IMP_VOL_50DELTA_DFLT",
    # 2-month: entirely new tenor, none of this confirmed yet. Full grid
    # from the FLDS search: put 10/25/40/50, call 10/25/40/50/75/90.
    "2m_put_10d": "2M_PUT_IMP_VOL_10DELTA_DFLT",
    "2m_put_25d": "2M_PUT_IMP_VOL_25DELTA_DFLT",
    "2m_put_40d": "2M_PUT_IMP_VOL_40DELTA_DFLT",
    "2m_put_50d": "2M_PUT_IMP_VOL_50DELTA_DFLT",
    "2m_call_10d": "2M_CALL_IMP_VOL_10DELTA_DFLT",
    "2m_call_25d": "2M_CALL_IMP_VOL_25DELTA_DFLT",
    "2m_call_40d": "2M_CALL_IMP_VOL_40DELTA_DFLT",
    "2m_call_50d": "2M_CALL_IMP_VOL_50DELTA_DFLT",
    "2m_call_75d": "2M_CALL_IMP_VOL_75DELTA_DFLT",
    "2m_call_90d": "2M_CALL_IMP_VOL_90DELTA_DFLT",
}


def check_bdp() -> dict[str, object]:
    """Single current value per candidate — confirms the field resolves at all."""
    results: dict[str, object] = {}
    for name, mnemonic in CANDIDATES.items():
        try:
            df = blp.bdp(tickers=TICKER, flds=mnemonic, backend="pandas")
            if not hasattr(df, "empty") and hasattr(df, "to_pandas"):
                df = df.to_pandas()
            val = df.iloc[0].get(mnemonic.lower(), df.iloc[0].get(mnemonic)) if not df.empty else None
            results[name] = val
        except Exception as exc:  # noqa: BLE001 - want to see every field's own error
            results[name] = f"ERROR: {exc!r}"
    return results


def check_bdh_2006() -> dict[str, object]:
    """Short BDH window at the start of the sample (Jan 2006) — matches how
    every other confirmed field's start date was established."""
    results: dict[str, object] = {}
    for name, mnemonic in CANDIDATES.items():
        try:
            df = blp.bdh(
                tickers=TICKER,
                flds=mnemonic,
                start_date="2006-01-01",
                end_date="2006-01-31",
                backend="pandas",
            )
            if not hasattr(df, "empty") and hasattr(df, "to_pandas"):
                df = df.to_pandas()
            results[name] = "non-blank" if not df.empty else "blank/no rows"
        except Exception as exc:  # noqa: BLE001
            results[name] = f"ERROR: {exc!r}"
    return results


def main() -> None:
    if not BLOOMBERG_AVAILABLE:
        raise RuntimeError(
            "xbbg is not installed, or no Bloomberg Desktop API session is "
            "available. Install xbbg and run this from a machine with an "
            "active Bloomberg Terminal session to actually run this check."
        )

    print(f"=== BDP (current value) check — {TICKER} ===")
    for name, val in check_bdp().items():
        print(f"{name:16s} ({CANDIDATES[name]:35s}) -> {val!r}")

    print(f"\n=== BDH (Jan 2006 window) check — {TICKER} ===")
    for name, val in check_bdh_2006().items():
        print(f"{name:16s} ({CANDIDATES[name]:35s}) -> {val!r}")


if __name__ == "__main__":
    main()
