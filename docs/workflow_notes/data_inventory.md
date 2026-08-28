# Data inventory

The single checklist tying required datasets to the six build phases in
[CLAUDE.md](../../CLAUDE.md). No pull happens without a row here first —
if a phase needs a dataset not listed below, add it here before writing
extraction code, so `data_raw/` provenance and the P/Q boundary stay
auditable. Field/table names below are candidates to confirm against the
actual Bloomberg/WRDS/OptionMetrics subscription in use — mark each row
confirmed once verified, don't assume the mnemonic is exactly right.

Status legend: **blocking** = phase cannot start without it · **needed** =
required before the phase is complete, doesn't block starting · **optional**
= only if a specific design choice is taken · **deferred** = phase 6 or later.

## (a) Universe construction — Phase 1

| Dataset | Source | Table / fields (candidate) | Purpose | Status |
|---|---|---|---|---|
| Index membership | `data_raw/crsp` | `crsp_m_indexes.dsp500list_v2` (`permno, mbrstartdt, mbrenddt`) — pulled 2026-08-19, see [crsp_sp500_raw_pull_20260819.md](../data_notes/crsp_sp500_raw_pull_20260819.md) | Defines the constituent set for the phase-1 point-in-time panel; source changed from the originally planned Bloomberg pull per the 2026-07-05 session decision | **done** |
| Constituent weight | `data_raw/crsp` | Self-computed from `dsf_v2.dlycap`, not a published index-weight field — see [index_weight_construction.md](../methodology_notes/index_weight_construction.md) | Capital weight input to HHI/CR-k/effective-N/entropy | **done** |
| CRSP Daily Stock File | `data_raw/crsp` | `dsf_v2` (`permno, dlycaldt, dlyret, dlyprc, shrout, dlycap`, + `sharetype`/`primaryexch` for the filter below) | Realized return series — used here and reused in Phase 4 | **done** |
| CRSP Delisting file | `data_raw/crsp` | `stkdelists` (`permno, delistingdt, delret, ...`) | Delisting-adjusted returns; omitting this biases realized risk downward exactly at index-exit events, which matter for a concentration/systemic-risk thesis | **done** — 459/462 events with a valid `delret` compounded into the last observation in `src/crsp/clean_sp500_raw.py`; 3 permnos (11786, 83630, 90090) had a missing `delret` and were left unadjusted, logged, not imputed |
| CRSP Names/Header file | `data_raw/crsp` | `stocknames_v2` (`permno, permco`, CUSIP/ticker history) | Identifier history — retained for a future crosswalk if one is ever needed (e.g. GICS join), not currently consumed by the Phase 1 build | **done** (pulled, not yet used) |
| Share type / exchange filter | `data_interim/crsp` | `sharetype='NS'`, `primaryexch in {N,Q,A}` — decided 2026-08-19 | Restricts the daily panel to ordinary common shares on a major exchange, matching CRSP legacy `shrcd IN (10,11)` | **done** — applied in `src/crsp/clean_sp500_raw.py`. Pre-filter: 5,019,232 rows / 1,117 permnos. Post-filter: 4,956,942 rows / 1,108 permnos. Dropped by `sharetype`: SB 34,920, UG 11,795, AD 1,480 (+13,628 `NS` rows dropped on the exchange leg of the filter). Dropped by `primaryexch` (non-N/Q/A component): X 11,866, B 1,978, I 251 |
| PERMNO ↔ Bloomberg entity_id crosswalk | `data_raw/manual` | `entity_id, permno` (+ match method/confidence) | **Not needed for Phase 1** (decided 2026-08-19) — `dsp500list_v2` is already PERMNO-native, so `build_constituent_panel.py`'s `crosswalk` argument now defaults to `None` and treats `entity_id == permno` directly. Kept as an optional code path, not deleted: still needed if a Bloomberg-only field (e.g. GICS sector) has to be joined on later | **not needed** (was: blocking) |
| Documented reconstitution effective dates (2-3 events) | `data_raw/manual` | Event name, announced effective date, source citation | The manual spot-check `membership_interval_convention.md` step 2 calls for (inclusive/exclusive date detection), now against CRSP `dsp500list_v2`'s `mbrenddt` rather than a Bloomberg field. The automated step-3 regression check (`_check_membership_interval_structure`) ran clean on the first real build: 29 gaps between consecutive same-permno intervals, median 1,854 days, **zero** exactly-1-day gaps — no evidence of a systematic inclusive-end-date bug, but this is not a substitute for the manual spot-check, which hasn't been done | **needed** — doesn't block the panel that's already built, but the panel isn't fully trusted at the reconstitution-boundary level until this runs |

## (b) Concentration measures — Phase 2

No new raw pulls. `src/concentration/measures.py` consumes
`data_final/universe/` exclusively.

| Dataset | Source | Purpose | Status |
|---|---|---|---|
| GICS sector/industry classification | `data_raw/bloomberg` (`GICS_SECTOR_NAME`) or `data_raw/compustat` (`gsector`) | Only needed if sector-adjusted concentration (mentioned as optional in `concentration-builder`'s scope) is implemented | **optional** — not required for the default HHI/CR-k/effective-N/entropy set |

## (c) CSI construction — Phase 3

No new raw pulls. `src/csi/` consumes `data_final/concentration/`
exclusively — by design (see
[csi_construction.md](../methodology_notes/csi_construction.md)), CSI
construction is pure aggregation with zero new external-data surface.

## (d) Physical-risk block — Phase 4

| Dataset | Source | Table / fields (candidate) | Purpose | Status |
|---|---|---|---|---|
| CRSP constituent returns | `data_raw/crsp` | Reused from Phase 1 | Realized risk at the entity level | **blocking** |
| CRSP market index returns | `data_raw/crsp` | CRSP Index File `vwretd`/`ewretd` (value- and equal-weighted market return) | Benchmark-relative risk measures; market-model residuals for CoVaR/MES-style systemic risk measures | **blocking** |
| Fama-French factors | via WRDS (Ken French Data Library mirror) or pulled directly | `Mkt-RF`, `SMB`, `HML`, `RF` at minimum | Control variables in predictive/conditional regressions (`physical-risk-analyst`'s scope explicitly mentions factor controls) | **needed** — doesn't block starting Phase 4 with univariate CSI-conditioned comparisons |
| Crisis/regime dating reference | `data_raw/manual` (e.g. NBER recession dates) | Episode start/end dates | Anchors "known stress episodes" for Phase 6 subperiod robustness | **deferred** to Phase 6 |

Source folder note: Fama-French factors don't fit any existing
`data_raw/` subfolder cleanly (not Bloomberg, CRSP, Compustat, or
OptionMetrics). Decide when this is actually pulled: either
`data_raw/manual/` (simplest, treat as a static reference file) or a new
`data_raw/famafrench/` if it needs periodic re-pulls — don't default this
silently.

## (e) Options-tail block — Phase 5

| Dataset | Source | Table / fields (candidate) | Purpose | Status |
|---|---|---|---|---|
| Bloomberg options chains | `data_raw/bloomberg` | Strikes, expirations, bid/ask/mid, implied vol, open interest per underlying-date | IV surface fitting and risk-neutral moment extraction | **blocking** — source decided (below), chain itself not yet pulled |
| ~~OptionMetrics IvyDB~~ | ~~`data_raw/optionmetrics`~~ | — | — | **not available** — this project's WRDS subscription does not include OptionMetrics access; `data_raw/optionmetrics/` removed 2026-08-25 (was an empty placeholder) |
| CSI | `data_final/csi/` | Reused from Phase 3 | Conditioning variable for "does the Q-tail premium widen with the CSI regime" | **blocking**, but already satisfied once Phase 3 completes |

**Source decision resolved (2026-08-25): Bloomberg is the primary (and only
available) options source.** OptionMetrics was never actually a live
option — no WRDS license for it — so this isn't a preference between two
available sources, it's the only one on the table. `bloomberg-extractor`
can write Phase 5 extraction code against Bloomberg without waiting on an
advisor call for this specific question.

Note this decision sits alongside a related, separately-found entitlement
gap: `spx_members_float_download.py` (Phase 1 weight cross-check, confirmed
2026-07-02) found this same Bloomberg subscription is *not* entitled to
official index-weight fields (`INDX_MWEIGHT_PX`'s "Percent Weight"/"Actual
Weight" return a degenerate constant). Different field family from options,
not evidence about options-chain entitlement either way.

**The confirmed field set for Phase 5, updated 2026-08-28, is the one now
in `bloomberg_field_reference.md`** — SPX ATM IV (30D, 3M; 6M/12M ATM
confirmed *not* available as a single field), a much wider skew-wing set
than before (1M 10/25/50-delta put and call, 2M 10/25/40/50-delta put and
call, 3M ATM put), the VIX family (spot, 9D, 3M, 6M), the CBOE SKEW index.
Phase 5 construction should design around this set as given.

**Update 2026-08-28 — the 1M/2M delta grid is now confirmed and pulled
into `spx_skew_wings_download.py`.** An FLDS search on "imp vol" against
`SPX Index` surfaced the real available delta-bucket family on this
subscription: 10/25/40/50 (plus redundant 75/90 call-side points) across
exactly two tenors, 1M and 2M. All were confirmed both via BDH (non-blank
from 2006) and BDP (real, differentiated current values, not the
degenerate-constant pattern seen on the unrelated official-index-weight
fields) — see `bloomberg_field_reference.md` section 2 for the full table.
This also resolves the earlier "untested, not unavailable" open question
below: the 3M/6M delta-wing family doesn't exist on this subscription at
all (not just the specific 25D-call/10D-put combination originally
tried) — confirmed by the FLDS search turning up zero 3M/6M delta-bucket
entries, not merely inferred.

**Open decision blocking pull scope:** index-level underlying (e.g. a
single broad index option chain) vs. a curated set of constituent-level
option chains vs. both. `options-tail-analyst`'s scope already flags that
these answer different questions; this inventory just makes explicit that
the decision has to be made *before* the pull, not after.

## (f) Passive flows — auxiliary channel block (Phase 4/6 input)

Not a numbered build phase — a mechanism-test control consumed by Phase 4
(physical-risk) and Phase 6 (integration) regressions alongside the CSI.
See [passive_flows_design.md](../methodology_notes/passive_flows_design.md)
for the full design rationale.

| Dataset | Source | Table / fields (candidate) | Purpose | Status |
|---|---|---|---|---|
| ETF AUM + net flow history (SPY, IVV, VOO, RSP) | `data_raw/bloomberg` | `FUND_TOTAL_ASSETS`, `FUND_FLOW` | Passive/mechanical demand pressure proxy; cap-weighted vs. equal-weighted flow differential | **done** — full historical pull confirmed 2026-08-25: `bloomberg_passive_flows_20260704.csv`, 23,572 rows, all 4 tickers, 1993-01-29 to 2026-07-02 |

## Open decisions summary

Everything below blocks starting extraction code for the phase noted, and
should be resolved (or explicitly deferred with a reason) before that
phase's agent begins pulling:

1. `dsp500list_v2.mbrenddt`'s inclusive/exclusive date convention — resolved
   as Bloomberg-sourced in the original phrasing of this item, superseded
   by the 2026-08-19 switch to CRSP-native membership. The automated
   regression check is clean (see the Phase 1 table above); the manual
   spot-check against 2-3 documented reconstitution events (`membership_interval_convention.md`
   step 2) still hasn't been run — **needed**, not blocking the panel that
   already exists.
2. Whether sector-adjusted concentration will be implemented — determines
   whether GICS/Compustat sector data is ever pulled — Phase 2, optional.
3. ~~Bloomberg vs. OptionMetrics as the primary options-tail source~~ —
   **resolved 2026-08-25: Bloomberg**, OptionMetrics not licensed under
   this project's WRDS subscription.
4. Index-level vs. constituent-level (vs. both) options underlyings —
   still open, blocks Phase 5 pull scope.
5. Fama-French factor source and storage location (`data_raw/manual/` vs.
   a new `data_raw/famafrench/`) — needed for Phase 4, not blocking.
