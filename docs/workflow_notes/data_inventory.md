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
| Index membership + weight history | `data_raw/bloomberg` | Periodic weight snapshot per constituent (Shape A in [membership_interval_convention.md](../methodology_notes/membership_interval_convention.md)), e.g. `INDX_MWEIGHT_PX`/`INDX_MWEIGHT_HIST`-class field for the chosen index | Defines the constituent set and weight for the phase-1 point-in-time panel | **blocking** |
| Constituent identifiers | `data_raw/bloomberg` | `BB_TICKER`, `ID_CUSIP`, `ID_ISIN`, `ID_BB_GLOBAL` per constituent-date | Builds the entity_id side of the PERMNO crosswalk | **blocking** |
| CRSP Daily/Monthly Stock File | `data_raw/crsp` | `PERMNO`, `date`, `RET`, `PRC`, `SHROUT`, `SHRCD`, `EXCHCD` | Realized return series — used here and reused in Phase 4 | **blocking** |
| CRSP Delisting file | `data_raw/crsp` | `PERMNO`, `DLRET`, `DLSTDT`, `DLSTCD` | Delisting-adjusted returns; omitting this biases realized risk downward exactly at index-exit events, which matter for a concentration/systemic-risk thesis | **blocking** |
| CRSP Names/Header (Stock Event) file | `data_raw/crsp` | `PERMNO`, `PERMCO`, CUSIP history, ticker history, `NAMEDT`/`NAMEENDT` | Supports crosswalk matching across CUSIP/ticker changes over time (a straight current-CUSIP match will miss renamed/re-CUSIPed names) | **blocking** |
| PERMNO ↔ Bloomberg entity_id crosswalk | `data_raw/manual` | `entity_id, permno` (+ match method/confidence) | Resolves cases an automated CUSIP/ISIN match can't (formatting differences, share-class ambiguity) | **blocking** |
| Documented reconstitution effective dates (2-3 events) | `data_raw/manual` | Event name, announced effective date, source citation | The spot-check inputs required by membership_interval_convention.md step 2 (inclusive/exclusive detection) | **blocking** — needed before the first panel build is trusted |

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
| Bloomberg options chains | `data_raw/bloomberg` | Strikes, expirations, bid/ask/mid, implied vol, open interest per underlying-date | IV surface fitting and risk-neutral moment extraction | **blocking** — pending source decision below |
| OptionMetrics IvyDB | `data_raw/optionmetrics` | Option Prices (best bid/offer, IV), Security Prices (underlying alignment), Zero Curve (risk-free term structure for BKM-type moment formulas), Standardized Options / Volatility Surface (if licensed) | Cleaner, pre-standardized alternative/complement to raw Bloomberg chains; often preferred for surface-fitting robustness | **blocking** — pending source decision below |
| CSI | `data_final/csi/` | Reused from Phase 3 | Conditioning variable for "does the Q-tail premium widen with the CSI regime" | **blocking**, but already satisfied once Phase 3 completes |

**Open decision blocking this phase's pull scope:** is Bloomberg or
OptionMetrics the primary options source, with the other used for
cross-validation, or is only one licensed for this thesis? This must be
confirmed with the advisor before `bloomberg-extractor`/`options-tail-analyst`
write any Phase 5 extraction code — pulling both blind wastes a WRDS/
Bloomberg query cycle on data that may not end up used.

**Open decision blocking pull scope:** index-level underlying (e.g. a
single broad index option chain) vs. a curated set of constituent-level
option chains vs. both. `options-tail-analyst`'s scope already flags that
these answer different questions; this inventory just makes explicit that
the decision has to be made *before* the pull, not after.

## Open decisions summary

Everything below blocks starting extraction code for the phase noted, and
should be resolved (or explicitly deferred with a reason) before that
phase's agent begins pulling:

1. Exact Bloomberg field mnemonic for index membership/weight history, and
   its inclusive/exclusive date convention — blocks Phase 1
   (see [membership_interval_convention.md](../methodology_notes/membership_interval_convention.md)).
2. Whether sector-adjusted concentration will be implemented — determines
   whether GICS/Compustat sector data is ever pulled — Phase 2, optional.
3. Bloomberg vs. OptionMetrics as the primary options-tail source — blocks
   Phase 5.
4. Index-level vs. constituent-level (vs. both) options underlyings —
   blocks Phase 5 pull scope.
5. Fama-French factor source and storage location (`data_raw/manual/` vs.
   a new `data_raw/famafrench/`) — needed for Phase 4, not blocking.
