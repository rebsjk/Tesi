# Bloomberg field reference — Priority 1 & 2 pull

Confirmed field spec for the Bloomberg download plan agreed in
[data_inventory.md](../workflow_notes/data_inventory.md): the SPX
options-implied tail/skew series (Q-measure, Phase 5) and the SPX
index-level series (Phase 1 cross-check).

**Status: confirmed in terminal on 2026-07-02.** Every field below is
either a verified, non-blank mnemonic (with its actual start date
recorded where it matters) or explicitly documented as unavailable, with
the chosen proxy noted instead. This document is now the authoritative
spec — `bloomberg-extractor`'s download scripts should read mnemonics
from here, not carry their own guesses.

Scope note: this covers Priority 1 (irreplaceable — no CRSP/Compustat or
OptionMetrics substitute exists) and Priority 2 (cheap, do it the same
session) only. Priority 3 (membership/weight cross-check snapshots) isn't
a field-reference problem in the same way and isn't covered here.

## 1. SPX ATM implied volatility term structure

The base Q-measure vol-level input. Ticker: `SPX Index`.

| Concept | Proposed mnemonic | To be confirmed in terminal? | Notes |
|---|---|---|---|
| 30-day ATM implied vol | `30DAY_IMPVOL_100.0%MNY_DF` | Confirmed in terminal (2026-07-02); non-blank from 2006. | Core series. Together with 3-month below, these are the **only** true SPX ATM term-structure fields used in the core spec — 6M/12M are intentionally handled via VIX proxies instead of a direct SPX ATM field (see rows below). |
| 3-month ATM implied vol | `3MTH_IMPVOL_100.0%MNY_DF` | Confirmed in terminal (2026-07-02); non-blank from 2006. | Same family as 30-day. Together with 30-day above, these are the **only** true SPX ATM term-structure fields used in the core spec — 6M/12M are intentionally handled via VIX proxies instead of a direct SPX ATM field (see rows below). |
| 6-month ATM implied vol | `not available as single ATM field` | Confirmed unavailable in terminal (2026-07-02) — see Notes for proxy. | No clean SPX single-field 6M ATM volatility. Use `VIX6M Index PX_LAST` or, if needed, `6MO_CALL_IMP_VOL` / `6MO_PUT_IMP_VOL` as proxies, or drop this tenor from the baseline spec. |
| 12-month ATM implied vol | `not available as single ATM field` | Confirmed unavailable in terminal (2026-07-02) — see Notes for proxy. | No clean SPX single-field 12M ATM volatility. For longer tenors rely on `VIX3M` / `VIX6M` and other VIX-family indices rather than a direct SPX ATM field. |

## 2. SPX skew wings (fixed-delta put/call implied vol)

The actual risk-neutral skew/tail-asymmetry measure — this is the core Q-measure
input for the CSI comparison, not just a vol level. Ticker: `SPX Index`.

| Concept | Proposed mnemonic | To be confirmed in terminal? | Notes |
|---|---|---|---|
| 1M 10-delta put IV | `1M_PUT_IMP_VOL_10DELTA_DFLT` | Confirmed in terminal (2026-08-28); non-blank from 2006, BDP=16.9686 (2026-08-28 snapshot). | Deep-tail wing, added to sharpen the 1M smile's downside curvature. |
| 1M 25-delta put IV | `1M_PUT_IMP_VOL_25DELTA_DFLT` | Confirmed in terminal (2026-07-02); non-blank from 2006. | Used to construct the short-tenor skew/wing measures. |
| 1M 50-delta put IV | `1M_PUT_IMP_VOL_50DELTA_DFLT` | Confirmed in terminal (2026-08-28); non-blank from 2006, BDP=11.3114. | ATM-equivalent, put side — numerically identical to the 50-delta call at the same tenor in the 2026-08-28 snapshot. |
| 1M 10-delta call IV | `1M_CALL_IMP_VOL_10DELTA_DFLT` | Confirmed in terminal (2026-08-28); non-blank from 2006, BDP=9.9702. | Deep-tail wing, upside. |
| 1M 25-delta call IV | `1M_CALL_IMP_VOL_25DELTA_DFLT` | Confirmed in terminal (2026-07-02); non-blank from 2006. | Used to construct the short-tenor skew/wing measures. |
| 1M 50-delta call IV | `1M_CALL_IMP_VOL_50DELTA_DFLT` | Confirmed in terminal (2026-08-28); non-blank from 2006, BDP=11.3114. | ATM-equivalent, call side. |
| 2M 10-delta put IV | `2M_PUT_IMP_VOL_10DELTA_DFLT` | Confirmed in terminal (2026-08-28); non-blank from 2006, BDP=19.2419. | New tenor — no 2M field existed in this spec before 2026-08-28. |
| 2M 25-delta put IV | `2M_PUT_IMP_VOL_25DELTA_DFLT` | Confirmed in terminal (2026-08-28); non-blank from 2006, BDP=14.9526. | |
| 2M 40-delta put IV | `2M_PUT_IMP_VOL_40DELTA_DFLT` | Confirmed in terminal (2026-08-28); non-blank from 2006, BDP=13.1981. | |
| 2M 50-delta put IV | `2M_PUT_IMP_VOL_50DELTA_DFLT` | Confirmed in terminal (2026-08-28); non-blank from 2006, BDP=12.1849. | ATM-equivalent, 2M. |
| 2M 10-delta call IV | `2M_CALL_IMP_VOL_10DELTA_DFLT` | Confirmed in terminal (2026-08-28); non-blank from 2006, BDP=10.7006. | |
| 2M 25-delta call IV | `2M_CALL_IMP_VOL_25DELTA_DFLT` | Confirmed in terminal (2026-08-28); non-blank from 2006, BDP=11.1098. | |
| 2M 40-delta call IV | `2M_CALL_IMP_VOL_40DELTA_DFLT` | Confirmed in terminal (2026-08-28); non-blank from 2006, BDP=11.6621. | |
| 2M 50-delta call IV | `2M_CALL_IMP_VOL_50DELTA_DFLT` | Confirmed in terminal (2026-08-28); non-blank from 2006, BDP=12.1849. | Numerically identical to the 2M 50-delta put in the 2026-08-28 snapshot. |
| 2M 75-delta call IV | `2M_CALL_IMP_VOL_75DELTA_DFLT` | Confirmed resolves (2026-08-28), but **not pulled** — see Notes. | BDP=14.9526, numerically identical to `2M_PUT_IMP_VOL_25DELTA_DFLT` — same strike quoted from the call side, no new smile information. Excluded from `spx_skew_wings_download.py`'s `FIELDS`. |
| 2M 90-delta call IV | `2M_CALL_IMP_VOL_90DELTA_DFLT` | Confirmed resolves (2026-08-28), but **not pulled** — see Notes. | BDP=19.2419, numerically identical to `2M_PUT_IMP_VOL_10DELTA_DFLT`. Same reason as the 75-delta row above. |
| 3M ATM put IV | `3MO_PUT_IMP_VOL` | Confirmed in terminal (2026-07-02); non-blank from 2006. | Used to construct the short-tenor skew/wing measures. |

**Model suffix note (2026-08-28):** every mnemonic above uses the `_DFLT`
suffix (Bloomberg's default vol-surface model). FLDS also surfaces a
`_VG` (Vanna-Volga) variant of the same delta/tenor points — a different
surface-interpolation model, not a second independent data source. Stay
on `_DFLT` throughout this spec for internal consistency; don't mix `_VG`
points into the same smile without an explicit decision to do so.

**3M/6M delta-wing family: re-checked 2026-08-28, still doesn't exist.**
The original candidate list also included 25-delta calls and 10-delta puts
at the 3M and 6M tenors; those did not confirm cleanly against this
subscription in 2026-07-02, and an FLDS search on "imp vol" against `SPX
Index` on 2026-08-28 confirms why: the only delta-bucket families this
subscription actually exposes are 1M and 2M (10/25/40/50, plus redundant
75/90 call-side points at 2M) — there is no 3M/6M delta-wing family to
find, confirmed rather than assumed. 3M keeps its single ATM-put field
above; 6M has no wing or ATM single-field coverage at all (see section 1),
only the VIX6M proxy.

## 3. CBOE SKEW Index

An independent, literature-standard tail-risk benchmark — not derived from
your own skew construction in section 2, useful as a cross-check on it.
Ticker: `SKEW Index`.

| Concept | Proposed mnemonic | To be confirmed in terminal? | Notes |
|---|---|---|---|
| Daily SKEW index level | `PX_LAST` | Confirmed in terminal (2026-07-02); non-blank from 2006. | Daily close level of the CBOE SKEW Index; used as external tail-risk benchmark. |

## 4. VIX family

Implied-vol term-structure context and the input for a variance-risk-premium
construction (paired against CRSP-based realized variance on the P side —
never compute both P and Q pieces of VRP in the same script; see
[CLAUDE.md](../../CLAUDE.md)'s P/Q separation rule).

| Concept | Proposed mnemonic | To be confirmed in terminal? | Notes |
|---|---|---|---|
| Spot VIX | `VIX Index` → `PX_LAST` | Confirmed in terminal (2026-07-02); non-blank from 2006. | Used as 30D / 3M implied-volatility term-structure points. |
| 9-day VIX | `VIX9D Index` → `PX_LAST` | Confirmed in terminal (2026-07-02). | First non-blank observations in 2011; expect blanks before that. |
| 3-month VIX | `VIX3M Index` → `PX_LAST` | Confirmed in terminal (2026-07-02); non-blank from 2006. | Used as 30D / 3M implied-volatility term-structure points. |
| 6-month VIX | `VIX6M Index` → `PX_LAST` | Confirmed in terminal (2026-07-02). | First non-blank observations in 2008; expect blanks before that. Used as 6-month term-structure proxy rather than direct SPX ATM. |

## 5. SPX index price/return levels

Trivial footprint (single ticker, ~2 fields, ~5,000 daily rows each) — used
to validate the CRSP/Compustat-reconstructed cap-weighted return series
against the actual published index. Ticker: `SPX Index`.

| Concept | Proposed mnemonic | To be confirmed in terminal? | Notes |
|---|---|---|---|
| Daily close level | `PX_LAST` | Confirmed in terminal (2026-07-02); non-blank from 2006. | Headline S&P 500 price index close. |
| Total return index (gross dividends) | `TOT_RETURN_INDEX_GROSS_DVDS` | Confirmed in terminal (2026-07-02); non-blank from 2006. | RT116: SPX total return index with gross dividends; used as benchmark for reconstructed CRSP/Compustat-based returns. |

## Terminal confirmation checklist

**Status: completed 2026-07-02.** Every field in sections 1-5 above has
been checked against the live terminal as of this date, with the result
recorded directly in each table — 6M/12M SPX ATM (section 1) confirmed
unavailable and replaced by the documented VIX proxies, the section-2 skew
set narrowed to the three fields that actually confirmed, and every
remaining field marked with its actual start date where that start date is
later than 2006. Treat this document as the authoritative spec: `src/bloomberg/*_download.py`
scripts should read mnemonics from here, and any `FIELDS` dict that still
carries the old placeholder/candidate values (in particular the wider
7-field section-2 list) should be updated to match this file rather than
the reverse.

For any future re-check — a new field being added to the spec, a
subscription change, or a periodic revalidation — repeat this procedure:

1. **Find the real mnemonics first.** Open `SPX Index` in the terminal,
   go to `OVDV` (or the equivalent implied-vol/derivatives screen), and use
   `FLDS` to search "implied vol" and "delta" for the concept you're
   trying to add. This is the process that was used to confirm the fields
   currently in this document — reuse it for any new field before adding
   it to the spec.
2. **Confirm each field resolves at all.** Pull a single recent value
   (`BDP` or a 30-day `BDH`) and confirm it returns non-blank data before
   spending quota on full history.
3. **Find each field's actual start date, don't assume 2006.** `BDH` a
   short window at the start of your intended range (2006-01-01 to
   2006-01-31). If blank, bisect forward (try 2008, then 2010, then
   2012...) until you find the first date with data, and record that in
   the Notes column — this is exactly how the 2011/2008 start dates for
   VIX9D/VIX6M above were established.
4. **Confirm the ticker resolves**, the same way as step 2, before
   assuming a whole family (e.g. the rest of the VIX family) is available
   just because one member is.
5. **Only after a field is confirmed**, include it in a full historical
   pull — chunk by field group and year range rather than one large
   request, per the download-limit constraints already noted in
   [data_inventory.md](../workflow_notes/data_inventory.md).
6. **Update this document first, then the extraction scripts.** This file
   is the spec `bloomberg-extractor` reads from — a script's `FIELDS` dict
   should never diverge from what's recorded here.
