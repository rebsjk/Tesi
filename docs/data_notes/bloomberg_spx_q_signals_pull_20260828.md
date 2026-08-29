# Bloomberg SPX Q-signal pull — 2026-08-28

Phase-5 raw pull, index-level scope (`bloomberg-extractor` work done
interactively over several turns 2026-08-28/29, on a separate machine with
Bloomberg Terminal access that has since ended — see
`docs/workflow_notes/data_inventory.md` for the scope decision this note
assumes). Raw only, plus the source-cleaning step — does not build the
Phase-5 Q-measure econometrics itself, which per `CLAUDE.md`'s priority
build order comes after Phase 4.

## Scope decision (2026-08-29): index-level only

Everything pulled here is SPX-index-level. Constituent-level option
underlyings were explicitly ruled out of current scope when confirming
before Bloomberg access ended — see `data_inventory.md`'s "Open decision
blocking pull scope." If that scope changes later, a fresh Bloomberg
session and a new extraction pass would be needed for single-name option
data; nothing here covers it.

## What was pulled, and the 2005-01 start-date correction

Three files, all re-pulled 2026-08-28 with `--start 2005-01-01`:

| File | Content | Rows |
|---|---|---|
| `bloomberg_spx_iv_term_structure_20260828.csv` | SPX ATM IV, 30D + 3M | 5,447 |
| `bloomberg_spx_skew_wings_20260828.csv` | 1M 10/25/50-delta put+call, 2M 10/25/40/50-delta put+call, 3M ATM put (15 columns) | 5,447 |
| `bloomberg_vol_indexes_20260828.csv` | VIX, VIX9D, VIX3M, VIX6M, CBOE SKEW | 5,480 |

**All three genuinely start 2005-01-03 with real (non-null) values**,
correcting the originally-documented "2006" start, which was never a
verified true start date — only the date the original 2026-07-02
confirmation check happened to begin from. `check_skew_wings_pre2006_coverage.py`
tested Jan 2000 through Jan 2005 and found a uniform cutover: blank
2000-2004, non-blank from 2005-01 across all 15 skew-wing fields; the same
re-pull confirmed the ATM term structure and (mostly) the VIX family also
start genuinely in 2005, not 2006. See
`docs/data_notes/bloomberg_field_reference.md` for the full per-field
confirmation record. 2000-2004 is confirmed blank, not merely untested —
don't re-attempt pulling that range.

## Known gaps (diagnosed, not errors)

1. **1M skew-wing family, 4 consecutive nulls: 2005-12-12 to 2005-12-15.**
   All six 1M columns (put/call × 10D/25D/50D) blank on exactly these four
   trading days; the 2M columns and 3M ATM put are unaffected. A vendor-
   side gap in that specific week, not a pull error — `_check_known_1m_wing_gap`
   in `src/bloomberg/clean_spx_q_signals.py` re-verifies this is still the
   case on every cleaning run.
2. **VIX9D / VIX6M: structural leading nulls** before their real start
   (~2011 / ~2008 respectively) — already documented in
   `bloomberg_field_reference.md` section 4, unchanged by this pull.
3. **VIX3M / SKEW: null on US market-holiday dates.** `VIX Index`'s own
   calendar includes rows on holidays (Memorial Day, Juneteenth, July 4th,
   Labor Day, Thanksgiving, MLK Day, Presidents Day, and the 2025-01-09
   national day of mourning) where `vix3m`/`skew` are blank but `vix`
   itself is often populated. `SPX Index` (the source for the other two
   files) produces no row at all on these dates — see the merge-strategy
   note below.

## Cleaning (`src/bloomberg/clean_spx_q_signals.py`, run 2026-08-29)

Per-source cleaning (date parsing, sort, duplicate-date check, numeric
coercion, null-count logging — no imputation) writes to
`data_interim/bloomberg/`:
- `bloomberg_spx_iv_term_structure_clean_20260829.csv`
- `bloomberg_spx_skew_wings_clean_20260829.csv`
- `bloomberg_vol_indexes_clean_20260829.csv`

**Merge strategy: inner join on date**, not outer — deliberate, not the
default fallen into. `vol_indexes` contributes 33 calendar rows (the
holiday dates from gap #3 above) that the two SPX-Index-sourced files
never produce a row for; an inner join drops exactly those, aligning the
merged panel to the SPX options-market trading calendar that every other
column is actually observed on, rather than carrying 33 rows that would
be all-NaN outside of `vix`. Written to `data_interim/options/`:
- `spx_q_signals_daily_clean_20260829.csv` — 5,447 rows, 2005-01-03 to
  2026-08-27, one row per SPX-options trading day, 21 value columns (2
  ATM + 15 skew-wing + 4 VIX-family/SKEW).

Full run log: `outputs/logs/clean_spx_q_signals_20260829.txt`.

## What this does not do

Does not build any Phase-5 Q-measure (smile fitting, moment extraction,
CSI conditioning) — this is source-cleaning and the first cross-source
merge only, per `CLAUDE.md`'s `data_interim/options/` description
("Cleaned option chains before tail-measure extraction"). Phase 5 itself
starts after Phase 4 completes, per the priority build order.

Cross-references: `docs/data_notes/bloomberg_field_reference.md` (full
field confirmation record), `docs/workflow_notes/data_inventory.md`
(Phase-5 status and the index-level-only scope decision).
